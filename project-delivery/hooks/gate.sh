#!/usr/bin/env bash
# gate.sh - L0 enforcement gate for Claude Code hooks (macOS / Linux).
#
# Mirrors gate.ps1. The IMPLEMENTATION is duplicated because PowerShell and sh
# are two languages; the JUDGEMENT is not -- every pattern, threshold and piece
# of human-facing text is read from config.json, which both sides share.
# If you find yourself adding a rule here that is not in config.json, stop:
# that is the moment the two platforms start disagreeing.
#
# STATUS: NOT YET TESTED ON A REAL POSIX MACHINE. Written and reviewed on
# Windows. Untested is untested -- do not present this file as verified.
#
# FAIL-OPEN, LOUDLY: if this gate breaks it must not stop the user from working,
# but it must never fail silently either.

set -u

# Which agent tool is calling. The JUDGEMENT is host-independent; only input
# field names and the block-output shape differ, and both live in config.json
# under "hosts"/"outputs". Adding a host = editing that JSON, not this script.
L0_HOST="claude"
L0_EVENT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --host)  L0_HOST="${2:-claude}"; shift 2 ;;
    --event) L0_EVENT="${2:-}";      shift 2 ;;
    *) shift ;;
  esac
done

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="$HOOK_DIR/config.json"

emit() { printf '%s\n' "$1"; }

# JSON string -> JSON-escaped string (quotes included).
# Uses whichever reader survived the probe below; the sed fallback is last resort
# and lossy (newlines collapse), so it must never be the silent default.
json_escape() {
  if [ "${JSON_TOOL:-}" = "jq" ]; then
    printf '%s' "$1" | jq -Rs .
  elif [ -n "${JSON_TOOL:-}" ]; then
    printf '%s' "$1" | "$JSON_TOOL" -c \
      'import json,sys; sys.stdout.write(json.dumps(sys.stdin.read(), ensure_ascii=False))'
  else
    printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ')"
  fi
}

RAW="$(cat)"
[ -z "${RAW// }" ] && exit 0

# --- pick a JSON reader -------------------------------------------------------
# jq first, then python3/python. Neither is *required* to be installed by the
# user; we use whatever is already on the machine. If none works the gate cannot
# run, and that must be said out loud rather than swallowed.
#
# !! `command -v` is NOT proof that a tool runs. On Windows, `command -v python3`
#    resolves to the Microsoft Store stub in WindowsApps: it exists, it is
#    executable, and it does nothing useful. Trusting the lookup made every
#    config read return empty, so master_switch read as "" (gate off), the
#    evidence pattern read as "" (nothing matches -> everything blocked), and
#    the reason text came out as mojibake. Three different symptoms, one cause.
#    So: actually run each candidate on a known input and check the answer.
JSON_TOOL=""
if command -v jq >/dev/null 2>&1 && [ "$(printf '{"a":"ok"}' | jq -r '.a' 2>/dev/null)" = "ok" ]; then
  JSON_TOOL="jq"
else
  for _py in python3 python py; do
    command -v "$_py" >/dev/null 2>&1 || continue
    if [ "$(printf '{"a":"ok"}' | PYTHONIOENCODING=utf-8 "$_py" -c \
            'import json,sys; sys.stdout.write(json.load(sys.stdin)["a"])' 2>/dev/null)" = "ok" ]; then
      JSON_TOOL="$_py"
      break
    fi
  done
fi
if [ -z "$JSON_TOOL" ]; then
  emit '{"systemMessage":"[L0] no working jq/python found - ALL GATES ARE OFF on this machine."}'
  exit 0
fi
# Python on Windows defaults stdout to the ANSI codepage; force UTF-8 everywhere
# so Chinese text survives the round trip.
export PYTHONIOENCODING=utf-8

