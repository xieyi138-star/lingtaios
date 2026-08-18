# gate.ps1 - L0 enforcement gate for Claude Code hooks (Windows / PowerShell 5.1+).
#
# ASCII-ONLY BY DESIGN. Do not put Chinese characters in this file.
#   PowerShell 5.1 decodes a BOM-less UTF-8 script as ANSI, so any Chinese
#   literal here would silently turn into mojibake. Every human-facing string
#   lives in config.json and is read back as UTF-8 at runtime.
#   This also honours the machine rule "no Chinese on the PowerShell command line".
#
# Contract with Claude Code:
#   stdin  - one JSON object, field hook_event_name selects the branch
#   stdout - JSON decision object, or plain text for SessionStart
#   exit 0 - always. Blocking is expressed through the JSON body, never the code.
#
# FAIL-OPEN, LOUDLY. If this gate itself breaks it must not stop the user from
# working -- a gate that bricks the session gets deleted, and then there is no
# gate at all. But a silent fallback is worse than none, so every internal
# failure is surfaced via systemMessage and written to traces.

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$HookDir = $PSScriptRoot
$CfgPath = Join-Path $HookDir 'config.json'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# ---------------------------------------------------------------- helpers ---

function Emit-Json($obj) {
    # ConvertTo-Json escapes non-ASCII as \uXXXX. That is exactly what we want:
    # the payload stays pure ASCII on the wire and Claude Code decodes it back,
    # so console codepage never gets a chance to corrupt the Chinese text.
    Write-Output ($obj | ConvertTo-Json -Depth 12 -Compress)
}

function Write-Trace($record) {
    try {
        if (-not $script:Cfg) { return }
        if (-not $script:Cfg.traces.enabled) { return }
        $dir = Join-Path $HookDir $script:Cfg.traces.dir
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        $day = Get-Date -Format 'yyyy-MM-dd'
        $file = Join-Path $dir ("$day.jsonl")
        $record['ts'] = (Get-Date -Format 'o')
        $line = ($record | ConvertTo-Json -Depth 12 -Compress)
        [IO.File]::AppendAllText($file, $line + "`r`n", $Utf8NoBom)
    } catch {
        # Never let bookkeeping break the gate.
    }
}

function Get-StatePath($sessionId) {
    $dir = Join-Path (Join-Path $HookDir $script:Cfg.traces.dir) '.state'
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $safe = ($sessionId -replace '[^A-Za-z0-9_\-]', '_')
    if ([string]::IsNullOrWhiteSpace($safe)) { $safe = 'nosession' }
    return (Join-Path $dir "$safe.json")
}

function Read-State($sessionId) {
    $p = Get-StatePath $sessionId
    if (Test-Path $p) {
        try {
            $o = Get-Content -Raw -Encoding UTF8 -Path $p | ConvertFrom-Json
            $h = @{}
            foreach ($prop in $o.PSObject.Properties) { $h[$prop.Name] = $prop.Value }
            return $h
        } catch { return @{} }
    }
    return @{}
}

function Save-State($sessionId, $state) {
    try {
        $p = Get-StatePath $sessionId
        $json = ($state | ConvertTo-Json -Depth 8 -Compress)
        [IO.File]::WriteAllText($p, $json, $Utf8NoBom)
    } catch { }
}

function Fill($template, $map) {
    $s = $template
    foreach ($k in $map.Keys) { $s = $s.Replace('{' + $k + '}', [string]$map[$k]) }
    return $s
}

function Gate-On($name) {
    if (-not $script:Cfg.master_switch) { return $false }
    $g = $script:Cfg.gates.$name
    if (-not $g) { return $false }
    return [bool]$g.enabled
}

