# loop.ps1 - the self-reinforcement loop for L0. ASCII-ONLY (see gate.ps1).
#
# What it closes
# --------------
# The pit library carries 87 entries, each with a "retire-when" clause. That
# clause is not prose -- it is a spec for the gate that would make the pit
# structurally impossible (P7's reads: "the destructive-test framework must
# assert the sha differs before and after the break").
# But the library cannot tell which of those specs are already built. So
# "already guarded" and "nobody is watching this" sit in the same table looking
# identical -- which is the exact failure mode the ledger warns about one level
# up: a rule that never fired and a rule that was never wired look the same.
#
# This command separates them, and orders what is left by how many times the
# pit has ACTUALLY happened. That ordering matters: it turns "68 pits unguarded"
# (paralysing) into "this one bit you 4 times and nothing guards it" (actionable).
#
# Guard rate is the one number that grows with use. It is the only quantifiable
# form of "the more people use it, the more accurate this method gets".
#
# Usage:
#   powershell -NoProfile -File loop.ps1              # summary + top gaps
#   powershell -NoProfile -File loop.ps1 -All         # every gap
#   powershell -NoProfile -File loop.ps1 -Guarded     # what IS covered, and by what

param(
    [switch]$All,
    [switch]$Guarded,
    [switch]$Excluded,
    [int]$Top = 12
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$HookDir = $PSScriptRoot
$Skills = Split-Path -Parent (Split-Path -Parent $HookDir)

function Load-Json($p, $label) {
    if (-not (Test-Path $p)) { Write-Output "[XX] missing $label : $p"; exit 1 }
    try { return Get-Content -Raw -Encoding UTF8 -Path $p | ConvertFrom-Json }
    catch { Write-Output "[XX] cannot parse $label : $p"; exit 1 }
}

$cfg = Load-Json (Join-Path $HookDir 'config.json') 'config.json'
$mapDoc = Load-Json (Join-Path $HookDir 'pit_gate_map.json') 'pit_gate_map.json'
# The pit library has a Chinese filename, which this ASCII-only script cannot
# spell. Same rule as gate.ps1: paths with non-ASCII live in config.json.
$pitPath = Join-Path $Skills ((([string]$cfg.paths.pits)) -replace '/', '\')
if (-not (Test-Path $pitPath)) { Write-Output "[XX] pit library not found: $pitPath"; exit 1 }

# ---- parse the pit library ---------------------------------------------------
# Row shape: | id | one-line pit | prevention | origin | hits | retire-when | added | contributor |
$pits = @()
$section = ''
foreach ($line in (Get-Content -Encoding UTF8 -Path $pitPath)) {
    if ($line -match '^##\s+(.+)$') { $section = $matches[1].Trim(); continue }
    if ($line -notmatch '^\|\s*([A-Z]+[0-9]+)\s*\|') { continue }
    $cells = $line.Split('|')
    if ($cells.Count -lt 7) { continue }
    $id = $cells[1].Trim()
    $hitRaw = $cells[5].Trim()
    # Column 7 is the date the entry was filed. Entries filed on or before
    # 2026-08-16 carry retire-criteria the AI derived, not the founder's words --
    # the library says so itself. Those criteria are exactly what the gap list
    # hands you as a "spec", so a shaky one has to be visible BEFORE you build
    # against it. The cutoff is read from the date column rather than a written
    # count: the original note said "these 38", and 38 stopped meaning anything
    # two days later when the library grew (that is pit S10, committed inside the
    # file that records S10).
    $filed = ''
    if ($cells.Count -ge 8) { $filed = $cells[7].Trim() }
    $unreviewed = ($filed -ne '' -and $filed -le '2026-08-16')
    # The hits column is either a number, a number with a CJK parenthetical, the
    # single char U+591A meaning "many", or U+2014 (em dash) meaning "not counted".
    # !! U+591A is written as an escape, not as a literal: this file must stay
    #    ASCII (PowerShell 5.1 reads a BOM-less UTF-8 script as ANSI), and a
    #    mojibake literal here would silently never match -- the pits marked
    #    "many" would score 0 and sink to the bottom of the priority list, which
    #    is exactly backwards. Code point looked up with python, not recalled
    #    (pit library W7: AI fabricates code points; it has done so 4 times).
    $MANY = [string][char]0x591A
    $hits = 0
    if ($hitRaw -match '^\s*(\d+)') { $hits = [int]$matches[1] }
    elseif ($hitRaw.StartsWith($MANY)) { $hits = 9 }
    $pits += [pscustomobject]@{
        id         = $id
        section    = $section
        pit        = $cells[2].Trim()
        hits       = $hits
        hitRaw     = $hitRaw
        retire     = $cells[6].Trim()
        unreviewed = $unreviewed
    }
}

if ($pits.Count -eq 0) { Write-Output "[XX] parsed 0 pits from $pitPath - the parser is wrong, not the library"; exit 1 }

# ---- fold in guards ----------------------------------------------------------
$mapped = @{}
foreach ($p in $mapDoc.map.PSObject.Properties) { $mapped[$p.Name] = $p.Value }

# ---- fold in gate firing counts ---------------------------------------------
$fired = @{}
$traceDir = Join-Path $HookDir ([string]$cfg.traces.dir)
if (Test-Path $traceDir) {
    foreach ($f in (Get-ChildItem -Path $traceDir -Filter '*.jsonl' -File)) {
        foreach ($ln in (Get-Content -Encoding UTF8 -Path $f.FullName)) {
            if ([string]::IsNullOrWhiteSpace($ln)) { continue }
            try { $e = $ln | ConvertFrom-Json } catch { continue }
            $r = [string]$e.rule
            if ($r) { if ($fired.ContainsKey($r)) { $fired[$r] += 1 } else { $fired[$r] = 1 } }
        }
    }
}

# Pits explicitly ruled out as gate material, with a reason each.
# !! They come OUT of the denominator. The denominator has to be "pits a gate
#    could plausibly catch", not "all pits" -- otherwise the rate can never
#    reach 100% and stops meaning anything, and worse, the top of the gap list
#    fills up with things no gate can do (P17 wants a human planning checkpoint,
#    P4 wants a test-set construction rule). Building gates for those yields
#    false positives, and the first thing anyone does with a gate that cries
#    wolf is switch it off -- taking the working ones with it.
$notGateable = @{}
if ($mapDoc.not_gateable) {
    foreach ($p in $mapDoc.not_gateable.PSObject.Properties) {
        if ($p.Name -notlike '_*' -and $p.Name -ne 'kinds') { $notGateable[$p.Name] = $p.Value }
    }
}

# !! $covered / $ruledOut, NOT $guarded / $excluded: PowerShell variable names
#    are case-insensitive, so a local named $excluded silently IS the
#    [switch]$Excluded parameter, and assigning an array to it fails with a
#    type error pointing at the wrong line. Hit this twice in this file --
#    once for $guarded, then again for $excluded after the first fix.
#    Same shape twice is a rule, not an accident: never name a local after a param.
$covered = @($pits | Where-Object { $mapped.ContainsKey($_.id) })
$ruledOut = @($pits | Where-Object { $notGateable.ContainsKey($_.id) })
$gaps = @($pits | Where-Object { -not $mapped.ContainsKey($_.id) -and -not $notGateable.ContainsKey($_.id) } |
          Sort-Object -Property @{Expression = 'hits'; Descending = $true}, 'id')
$denom = $pits.Count - $ruledOut.Count
$rate = 0
if ($denom -gt 0) { $rate = [math]::Round(100.0 * $covered.Count / $denom, 1) }

Write-Output ''
Write-Output ('=' * 96)
Write-Output ("L0 self-reinforcement loop   --   guard rate {0}%  ({1} of {2} gateable pits are guarded)" -f $rate, $covered.Count, $denom)
if ($ruledOut.Count -gt 0) {
    Write-Output ("   {0} of {1} pits are ruled out as gate material (run -Excluded to see why)." -f $ruledOut.Count, $pits.Count)
}
Write-Output ('=' * 96)
Write-Output 'This number is the only one that grows with use. It is what "the method gets more'
Write-Output 'accurate the more it is used" looks like when you can actually measure it.'
Write-Output ''

# ---- 1. dumb gates: wired but never fired ------------------------------------
Write-Output '--- [1] gates that never fired ------------------------------------------------'
$anyDumb = $false
foreach ($prop in $cfg.gates.PSObject.Properties) {
    $rid = [string]$prop.Value.rule_id
    $n = 0
    if ($fired.ContainsKey($rid)) { $n = $fired[$rid] }
    if ($n -eq 0 -and $prop.Value.enabled) {
        Write-Output ("  {0,-11} {1,-15} 0 events" -f $rid, $prop.Name)
        $anyDumb = $true
    }
}
if (-not $anyDumb) {
    Write-Output '  (none - every enabled gate has fired at least once)'
} else {
    Write-Output ''
    Write-Output '  A gate that never fired and a gate that was never wired look identical from'
    Write-Output '  outside. Run tests/hooks_gate_test.py to rule out the second before concluding'
    Write-Output '  the first. Do not retire a rule on this column alone.'
}
Write-Output ''

# ---- 2. gaps: pits nothing is watching ---------------------------------------
Write-Output '--- [2] pits with NO guard, ordered by how many times they actually bit --------'
Write-Output ''
$show = $gaps
if (-not $All) { $show = $gaps | Select-Object -First $Top }
foreach ($g in $show) {
    $mark = ''
    # hitRaw looks like "4" / "2(same day twice)" / "6 +Savant..." with CJK
    # punctuation this script cannot spell -- keep only the leading digits.
    if ($g.hits -ge 2) { $mark = ('  [bit ' + $g.hits + ' times]') }
    Write-Output ("  {0,-5} {1}{2}" -f $g.id, $g.pit.Substring(0, [Math]::Min(76, $g.pit.Length)), $mark)
    if ($g.retire) {
        $tag = ''
        if ($g.unreviewed) { $tag = '  [criterion UNREVIEWED - check it before building to it]' }
        Write-Output ("        spec: {0}{1}" -f $g.retire.Substring(0, [Math]::Min(84, $g.retire.Length)), $tag)
    }
    Write-Output ''
}
if (-not $All -and $gaps.Count -gt $Top) {
    Write-Output ("  ... and {0} more. Run with -All to see every one." -f ($gaps.Count - $Top))
    Write-Output ''
}
Write-Output '  The "spec:" line is that pit''s own retire-when clause, verbatim. It already'
Write-Output '  describes the gate that would make the pit impossible -- it is a specification,'
Write-Output '  not a wish. Building it is how a pit retires; deleting the row is not.'
$unrev = @($pits | Where-Object { $_.unreviewed }).Count
if ($unrev -gt 0) {
    Write-Output ''
    Write-Output ("  [!] {0} of {1} criteria are marked UNREVIEWED (filed on or before 2026-08-16)." -f $unrev, $pits.Count)
    Write-Output '      Those were derived by an AI from the pit''s cause, not written by the author.'
    Write-Output '      Do NOT batch-approve them. Review one only when you are about to act on it --'
    Write-Output '      either building a gate to that spec, or retiring that pit. Batch review while'
    Write-Output '      tired is worse than no review: it converts "unsure" into "approved" in one pass.'
}
Write-Output ''

# ---- 3. what is covered ------------------------------------------------------
if ($Guarded) {
    Write-Output '--- [3] pits that DO have a guard ---------------------------------------------'
    Write-Output ''
    foreach ($g in ($covered | Sort-Object id)) {
        $m = $mapped[$g.id]
        $partial = ''
        if ($m.partial) { $partial = '   [PARTIAL]' }
        Write-Output ("  {0,-5} {1}{2}" -f $g.id, $g.pit.Substring(0, [Math]::Min(70, $g.pit.Length)), $partial)
        # `internal:` = that guard lives only in the author's repo and is not
        # shipped. For someone holding a release, that pit has NO guard at all --
        # show it, so the guard rate does not read stronger than it is.
        $gs = @($m.guards | ForEach-Object {
            if ([string]$_ -like 'internal:*') { ([string]$_).Substring(9) + ' (internal)' } else { [string]$_ }
        })
        Write-Output ("        by:  {0}  ({1})" -f ($gs -join ', '), [string]$m.kind)
        if ($m.how) { Write-Output ("        how: {0}" -f ([string]$m.how).Substring(0, [Math]::Min(84, ([string]$m.how).Length))) }
        Write-Output ''
    }
}

# ---- next action -------------------------------------------------------------
if ($Excluded) {
    Write-Output '--- [4] pits ruled OUT as gate material ---------------------------------------'
    Write-Output ''
    foreach ($g in ($ruledOut | Sort-Object id)) {
        $e = $notGateable[$g.id]
        Write-Output ("  {0,-5} {1}" -f $g.id, $g.pit.Substring(0, [Math]::Min(70, $g.pit.Length)))
        Write-Output ("        kind: {0}   ->  handled by: {1}" -f [string]$e.kind, [string]$e.by)
        Write-Output ("        why : {0}" -f ([string]$e.why).Substring(0, [Math]::Min(88, ([string]$e.why).Length)))
        Write-Output ''
    }
    Write-Output '  Ruled out means "not L0''s job", NOT "nobody has to deal with it".'
    Write-Output '  The `handled by` line has to name someone. If it cannot, the entry does not'
    Write-Output '  belong here -- that would be using a category to hide the fact that nobody owns it.'
    Write-Output ''
}

Write-Output ('=' * 96)
$top1 = $gaps | Select-Object -First 1
if ($top1) {
    Write-Output ("Next gate to build:  {0}  (recorded {1} occurrences, nothing guards it)" -f $top1.id, $top1.hits)
    Write-Output ("Its spec is already written: {0}" -f $top1.retire)
} else {
    Write-Output 'Every pit has a guard. Now go check the guards are not lying -- run the regression.'
}
Write-Output ''
Write-Output '[!] Guard rate is not a score to maximise. A wrong mapping raises it while deleting'
Write-Output '    the very line that should have told you to build something. Empty beats wrong --'
Write-Output '    the pit library says the same about its own retire-when column.'