# q <json-text> <path>   -> raw value ("" when absent)
# !! Every reader here writes bytes, never print().
#    On Windows, Python's text-mode stdout turns "\n" into "\r\n", so each value
#    came back with a trailing CR. Symptoms looked unrelated: tool matching
#    compared "Bash\r" against "Bash" (danger gate never fired) and the regex
#    became "^<evidence-header>\r" (evidence gate blocked every valid reply). One cause,
#    two opposite failures -- and invisible until `cat -A`.
#    The trailing `tr -d '\r'` is belt-and-braces for other readers.
q() {
  if [ "$JSON_TOOL" = "jq" ]; then
    printf '%s' "$1" | jq -r "$2 // empty" 2>/dev/null | tr -d '\r'
  else
    printf '%s' "$1" | JQPATH="$2" "$JSON_TOOL" -c '
import json,os,sys
try: d=json.load(sys.stdin)
except Exception: sys.exit(0)
p=os.environ["JQPATH"].lstrip(".")
cur=d
for part in [x for x in p.split(".") if x]:
    if isinstance(cur,dict) and part in cur: cur=cur[part]
    else: sys.exit(0)
if cur is None: sys.exit(0)
if isinstance(cur,bool): out="true" if cur else "false"
elif isinstance(cur,(list,dict)): out=json.dumps(cur,ensure_ascii=False)
else: out=str(cur)
sys.stdout.buffer.write(out.encode("utf-8"))
' 2>/dev/null | tr -d '\r'
  fi
}

# qa <json-text> <path>  -> array elements, one per line
qa() {
  if [ "$JSON_TOOL" = "jq" ]; then
    printf '%s' "$1" | jq -r "$2[]? // empty" 2>/dev/null | tr -d '\r'
  else
    printf '%s' "$1" | JQPATH="$2" "$JSON_TOOL" -c '
import json,os,sys
try: d=json.load(sys.stdin)
except Exception: sys.exit(0)
p=os.environ["JQPATH"].lstrip(".")
cur=d
for part in [x for x in p.split(".") if x]:
    if isinstance(cur,dict) and part in cur: cur=cur[part]
    else: sys.exit(0)
if isinstance(cur,list):
    for x in cur: sys.stdout.buffer.write((str(x)+"\n").encode("utf-8"))
' 2>/dev/null | tr -d '\r'
  fi
}

[ -f "$CFG" ] || { emit '{"systemMessage":"[L0] hooks/config.json missing - ALL GATES ARE OFF."}'; exit 0; }
CFGTXT="$(cat "$CFG")"

[ "$(q "$CFGTXT" '.master_switch')" = "true" ] || {
  emit '{"systemMessage":"[L0] master_switch=false in hooks/config.json - all gates are OFF."}'
  exit 0
}

gate_on() { [ "$(q "$CFGTXT" ".gates.$1.enabled")" = "true" ]; }