function Count-VerifyToolsThisTurn($transcriptPath, $verifyTools) {
    # How many query-type tool calls happened since the last REAL human message.
    #
    # Transcript is JSONL. A human turn is type=="user" whose message.content is a
    # STRING; tool results are also type=="user" but carry a content ARRAY of
    # tool_result blocks. Getting that distinction wrong makes every turn look
    # like it starts at the last tool result -- i.e. always zero tools -- and the
    # gate would fire on every single reply.
    #
    # Returns: -1 when the transcript cannot be read/parsed. -1 is NOT zero.
    # Zero means "verified: it queried nothing". -1 means "cannot tell", and the
    # caller must fail open and say so -- a gate that silently treats "unknown"
    # as "guilty" trains people to disable it.
    if (-not $transcriptPath -or -not (Test-Path -LiteralPath $transcriptPath)) { return -1 }
    try {
        $lines = Get-Content -LiteralPath $transcriptPath -Encoding UTF8 -Tail 900
    } catch { return -1 }
    if (-not $lines) { return -1 }

    $startIdx = 0
    for ($i = $lines.Count - 1; $i -ge 0; $i--) {
        $ln = $lines[$i]
        if ([string]::IsNullOrWhiteSpace($ln)) { continue }
        if ($ln -notmatch '"type"\s*:\s*"user"') { continue }
        try { $o = $ln | ConvertFrom-Json } catch { continue }
        if ([string]$o.type -ne 'user') { continue }
        $c = $o.message.content
        if ($c -is [string] -and -not [string]::IsNullOrWhiteSpace($c)) { $startIdx = $i; break }
    }

    $n = 0
    for ($i = $startIdx; $i -lt $lines.Count; $i++) {
        $ln = $lines[$i]
        if ([string]::IsNullOrWhiteSpace($ln)) { continue }
        if ($ln -notmatch '"tool_use"') { continue }
        try { $o = $ln | ConvertFrom-Json } catch { continue }
        if ([string]$o.type -ne 'assistant') { continue }
        foreach ($blk in ($o.message.content)) {
            if ([string]$blk.type -eq 'tool_use' -and ($verifyTools -contains [string]$blk.name)) { $n++ }
        }
    }
    return $n
}

function Hash-Text($t) {
    $md5 = [Security.Cryptography.MD5]::Create()
    $bytes = [Text.Encoding]::UTF8.GetBytes([string]$t)
    return ([BitConverter]::ToString($md5.ComputeHash($bytes)) -replace '-', '').Substring(0, 16)
}

# ------------------------------------------------------------------- boot ---

# Read stdin as raw bytes and decode as UTF-8 explicitly.
#
# !! Do NOT use [Console]::In.ReadToEnd(). It decodes with [Console]::InputEncoding,
#    which on Windows defaults to the ANSI codepage (936/GBK here), not UTF-8.
#    Claude Code sends UTF-8. The failure mode is nasty and one-sided: ASCII
#    payloads pass fine, so a smoke test looks green -- but the evidence header
#    is Chinese, so it turns to mojibake and NEVER matches. The gate would then
#    block every single reply, including correct ones, and the first thing a
#    user does with a gate that cries wolf is delete it.
#    Caught by the negative assertion (valid header must PASS), not by the
#    positive one -- the positive test was green the whole time.
$rawIn = ''
try {
    $stdinStream = [Console]::OpenStandardInput()
    $reader = New-Object System.IO.StreamReader($stdinStream, (New-Object System.Text.UTF8Encoding($false)))
    $rawIn = $reader.ReadToEnd()
    $reader.Dispose()
} catch {
    try { $rawIn = [Console]::In.ReadToEnd() } catch { }
}
if ([string]::IsNullOrWhiteSpace($rawIn)) { exit 0 }

$payload = $null
try { $payload = $rawIn | ConvertFrom-Json } catch { exit 0 }

$script:Cfg = $null
try {
    $script:Cfg = Get-Content -Raw -Encoding UTF8 -Path $CfgPath | ConvertFrom-Json
} catch {
    # Config unreadable: the gate is effectively off. Say so out loud -- this is
    # precisely the "silent fallback" the constitution forbids.
    Emit-Json @{ systemMessage = "[L0] gate config unreadable, ALL GATES ARE OFF: $CfgPath" }
    exit 0
}

if (-not $script:Cfg.master_switch) {
    Emit-Json @{ systemMessage = "[L0] master_switch=false in hooks/config.json - all gates are OFF." }
    exit 0
}

$evtName = [string]$payload.hook_event_name
$sid = [string]$payload.session_id

# ============================================================ SessionStart ===

