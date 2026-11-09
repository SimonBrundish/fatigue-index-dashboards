#!/bin/bash
# One command for the weekly dashboards. Runs detached under caffeinate, so a
# parked session or a sleeping Mac can't kill it, and only one can run at a time.
#   ./update_all.sh              # full update, then publish whatever passes the checks
#   ./update_all.sh --no-push    # the same, but stop before GitHub (dry run)
#   ./update_all.sh --scheduled  # 05:40 job: only if a PL club played yesterday
#   ./update_all.sh --up-only    # after writing the sheet: just Under Pressure, checks, push
# Report: logs/update_YYYYMMDD.md (last 30 kept).
#
# Scrapes come first because Perf Desk needs FotMob's running data, and Under
# Pressure is last because it reads the Fatigue Index it reports on.
set -uo pipefail

LA="/Users/simon/Documents/LiverpoolAnalysis"
REPO="/Users/simon/Documents/fatigue-index-dashboards"
LOGS="$LA/logs"
LOCK="$LA/.update_all.lock"
PY="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
export PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/Users/simon/bin"
export GIT_TERMINAL_PROMPT=0

mkdir -p "$LOGS"
if [ -z "${LFC_UPDATE_DETACHED:-}" ]; then
  LFC_UPDATE_DETACHED=1 nohup /usr/bin/caffeinate -dimsu "$0" "$@" </dev/null >>"$LOGS/update_all.out" 2>&1 &
  echo "update started detached, pid $! (report: $LOGS/update_$(date +%Y%m%d).md)"
  exit 0
fi

PUSH=1 SCHEDULED=0 UP_ONLY=0
for a in "$@"; do
  case "$a" in
    --no-push) PUSH=0 ;;
    --scheduled) SCHEDULED=1 ;;
    --up-only) UP_ONLY=1 ;;
    *) echo "unknown option $a"; exit 2 ;;
  esac
done

# one-shot dry run through the real scheduled path (the launchd job)
if [ -f "$LOGS/.no_push_once" ]; then PUSH=0; rm -f "$LOGS/.no_push_once"; fi

if ! ( set -C; echo $$ >"$LOCK" ) 2>/dev/null; then
  if kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
    echo "$(date '+%F %T') another update is running (pid $(cat "$LOCK")), exiting"
    exit 0
  fi
  echo $$ >"$LOCK"           # left behind by a run that died
fi
trap 'rm -f "$LOCK"' EXIT

DAY=$(date +%Y%m%d)
LOG="$LOGS/update_$DAY.log"
REPORT="$LOGS/update_$DAY.md"
STEPS=()
ANY_FAILED=0
ts() { date '+%H:%M:%S'; }
say() { echo "[$(ts)] $*" | tee -a "$LOG"; }

# step "name" command...: a failed step is recorded and the run goes on, since
# the checks decide what is safe to publish
step() {
  local name="$1"; shift
  local t0=$SECONDS
  say "START $name"
  if "$@" >>"$LOG" 2>&1; then
    STEPS+=("| $name | OK | $(( (SECONDS - t0) / 60 )) min |")
    say "OK    $name"
  else
    local rc=$?
    STEPS+=("| $name | FAILED (exit $rc) | $(( (SECONDS - t0) / 60 )) min |")
    ANY_FAILED=1
    say "FAIL  $name (exit $rc)"
  fi
}

notify() { /usr/bin/osascript -e "display notification \"$1\" with title \"LFC dashboards\"" >/dev/null 2>&1 || true; }

sync_repo() {
  git -C "$REPO" pull -q --ff-only origin main && cp "$REPO/up_running_weekly.py" "$LA/up_pod/up_running_weekly.py"
}

barts() {
  local tmp; tmp=$(mktemp -d "${TMPDIR:-/tmp}/barts.XXXXXX")
  if git clone -q --depth 1 https://github.com/barts78/DrBarts2627.git "$tmp/repo"; then
    ( cd "$LA/up_pod" && BARTS_LOCAL="$tmp/repo" "$PY" -W ignore fetch_barts_matches.py --local "$tmp/repo" ) || { rm -rf "$tmp"; return 1; }
  else
    ( cd "$LA/up_pod" && "$PY" -W ignore fetch_barts_matches.py ) || { rm -rf "$tmp"; return 1; }
  fi
  rm -rf "$tmp"
}

cd "$LA" || exit 1
say "===== update_all start ($*) ====="

if [ "$SCHEDULED" = 1 ] && ! "$PY" "$LA/fatigue/games_yesterday.py" >>"$LOG" 2>&1; then
  say "no PL-club games yesterday, nothing to do"
  printf '# Dashboard update %s\n\nSkipped: no Premier League club played yesterday.\n' "$(date '+%A %-d %B %Y')" >"$REPORT"
  exit 0
fi