# count_verify_tools <transcript_path> <tool1,tool2,...>
#   -> number of query-type tool calls since the last REAL human message.
#   -> -1 when it cannot be determined. -1 is NOT zero: zero means "checked,
#      it queried nothing"; -1 means "cannot tell", and the caller must fail
#      open and say so. A gate that silently reads "unknown" as "guilty"
#      gets disabled by its user within the day.
#
# A human turn is type=="user" whose message.content is a STRING. Tool results
# are also type=="user" but carry a content ARRAY -- confusing the two makes
# every turn start at the last tool result, so the count is always zero and the
# gate fires on every reply.
count_verify_tools() {
  local tp="$1" tools="$2" py=""
  [ -f "$tp" ] || { echo -1; return; }
  # This one needs real parsing; jq can do it but the boundary scan is far
  # easier to get right in python. If neither python is present we say -1
  # rather than guessing.
  for c in python3 python py; do
    if command -v "$c" >/dev/null 2>&1 && printf '{"a":1}' | "$c" -c 'import json,sys;json.load(sys.stdin)' >/dev/null 2>&1; then
      py="$c"; break
    fi
  done
  [ -n "$py" ] || { echo -1; return; }
  TOOLS="$tools" "$py" - "$tp" <<'PYEOF' 2>/dev/null || echo -1
import json, os, sys
tools = set(os.environ.get("TOOLS", "").split(","))
try:
    rows = []
    with open(sys.argv[1], encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except ValueError:
                pass
except OSError:
    print(-1); raise SystemExit(0)
start = 0
for i in range(len(rows) - 1, -1, -1):
    r = rows[i]
    if r.get("type") == "user" and isinstance(r.get("message", {}).get("content"), str) \
            and r["message"]["content"].strip():
        start = i
        break
n = 0
for r in rows[start:]:
    if r.get("type") != "assistant":
        continue
    for blk in (r.get("message", {}).get("content") or []):
        if isinstance(blk, dict) and blk.get("type") == "tool_use" and blk.get("name") in tools:
            n += 1
print(n)
PYEOF
}

# ---- host adapter ------------------------------------------------------------
HOSTQ=".hosts.$L0_HOST"
if [ -z "$(q "$CFGTXT" "$HOSTQ.name")" ]; then
  emit "{\"systemMessage\":$(json_escape "[L0] unknown host '$L0_HOST' - gates are OFF. Known hosts live in hooks/config.json.")}"
  exit 0
fi
OUTQ=".outputs.$(q "$CFGTXT" "$HOSTQ.output")"

RAW_EVT="$L0_EVENT"
[ -z "$RAW_EVT" ] && RAW_EVT="$(q "$RAW" ".$(q "$CFGTXT" "$HOSTQ.event_field")")"
# !! No quotes around the key: q() splits the path on dots and looks the segment
#    up verbatim, so `events."Stop"` would search for a key literally named
#    `"Stop"`, find nothing, and the script would exit silently on every event.
EVT="$(q "$CFGTXT" "$HOSTQ.events.$RAW_EVT")"
[ -z "$EVT" ] && exit 0        # event this host fires but L0 does not judge

# nf <logical-name> -> that value out of the host payload
nf() {
  local path
  path="$(q "$CFGTXT" "$HOSTQ.fields.$1")"
  [ -z "$path" ] && { printf ''; return; }
  q "$RAW" ".$path"
}

# emit_decision <block_stop|deny_tool|notice> <text>
# Falls back to exit 2 (understood by every host we know of) when a host has no
# template -- but JSON first: stderr goes through the console codepage and these
# reasons are Chinese.
emit_decision() {
  local tpl reason
  tpl="$(q "$CFGTXT" "$OUTQ.$1")"
  if [ -z "$tpl" ]; then
    printf '%s' "$2" >&2
    exit 2
  fi
  reason="$(json_escape "$2")"
  # !! Pure bash substitution -- do NOT pipe through "$JSON_TOOL" here.
  #    JSON_TOOL is jq on most machines and python only where jq is missing.
  #    The first version fed a python snippet to it unconditionally: on Windows
  #    Git Bash (no jq) it worked, so 60/60 passed locally, while on a real
  #    macOS runner jq got handed python source and every blocking assertion
  #    failed -- 9 red. Exactly the "Git Bash is not Linux" gap the CI exists for.
  printf '%s\n' "${tpl//%REASON%/$reason}"
}

SID="$(nf session)"
SID_SAFE="$(printf '%s' "${SID:-nosession}" | tr -c 'A-Za-z0-9_-' '_')"

TDIR="$HOOK_DIR/$(q "$CFGTXT" '.traces.dir')"
SDIR="$TDIR/.state"
mkdir -p "$SDIR" 2>/dev/null || true

trace() {
  [ "$(q "$CFGTXT" '.traces.enabled')" = "true" ] || return 0
  printf '%s\n' "$1" >> "$TDIR/$(date +%Y-%m-%d).jsonl" 2>/dev/null || true
}

state_get() { # state_get <key>  (integer/string, "" when absent)
  local f="$SDIR/$SID_SAFE.$1"
  [ -f "$f" ] && cat "$f" || printf ''
}
state_set() { printf '%s' "$2" > "$SDIR/$SID_SAFE.$1" 2>/dev/null || true; }

fill() { # fill <template> <token> <value>
  printf '%s' "$1" | sed "s|{$2}|$(printf '%s' "$3" | sed 's/[&|\\]/\\&/g')|g"
}

# ========================================================== SessionStart =====
if [ "$EVT" = "session_start" ]; then
  # Housekeeping, once per new window. retain_days used to sit in config.json
  # with nothing reading it -- a config key that does nothing reads as "someone
  # is managing this", which is worse than having no key. .state is the one that
  # actually piles up: one file per session, forever, somewhere nobody looks.
  PRUNED_T=0; PRUNED_S=0
  KEEP="$(q "$CFGTXT" '.traces.retain_days')"
  KEEP_S="$(q "$CFGTXT" '.traces.state_retain_days')"
  if [ -n "$KEEP" ] && [ "$KEEP" -gt 0 ] 2>/dev/null && [ -d "$TDIR" ]; then
    while IFS= read -r f; do
      [ -n "$f" ] && rm -f "$f" && PRUNED_T=$((PRUNED_T + 1))
    done <<< "$(find "$TDIR" -maxdepth 1 -name '*.jsonl' -type f -mtime +"$KEEP" 2>/dev/null)"
  fi
  if [ -n "$KEEP_S" ] && [ "$KEEP_S" -gt 0 ] 2>/dev/null && [ -d "$SDIR" ]; then
    while IFS= read -r f; do
      [ -n "$f" ] && rm -f "$f" && PRUNED_S=$((PRUNED_S + 1))
    done <<< "$(find "$SDIR" -maxdepth 1 -type f -mtime +"$KEEP_S" 2>/dev/null)"
  fi
  if [ "$PRUNED_T" -gt 0 ] || [ "$PRUNED_S" -gt 0 ]; then
    trace "{\"rule\":\"L0-PRUNE\",\"gate\":\"housekeeping\",\"action\":\"prune\",\"traces_removed\":$PRUNED_T,\"state_removed\":$PRUNED_S,\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
  fi
  gate_on session_start || exit 0
  SKILLS="$(cd "$HOOK_DIR/../.." && pwd)"
  TXT="$(q "$CFGTXT" '.gates.session_start.inject')"
  ACTIVE=""
  for g in evidence redline rollback danger session_start; do
    if gate_on "$g"; then ACTIVE="$ACTIVE$(q "$CFGTXT" ".gates.$g.rule_id") $g | "; fi
  done
  TXT="$(fill "$TXT" map    "$SKILLS/$(q "$CFGTXT" '.paths.map')")"
  TXT="$(fill "$TXT" core   "$SKILLS/$(q "$CFGTXT" '.paths.core')")"
  TXT="$(fill "$TXT" readme "$HOOK_DIR/README.md")"
  TXT="$(fill "$TXT" active "${ACTIVE% | }")"
  # This gate never blocks, so it can never produce a block/deny row. Without its
  # own record it reads as "never fired" in the ledger -- the same signal that
  # means "or it was never wired". Record the injection.
  trace "{\"rule\":$(json_escape "$(q "$CFGTXT" '.gates.session_start.rule_id')"),\"gate\":\"session_start\",\"action\":\"inject\",\"session\":$(json_escape "$SID"),\"host\":$(json_escape "$L0_HOST"),\"startup\":$(json_escape "$(nf startup)"),\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
  printf '%b\n' "$TXT"
  exit 0
fi

# ================================================================= Stop ======
if [ "$EVT" = "stop" ]; then
  MSG="$(nf assistant_text)"
  NOTICES=""

  # ---- R-L0-002 redline phrases: record and warn, never block ---------------
  if gate_on redline; then
    HITS=""
    while IFS= read -r p; do
      [ -z "$p" ] && continue
      case "$MSG" in *"$p"*) HITS="$HITS$p / " ;; esac
    done <<< "$(qa "$CFGTXT" '.gates.redline.phrases')"
    if [ -n "$HITS" ]; then
      HITS="${HITS% / }"
      trace "{\"rule\":$(json_escape "$(q "$CFGTXT" '.gates.redline.rule_id')"),\"gate\":\"redline\",\"action\":\"warn\",\"session\":$(json_escape "$SID"),\"hits\":$(json_escape "$HITS"),\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
      NOTICES="$(fill "$(q "$CFGTXT" '.gates.redline.notice')" hits "$HITS")"
    fi
  fi

  # ---- R-L0-006 claiming something is live without verifying it -------------
  # Pit S3: six occurrences, the most-bitten entry in the library.
  if gate_on claim; then
    CHITS=""
    while IFS= read -r p; do
      [ -z "$p" ] && continue
      case "$MSG" in *"$p"*) CHITS="$CHITS$p / " ;; esac
    done <<< "$(qa "$CFGTXT" '.gates.claim.claim_phrases')"
    if [ -n "$CHITS" ]; then
      CHITS="${CHITS% / }"
      VT="$(qa "$CFGTXT" '.gates.claim.verify_tools' | tr '\n' ',' | sed 's/,$//')"
      NV="$(count_verify_tools "$(nf transcript)" "$VT")"
      RID6="$(q "$CFGTXT" '.gates.claim.rule_id')"
      if [ "$NV" -lt 0 ] 2>/dev/null; then
        NOTICES="$NOTICES