if ($evtName -eq 'SessionStart') {
    if (-not (Gate-On 'session_start')) { exit 0 }
    $g = $script:Cfg.gates.session_start
    # HookDir = <skills>\project-delivery\hooks  ->  two levels up is the repo root.
    $skills = Split-Path -Parent (Split-Path -Parent $HookDir)
    $active = @()
    foreach ($prop in $script:Cfg.gates.PSObject.Properties) {
        if ($prop.Value.enabled) { $active += ($prop.Value.rule_id + ' ' + $prop.Name) }
    }
    # Chinese file names come from config.json -- this script cannot spell them.
    $mapPath  = Join-Path $skills (([string]$script:Cfg.paths.map)  -replace '/', '\')
    $corePath = Join-Path $skills (([string]$script:Cfg.paths.core) -replace '/', '\')

    # Guard rate, computed cheaply: count pit rows, count mapped ids. No sorting,
    # no trace scan -- SessionStart has a 20s budget and this runs on every window.
    # The full analysis lives in loop.ps1; here we only surface the one number, so
    # that "how much is actually defended" is impossible to not see.
    $pitCount = 0; $coveredCount = 0; $rate = 0
    try {
        $pitPath = Join-Path $skills (([string]$script:Cfg.paths.pits) -replace '/', '\')
        if (Test-Path $pitPath) {
            $pitCount = @(Select-String -Path $pitPath -Pattern '^\|\s*[A-Z]+[0-9]+\s*\|' -Encoding UTF8).Count
        }
        $mapFile = Join-Path $HookDir 'pit_gate_map.json'
        if (Test-Path $mapFile) {
            $md = Get-Content -Raw -Encoding UTF8 -Path $mapFile | ConvertFrom-Json
            $coveredCount = @($md.map.PSObject.Properties).Count
        }
        if ($pitCount -gt 0) { $rate = [math]::Round(100.0 * $coveredCount / $pitCount, 1) }
    } catch { }

    $text = Fill $g.inject @{
        map     = $mapPath
        core    = $corePath
        readme  = (Join-Path $HookDir 'README.md')
        active  = ($active -join ' | ')
        rate    = $rate
        pits    = $pitCount
        covered = $coveredCount
        loop    = (Join-Path $HookDir 'loop.ps1')
    }
    # This gate never blocks, so it can never produce a block/deny row. Without
    # its own record it shows up in the ledger as "never fired" -- which is the
    # exact signal that means "or it was never wired". Record the injection.
    Write-Trace @{
        rule    = [string]$g.rule_id
        gate    = 'session_start'
        action  = 'inject'
        session = $sid
        startup = [string]$payload.startup_type
    }
    # SessionStart: plain stdout is injected into context.
    Write-Output $text
    exit 0
}

# =================================================================== Stop ====

if ($evtName -eq 'Stop' -or $evtName -eq 'SubagentStop') {
    $msg = [string]$payload.last_assistant_message
    $state = Read-State $sid
    $notices = @()

    # ---- R-L0-002 redline phrases: record and warn, never block -------------
    if (Gate-On 'redline') {
        $g2 = $script:Cfg.gates.redline
        $hits = @()
        foreach ($p in $g2.phrases) { if ($msg -and $msg.Contains([string]$p)) { $hits += [string]$p } }
        if ($hits.Count -gt 0) {
            Write-Trace @{
                rule    = [string]$g2.rule_id
                gate    = 'redline'
                action  = 'warn'
                session = $sid
                hits    = $hits
            }
            $notices += (Fill $g2.notice @{ hits = ($hits -join ' / ') })
        }
    }

    # ---- R-L0-006 claiming something is live without verifying it -----------
    # Pit S3, six occurrences, the most-bitten entry in the whole library.
    if (Gate-On 'claim') {
        $g6 = $script:Cfg.gates.claim
        $chits = @()
        foreach ($p in $g6.claim_phrases) { if ($msg -and $msg.Contains([string]$p)) { $chits += [string]$p } }
        if ($chits.Count -gt 0) {
            $nv = Count-VerifyToolsThisTurn ([string]$payload.transcript_path) $g6.verify_tools
            if ($nv -lt 0) {
                # Cannot tell. Fail open, out loud -- never guess guilty.
                $notices += [string]$g6.transcript_unreadable_notice
            } elseif ($nv -eq 0) {
                $cn = 0
                if ($state.ContainsKey('claim_blocks')) { $cn = [int]$state['claim_blocks'] }
                $cn = $cn + 1
                if ($cn -gt [int]$g6.max_consecutive_blocks) {
                    $state['claim_blocks'] = 0
                    Save-State $sid $state
                    Write-Trace @{ rule = [string]$g6.rule_id; gate = 'claim'; action = 'released'
                                   session = $sid; count = $cn; hits = $chits }
                    $notices += (Fill $g6.release_notice @{ count = $cn })
                } else {
                    $state['claim_blocks'] = $cn
                    Save-State $sid $state
                    Write-Trace @{ rule = [string]$g6.rule_id; gate = 'claim'; action = 'block'
                                   session = $sid; count = $cn; hits = $chits; verify_tools = 0 }
                    Emit-Json @{ decision = 'block'; reason = (Fill $g6.block_reason @{ hits = ($chits -join ' / ') }) }
                    exit 0
                }
            } else {
                if ($state.ContainsKey('claim_blocks') -and [int]$state['claim_blocks'] -gt 0) {
                    $state['claim_blocks'] = 0
                    Save-State $sid $state
                }
            }
        }
    }

    # ---- R-L0-001 evidence header: block ------------------------------------
    if (Gate-On 'evidence') {
        $g1 = $script:Cfg.gates.evidence
        $firstLine = ''
        if ($msg) {
            foreach ($ln in ($msg -split "`r?`n")) {
                if (-not [string]::IsNullOrWhiteSpace($ln)) { $firstLine = $ln.Trim(); break }
            }
        }

        $empty = [string]::IsNullOrWhiteSpace($firstLine)
        $ok = $false
        foreach ($rx in $g1.first_line_must_match) {
            if ($firstLine -match [string]$rx) { $ok = $true; break }
        }
        if ($empty -and $g1.allow_empty) { $ok = $true }

        if ($ok) {
            if ($state.ContainsKey('evidence_blocks') -and [int]$state['evidence_blocks'] -gt 0) {
                $state['evidence_blocks'] = 0
                Save-State $sid $state
            }
        } else {
            $n = 0
            if ($state.ContainsKey('evidence_blocks')) { $n = [int]$state['evidence_blocks'] }
            $n = $n + 1

            if ($n -gt [int]$g1.max_consecutive_blocks) {
                # Loop breaker. Releasing is itself an event that must be visible:
                # an unseen release is indistinguishable from a rule that held.
                $state['evidence_blocks'] = 0
                Save-State $sid $state
                Write-Trace @{
                    rule       = [string]$g1.rule_id
                    gate       = 'evidence'
                    action     = 'released'
                    session    = $sid
                    count      = $n
                    first_line = $firstLine
                }
                $notices += (Fill $g1.release_notice @{ count = $n })
            } else {
                $state['evidence_blocks'] = $n
                Save-State $sid $state
                Write-Trace @{
                    rule       = [string]$g1.rule_id
                    gate       = 'evidence'
                    action     = 'block'
                    session    = $sid
                    count      = $n
                    first_line = $firstLine
                }
                $reason = [string]$g1.block_reason
                if ($notices.Count -gt 0) { $reason = $reason + "`n`n" + ($notices -join "`n") }
                Emit-Json @{ decision = 'block'; reason = $reason }
                exit 0
            }
        }
    }

    if ($notices.Count -gt 0) { Emit-Json @{ systemMessage = ($notices -join "`n") } }
    exit 0
}

# ============================================================= PreToolUse ====

if ($evtName -eq 'PreToolUse') {
    $tool = [string]$payload.tool_name
    $state = Read-State $sid

    # ---- R-L0-003 core source must sit on a rollback point ------------------
    if (Gate-On 'rollback') {
        $g3 = $script:Cfg.gates.rollback
        if ($g3.match_tools -contains $tool) {
            $target = [string]$payload.tool_input.file_path
            if (-not $target) { $target = [string]$payload.tool_input.notebook_path }
            if ($target) {
                $lower = $target.ToLower()
                $protected = $false
                foreach ($kw in $g3.protected_keywords) {
                    if ($lower.Contains(([string]$kw).ToLower())) { $protected = $true; break }
                }
                if ($protected) {
                    # Walk up to the first directory that actually exists: the file
                    # itself is usually about to be created, and `git -C <missing dir>`
                    # fails for the wrong reason.
                    $dir = Split-Path -Parent $target
                    $guard = 0
                    while ($dir -and -not (Test-Path -LiteralPath $dir -PathType Container) -and $guard -lt 40) {
                        $parent = Split-Path -Parent $dir
                        if ($parent -eq $dir) { break }
                        $dir = $parent
                        $guard = $guard + 1
                    }

                    # "git is missing" and "git says this is not a repo" are two
                    # different findings and must not share a branch.
                    $gitCmd = $null
                    try { $gitCmd = Get-Command git -ErrorAction SilentlyContinue } catch { }
                    if (-not $gitCmd) {
                        Emit-Json @{ systemMessage = "[L0 R-L0-003] git executable not found - rollback check skipped for: $target" }
                        exit 0
                    }

                    # !! $ErrorActionPreference='Stop' turns a native command's stderr
                    #    into a terminating error in PowerShell 5.1. git writes to
                    #    stderr whenever the path is not a repo -- i.e. exactly the
                    #    case this gate exists to catch. Left as-is, the gate reported
                    #    "git not runnable" and passed, so the one scenario it was
                    #    built for was the one scenario it never caught, while blaming
                    #    a healthy git. Drop to Continue around the call.
                    $prevEap = $ErrorActionPreference
                    $ErrorActionPreference = 'Continue'
                    $top = ''
                    try { $top = (& git -C "$dir" rev-parse --show-toplevel 2>$null | Out-String).Trim() } catch { }
                    $code = $LASTEXITCODE
                    $ErrorActionPreference = $prevEap

                    # Direct evidence (a toplevel path came back) rather than exit code alone.
                    $hasRepo = ($code -eq 0 -and -not [string]::IsNullOrWhiteSpace($top))
                    if (-not $hasRepo) {
                        Write-Trace @{
                            rule    = [string]$g3.rule_id
                            gate    = 'rollback'
                            action  = 'deny'
                            session = $sid
                            tool    = $tool
                            path    = $target
                        }
                        Emit-Json @{
                            hookSpecificOutput = @{
                                hookEventName            = 'PreToolUse'
                                permissionDecision       = 'deny'
                                permissionDecisionReason = (Fill $g3.block_reason @{ path = $target })
                            }
                        }
                        exit 0
                    }
                }
            }
        }
    }

    # ---- R-L0-004 irreversible commands -------------------------------------
    if (Gate-On 'danger') {
        $g4 = $script:Cfg.gates.danger
        if ($g4.match_tools -contains $tool) {
            $cmd = [string]$payload.tool_input.command
            if ($cmd) {
                $hitPattern = $null
                foreach ($rx in $g4.danger_patterns) {
                    try {
                        if ([Text.RegularExpressions.Regex]::IsMatch(
                                $cmd, [string]$rx,
                                [Text.RegularExpressions.RegexOptions]::IgnoreCase)) {
                            $hitPattern = [string]$rx; break
                        }
                    } catch { }
                }
                if ($hitPattern) {
                    $h = Hash-Text $cmd
                    $seen = @()
                    if ($state.ContainsKey('danger_seen') -and $state['danger_seen']) { $seen = @($state['danger_seen']) }

                    if ($g4.second_try_passes -and ($seen -contains $h)) {
                        # Confirmed re-issue. Passing is also an event worth recording:
                        # "blocked once, then executed" is the interesting row in traces.
                        Write-Trace @{
                            rule    = [string]$g4.rule_id
                            gate    = 'danger'
                            action  = 'pass_on_retry'
                            session = $sid
                            tool    = $tool
                            command = $cmd
                            pattern = $hitPattern
                        }
                        exit 0
                    }

                    $seen += $h
                    $state['danger_seen'] = $seen
                    Save-State $sid $state
                    Write-Trace @{
                        rule    = [string]$g4.rule_id
                        gate    = 'danger'
                        action  = 'deny'
                        session = $sid
                        tool    = $tool
                        command = $cmd
                        pattern = $hitPattern
                    }
                    Emit-Json @{
                        hookSpecificOutput = @{
                            hookEventName            = 'PreToolUse'
                            permissionDecision       = 'deny'
                            permissionDecisionReason = (Fill $g4.block_reason @{ command = $cmd; pattern = $hitPattern })
                        }
                    }
                    exit 0
                }
            }
        }
    }

    exit 0
}

exit 0
