# tally.ps1 - render the L0 rule ledger from traces. NOTHING here is hand-written.
#
# ASCII-ONLY (same reason as gate.ps1: PowerShell 5.1 misreads BOM-less UTF-8).
# Rule text comes from config.json; counts come from traces/*.jsonl.
#
# Why this exists:
#   The rule ledger template has two columns -- "how many times did it fire" and
#   "which rule actually prevented an incident". Those are the columns its own
#   delete-criterion depends on ("never triggered").
#   A hand-maintained count rots the moment someone forgets to update it, and a
#   rotten count is worse than none: it reads as evidence.
#   So the ledger is not a document you edit. It is this command's output.
#
# Usage:
#   powershell -NoProfile -File tally.ps1
#   powershell -NoProfile -File tally.ps1 -Days 7
#   powershell -NoProfile -File tally.ps1 -Detail          # list the blocked events

param(
    [int]$Days = 0,
    [switch]$Detail
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$HookDir = $PSScriptRoot
$CfgPath = Join-Path $HookDir 'config.json'

try {
    $cfg = Get-Content -Raw -Encoding UTF8 -Path $CfgPath | ConvertFrom-Json
} catch {
    Write-Output "[XX] cannot read config.json: $CfgPath"
    exit 1
}

$traceDir = Join-Path $HookDir ([string]$cfg.traces.dir)
if (-not (Test-Path $traceDir)) {
    Write-Output "[i] no traces yet: $traceDir"
    Write-Output "    An empty ledger and a disconnected gate look identical from outside."
    Write-Output "    Verify the gate is wired: run tests/hooks_gate_test.py."
    exit 0
}

$cut = $null
if ($Days -gt 0) { $cut = (Get-Date).AddDays(-$Days) }

$events = @()
foreach ($f in (Get-ChildItem -Path $traceDir -Filter '*.jsonl' -File)) {
    foreach ($line in (Get-Content -Encoding UTF8 -Path $f.FullName)) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try { $e = $line | ConvertFrom-Json } catch { continue }
        if ($cut) {
            $t = $null
            try { $t = [datetime]::Parse([string]$e.ts) } catch { }
            if ($t -and $t -lt $cut) { continue }
        }
        $events += $e
    }
}

$span = 'all time'
if ($Days -gt 0) { $span = "last $Days days" }
Write-Output ''
Write-Output ("L0 rule ledger  --  machine-generated from traces, $span")
Write-Output ('=' * 100)
Write-Output ("{0,-11} {1,-14} {2,7} {3,7} {4,7} {5,7} {6,7} {7,7}  {8}" -f `
    'rule', 'gate', 'block', 'deny', 'warn', 'retry', 'inject', 'RELEAS', 'last seen')
Write-Output ('-' * 100)

$anyReleased = $false
foreach ($prop in $cfg.gates.PSObject.Properties) {
    $name = $prop.Name
    $rid = [string]$prop.Value.rule_id
    $rows = @($events | Where-Object { $_.gate -eq $name })
    $c = @{}
    foreach ($a in @('block', 'deny', 'warn', 'pass_on_retry', 'released', 'inject')) {
        $c[$a] = @($rows | Where-Object { $_.action -eq $a }).Count
    }
    $last = ''
    if ($rows.Count -gt 0) {
        $lastRow = $rows | Sort-Object { [string]$_.ts } | Select-Object -Last 1
        $last = ([string]$lastRow.ts)
        if ($last.Length -gt 19) { $last = $last.Substring(0, 19) }
    }
    if ($c['released'] -gt 0) { $anyReleased = $true }
    $flag = ''
    if ($rows.Count -eq 0) { $flag = '   <- never fired' }
    Write-Output ("{0,-11} {1,-14} {2,7} {3,7} {4,7} {5,7} {6,7} {7,7}  {8}{9}" -f `
        $rid, $name, $c['block'], $c['deny'], $c['warn'], $c['pass_on_retry'], $c['inject'], $c['released'], $last, $flag)
}

Write-Output ('-' * 100)
Write-Output ("total events: {0}" -f $events.Count)
Write-Output ''

# The two readings that matter, spelled out -- a table nobody knows how to read
# is the same as no table.
Write-Output 'How to read this:'
Write-Output '  block/deny  = the rule actually stopped something. These are the rows that go into'
Write-Output '                the ledger column "which rule really prevented an incident".'
Write-Output '  RELEAS      = the loop breaker gave up after repeated blocks. A nonzero number here'
Write-Output '                means the rule did NOT hold that turn -- this is the column to watch.'
Write-Output '  inject      = a non-blocking gate ran. It exists so that gates which never block'
Write-Output '                still leave proof they are wired, instead of reading as "never fired".'
Write-Output '  never fired = EITHER the thing it guards never happened, OR the gate is not wired.'
Write-Output '                Those two look identical from outside. Do not delete a rule on this'
Write-Output '                alone -- run tests/hooks_gate_test.py first to rule out the second.'
if ($anyReleased) {
    Write-Output ''
    Write-Output '[!!] Some turns ended in RELEASED: the gate blocked, the model still did not comply,'
    Write-Output '     and the turn was let through. Those turns are unverified by construction.'
}

if ($Detail) {
    Write-Output ''
    Write-Output 'Blocked / denied events:'
    Write-Output ('-' * 100)
    foreach ($e in ($events | Where-Object { $_.action -eq 'block' -or $_.action -eq 'deny' })) {
        $what = ''
        if ($e.first_line) { $what = [string]$e.first_line }
        elseif ($e.command) { $what = [string]$e.command }
        elseif ($e.path) { $what = [string]$e.path }
        if ($what.Length -gt 68) { $what = $what.Substring(0, 68) + '...' }
        $ts = [string]$e.ts
        if ($ts.Length -gt 19) { $ts = $ts.Substring(0, 19) }
        Write-Output ("  {0}  {1,-11} {2,-6} {3}" -f $ts, [string]$e.rule, [string]$e.action, $what)
    }
}