step "Sync repo + up_running_weekly.py" sync_repo
if [ "$UP_ONLY" = 0 ]; then
  step "Scrapes (FBref minutes, FotMob, injuries)" env FI_SCRAPE_ONLY=1 "$LA/fatigue/refresh_fatigue_index.sh"
  step "Perf Desk" bash -c "cd '$LA/fotmob_physical' && '$PY' -W ignore build_perf_desk.py"
  step "HQC" "$LA/understat_bulk/nightly_update.sh"
  step "Barts' match pages" barts
  step "Fatigue Index rebuild" env FI_BUILD_ONLY=1 "$LA/fatigue/refresh_fatigue_index.sh"
fi
step "Under Pressure pipeline" bash -c "cd '$LA/up_pod' && '$PY' -W ignore pipeline.py"
step "Sheet to-do list" bash -c "cd '$LA/up_pod' && '$PY' -W ignore sheet_plan.py"
step "Checks" "$PY" "$LA/update_checks.py"

# publish only what passed; anything held keeps its last good version on GitHub
PASSED=$("$PY" -c "
import json; d=json.load(open('$LOGS/checks.json'))['dashboards']
print(' '.join(k for k,v in d.items() if v['ok']))" 2>/dev/null)
PUSHED="not attempted"
if [ "$PUSH" = 1 ] && [ -n "$PASSED" ]; then
  # shellcheck disable=SC2086
  step "Push to GitHub ($PASSED)" "$REPO/push_to_github.sh" $PASSED
  PUSHED="$(git -C "$REPO" log -1 --format='%h %s')"
elif [ "$PUSH" = 0 ]; then
  PUSHED="skipped (--no-push)"
fi

"$PY" - "$REPORT" "$LOG" "$PUSHED" "$PUSH" "${STEPS[@]}" <<'PY' >>"$LOG" 2>&1
import datetime as dt, json, re, sys
from pathlib import Path
report, log, pushed, push, *steps = sys.argv[1:]
LA = Path("/Users/simon/Documents/LiverpoolAnalysis")
c = json.loads((LA / "logs/checks.json").read_text())
names = dict(hqc="HQC", pd="Perf Desk", fi="Fatigue Index", up="Under Pressure")
out = [f"# Dashboard update {dt.date.today():%A %-d %B %Y}", "", f"Latest Liverpool game: {c['latest']}", "",
       "| Step | Result | Time |", "|---|---|---|", *steps, "", "## What's live", ""]
for k, v in c["dashboards"].items():
    state = "Passed" if v["ok"] else "**HELD, last good version stays live**"
    out.append(f"- {names[k]}: {state}" + ("" if v["ok"] else ": " + "; ".join(v["fails"])))
out += ["", f"GitHub: {pushed}", ""]
if c["warns"]:
    out += ["## Warnings", ""] + [f"- {w}" for w in c["warns"]] + [""]
scrape = [l.split("WARN:", 1)[1].strip() for l in Path(log).read_text(errors="ignore").splitlines() if "WARN:" in l]
fi_log = (LA / "fatigue/refresh_fatigue_index.log").read_text(errors="ignore")
today = dt.date.today().isoformat()
fi_warn = [l.split("WARN:", 1)[1].strip() for l in fi_log.splitlines() if l.startswith(f"[{today}") and "WARN:" in l]
if scrape or fi_warn:
    out += ["## Scraper warnings", ""] + [f"- {w}" for w in dict.fromkeys(scrape + fi_warn)] + [""]
t = json.loads((LA / "logs/sheet_todo.json").read_text()) if (LA / "logs/sheet_todo.json").exists() else {}
if t.get("missing_tabs") or t.get("fi_tab_empty"):
    out += ["## Needs the sheet (a Claude session, Sheets connector)", ""]
    out += [f"- New match tab: {m['tab']} ({m['date']})" for m in t.get("missing_tabs", [])]
    out += [f"- Fatigue Index tab, empty game column: {f['tab']} ({f['range']})" for f in t.get("fi_tab_empty", [])]
    out += ["", "Then run `update_all.sh --up-only`.", ""]
Path(report).write_text("\n".join(out))
PY

# last_good only moves when the Fatigue Index passed and went out
if [ "$PUSH" = 1 ] && [[ " $PASSED " == *" fi "* ]]; then
  "$PY" -c "
import json; c=json.load(open('$LOGS/checks.json'))
json.dump(dict(fi_players=c['fi_players']),open('$LOGS/last_good.json','w'))"
fi

HELD=$("$PY" -c "
import json; d=json.load(open('$LOGS/checks.json'))['dashboards']
print(', '.join(k for k,v in d.items() if not v['ok']))" 2>/dev/null)
if [ "$ANY_FAILED" = 1 ] || [ -n "$HELD" ]; then
  notify "Update needs a look${HELD:+: held $HELD}. See logs/update_$DAY.md"
fi

# keep the last 30 reports and raw logs
for pat in 'update_[0-9]*.md' 'update_[0-9]*.log'; do
  # shellcheck disable=SC2086
  ls -1t "$LOGS"/$pat 2>/dev/null | tail -n +31 | while read -r f; do rm -f "$f"; done
done
say "===== update_all done ====="