$(q "$CFGTXT" '.gates.claim.transcript_unreadable_notice')"
      elif [ "$NV" -eq 0 ] 2>/dev/null; then
        CN="$(state_get claim_blocks)"; CN="${CN:-0}"; CN=$((CN + 1))
        MAXC="$(q "$CFGTXT" '.gates.claim.max_consecutive_blocks')"; MAXC="${MAXC:-2}"
        if [ "$CN" -gt "$MAXC" ]; then
          state_set claim_blocks 0
          trace "{\"rule\":$(json_escape "$RID6"),\"gate\":\"claim\",\"action\":\"released\",\"session\":$(json_escape "$SID"),\"count\":$CN,\"hits\":$(json_escape "$CHITS"),\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
          NOTICES="$NOTICES
$(fill "$(q "$CFGTXT" '.gates.claim.release_notice')" count "$CN")"
        else
          state_set claim_blocks "$CN"
          trace "{\"rule\":$(json_escape "$RID6"),\"gate\":\"claim\",\"action\":\"block\",\"session\":$(json_escape "$SID"),\"count\":$CN,\"hits\":$(json_escape "$CHITS"),\"verify_tools\":0,\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
          emit_decision block_stop "$(fill "$(q "$CFGTXT" '.gates.claim.block_reason')" hits "$CHITS")"
          exit 0
        fi
      else
        state_set claim_blocks 0
      fi
    fi
  fi

  # ---- R-L0-001 evidence header: block --------------------------------------
  if gate_on evidence; then
    FIRST="$(printf '%s' "$MSG" | sed -n '/[^[:space:]]/{p;q;}' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    OK=0
    [ -z "$FIRST" ] && [ "$(q "$CFGTXT" '.gates.evidence.allow_empty')" = "true" ] && OK=1
    if [ $OK -eq 0 ]; then
      while IFS= read -r rx; do
        [ -z "$rx" ] && continue
        if printf '%s' "$FIRST" | grep -qE "$rx"; then OK=1; break; fi
      done <<< "$(qa "$CFGTXT" '.gates.evidence.first_line_must_match')"
    fi

    if [ $OK -eq 1 ]; then
      state_set evidence_blocks 0
    else
      N="$(state_get evidence_blocks)"; N="${N:-0}"; N=$((N + 1))
      MAXB="$(q "$CFGTXT" '.gates.evidence.max_consecutive_blocks')"; MAXB="${MAXB:-2}"
      RID="$(q "$CFGTXT" '.gates.evidence.rule_id')"
      if [ "$N" -gt "$MAXB" ]; then
        # Loop breaker. Releasing must be visible: an unseen release is
        # indistinguishable from a rule that held.
        state_set evidence_blocks 0
        trace "{\"rule\":$(json_escape "$RID"),\"gate\":\"evidence\",\"action\":\"released\",\"session\":$(json_escape "$SID"),\"count\":$N,\"first_line\":$(json_escape "$FIRST"),\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
        NOTICES="$NOTICES
$(fill "$(q "$CFGTXT" '.gates.evidence.release_notice')" count "$N")"
      else
        state_set evidence_blocks "$N"
        trace "{\"rule\":$(json_escape "$RID"),\"gate\":\"evidence\",\"action\":\"block\",\"session\":$(json_escape "$SID"),\"count\":$N,\"first_line\":$(json_escape "$FIRST"),\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
        REASON="$(q "$CFGTXT" '.gates.evidence.block_reason')"
        [ -n "$NOTICES" ] && REASON="$REASON

$NOTICES"
        emit_decision block_stop "$REASON"
        exit 0
      fi
    fi
  fi

  if [ -n "${NOTICES// }" ]; then
    emit_decision notice "$NOTICES"
  fi
  exit 0
fi

# ============================================================ PreToolUse =====
if [ "$EVT" = "pre_tool" ]; then
  TOOL="$(nf tool_name)"

  # ---- R-L0-003 core source must sit on a rollback point --------------------
  if gate_on rollback; then
    MATCH=0
    while IFS= read -r t; do [ "$t" = "$TOOL" ] && MATCH=1; done <<< "$(qa "$CFGTXT" '.gates.rollback.match_tools')"
    # Some hosts fire a file-specific event with no tool name (Cursor). Judge on
    # what the payload actually carries rather than requiring a tool name --
    # otherwise the gate silently stops firing on that host.
    [ -z "$TOOL" ] && [ -n "$(nf file_path)" ] && MATCH=1
    if [ $MATCH -eq 1 ]; then
      TARGET="$(nf file_path)"
      [ -z "$TARGET" ] && TARGET="$(nf notebook_path)"
      if [ -n "$TARGET" ]; then
        LOWER="$(printf '%s' "$TARGET" | tr '[:upper:]' '[:lower:]')"
        PROT=0
        while IFS= read -r kw; do
          [ -z "$kw" ] && continue
          KWL="$(printf '%s' "$kw" | tr '[:upper:]' '[:lower:]')"
          case "$LOWER" in *"$KWL"*) PROT=1; break ;; esac
        done <<< "$(qa "$CFGTXT" '.gates.rollback.protected_keywords')"

        if [ $PROT -eq 1 ]; then
          # Walk up to the first directory that exists: the file is usually
          # about to be created, and git -C <missing dir> fails for the wrong reason.
          DIR="$(dirname "$TARGET")"
          GUARD=0
          while [ ! -d "$DIR" ] && [ "$DIR" != "/" ] && [ "$DIR" != "." ] && [ $GUARD -lt 40 ]; do
            DIR="$(dirname "$DIR")"; GUARD=$((GUARD + 1))
          done
          # "git is missing" and "git says not a repo" are different findings.
          if ! command -v git >/dev/null 2>&1; then
            emit_decision notice "[L0 R-L0-003] git executable not found - rollback check skipped."
            exit 0
          fi
          TOP="$(git -C "$DIR" rev-parse --show-toplevel 2>/dev/null || true)"
          if [ -z "${TOP// }" ]; then
            RID="$(q "$CFGTXT" '.gates.rollback.rule_id')"
            trace "{\"rule\":$(json_escape "$RID"),\"gate\":\"rollback\",\"action\":\"deny\",\"session\":$(json_escape "$SID"),\"tool\":$(json_escape "$TOOL"),\"path\":$(json_escape "$TARGET"),\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
            emit_decision deny_tool "$(fill "$(q "$CFGTXT" '.gates.rollback.block_reason')" path "$TARGET")"
            exit 0
          fi
        fi
      fi
    fi
  fi

  # ---- R-L0-004 irreversible commands ---------------------------------------
  if gate_on danger; then
    MATCH=0
    while IFS= read -r t; do [ "$t" = "$TOOL" ] && MATCH=1; done <<< "$(qa "$CFGTXT" '.gates.danger.match_tools')"
    # Same as above: judge the command when the host gives one but no tool name.
    [ -z "$TOOL" ] && [ -n "$(nf command)" ] && MATCH=1
    if [ $MATCH -eq 1 ]; then
      CMD="$(nf command)"
      if [ -n "$CMD" ]; then
        HITRX=""
        while IFS= read -r rx; do
          [ -z "$rx" ] && continue
          if printf '%s' "$CMD" | grep -qiE "$rx"; then HITRX="$rx"; break; fi
        done <<< "$(qa "$CFGTXT" '.gates.danger.danger_patterns')"
        if [ -n "$HITRX" ]; then
          H="$(printf '%s' "$CMD" | cksum | tr -d ' ' )"
          RID="$(q "$CFGTXT" '.gates.danger.rule_id')"
          SEENF="$SDIR/$SID_SAFE.danger_$H"
          if [ "$(q "$CFGTXT" '.gates.danger.second_try_passes')" = "true" ] && [ -f "$SEENF" ]; then
            trace "{\"rule\":$(json_escape "$RID"),\"gate\":\"danger\",\"action\":\"pass_on_retry\",\"session\":$(json_escape "$SID"),\"tool\":$(json_escape "$TOOL"),\"command\":$(json_escape "$CMD"),\"pattern\":$(json_escape "$HITRX"),\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
            exit 0
          fi
          : > "$SEENF" 2>/dev/null || true
          trace "{\"rule\":$(json_escape "$RID"),\"gate\":\"danger\",\"action\":\"deny\",\"session\":$(json_escape "$SID"),\"tool\":$(json_escape "$TOOL"),\"command\":$(json_escape "$CMD"),\"pattern\":$(json_escape "$HITRX"),\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
          REASON="$(fill "$(q "$CFGTXT" '.gates.danger.block_reason')" command "$CMD")"
          REASON="$(fill "$REASON" pattern "$HITRX")"
          emit_decision deny_tool "$REASON"
          exit 0
        fi
      fi
    fi
  fi
  exit 0
fi

exit 0
