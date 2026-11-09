#!/usr/bin/env python3
"""Checks that decide what update_all.sh may publish. Each failure holds that
dashboard back (last good stays live); warnings are reported but don't block.
Writes logs/checks.json; exit code 0 unless the checks themselves crash.
Limits were set from the data on 9 Nov 2026 (tracked 60+ min max 13.2 km/90)."""
import collections, csv, html.parser, json, re, sys
from pathlib import Path

LA = Path(__file__).resolve().parent
LOGS = LA / "logs"
MAX_BYTES = 16 * 1024 * 1024      # Artifact per-file limit
KM90, HI90, SP90 = 14.5, 6000, 1500
PLAYED_MAX = 130
FI_SWING = 0.05

fails = collections.defaultdict(list)
warns = []
counts = {}
ids = dict(re.findall(r'"([A-Za-z\- ]+)": "([0-9a-f]{8})"', (LA / "up_pod/pipeline.py").read_text()))
name_of = {v: k for k, v in ids.items()}


def liverpool_games():
    """{date: {played names}} from FBref minutes, the truth for 'latest match'."""
    out = collections.defaultdict(set)
    for f in ("match_minutes", "cup_europe_minutes"):
        for r in csv.DictReader(open(LA / f"lfc_data/data/{f}.csv")):
            if r["team"] == "Liverpool":
                out[r["date"]].add(name_of.get(r["fbref_id"], r["fbref_id"]))
                try:
                    if float(r["min"]) > PLAYED_MAX:
                        fails["fi"].append(f"{r['player']} shows {r['min']} minutes on {r['date']} (over {PLAYED_MAX})")
                except (TypeError, ValueError):
                    pass
    return out


games = liverpool_games()
latest = max(games)


def script_json(page, sid):
    m = re.search(rf'<script[^>]*id="{sid}"[^>]*>(.*?)</script>', page, re.S)
    return json.loads(m.group(1))


class _H(html.parser.HTMLParser):
    pass


def check_file(key, path):
    try:
        size = path.stat().st_size
    except OSError:
        fails[key].append(f"{path.name} is missing")
        return False
    if size > MAX_BYTES:
        fails[key].append(f"{path.name} is {size / 1048576:.1f} MB (limit 16)")
    try:
        if path.suffix == ".json":
            json.loads(path.read_text())
        else:
            _H().feed(path.read_text())
    except Exception as e:                 # noqa: BLE001
        fails[key].append(f"{path.name} does not parse: {e}")
        return False
    return True


def check_hqc():
    p = LA / "dashboard.html"
    if not check_file("hqc", p):
        return
    t = p.read_text()
    g = script_json(t, "lfcdata")["games"]
    if latest not in {x["date"] for x in g}:
        fails["hqc"].append(f"latest Liverpool game ({latest}) is not in the HQC Liverpool view")
    d = script_json(t, "data")
    n = len(d.get("fotmob_games") or [])
    if n:
        warns.append(f"HQC: Understat is missing {n} league game(s), FotMob stands in on the 0.18 line")


def check_pd():
    p = LA / "perf_desk.html"
    if not check_file("pd", p):
        return
    last = max(d for d in games)
    pl = [r for r in csv.DictReader(open(LA / "fotmob_physical/data/physical_all_player.csv")) if r["team"] == "Liverpool"]
    latest_pl = max(r["date"][:10] for r in pl if r["comp"] == "PL")
    lfc_pl = sorted({r["date"] for r in csv.DictReader(open(LA / "lfc_data/data/match_minutes.csv")) if r["team"] == "Liverpool"})
    if lfc_pl and lfc_pl[-1] != latest_pl:
        fails["pd"].append(f"FotMob running data stops at {latest_pl}, Liverpool's last league game was {lfc_pl[-1]}")
    if last not in {r["date"][:10] for r in pl}:
        warns.append(f"Perf Desk: no FotMob running data for {last} (cups aren't tracked)")


def check_fi():
    slim = LA / "fatigue/slim"
    if not check_file("fi", slim / "fatigue-index.html"):
        return
    for f in sorted((slim / "fatigue-data").glob("*.json")):
        check_file("fi", f)
    d = json.loads((LA / "fatigue/data/fatigue_data.json").read_text())
    if latest not in {r["d"] for v in d["series"].values() for r in v}:
        fails["fi"].append(f"latest Liverpool game ({latest}) is not in the Fatigue Index series")
    bad = []
    for fid, rows in d["series"].items():
        for r in rows:
            m, km = r.get("m"), r.get("km")
            if not m or km is None or not (r.get("est") or m >= 60):
                continue
            k = km / m * 90
            hi = (r.get("hi") or 0) / m * 90
            sp = (r.get("sp") or 0) / m * 90
            if not 0 <= k <= KM90 or hi > HI90 or sp > SP90:
                bad.append(f"{fid} {r['d']}: {k:.1f} km/90, {hi:.0f} hi/90, {sp:.0f} sprint/90")
    if bad:
        fails["fi"].append(f"{len(bad)} implausible running row(s), e.g. {bad[0]}")
    state = LOGS / "last_good.json"
    last = json.loads(state.read_text()) if state.exists() else {}
    n = len(d["players"])
    if last.get("fi_players"):
        swing = abs(n - last["fi_players"]) / last["fi_players"]
        if swing > FI_SWING:
            fails["fi"].append(f"Fatigue Index has {n} players, {last['fi_players']} last run ({swing:.0%} change, club rename?)")
    counts["fi_players"] = n


def check_up():
    p = LA / "up_pod/data.json"
    if not check_file("up", p):
        return
    d = json.loads(p.read_text())
    for k in ("fatigue_index", "weekly_2526", "fi_published", "weekly_history", "career_meta", "xt100", "running_weekly"):
        if not d.get(k):
            fails["up"].append(f"data.json lost its {k} block")
    meta = d["matches_meta"]
    dates = {m["date"]: m["tab"] for m in meta}
    if latest not in dates:
        fails["up"].append(f"no match tab in the sheet for the latest game ({latest})")
    for lab, c in (("match tab", collections.Counter(m["tab"] for m in meta)), ("match date", collections.Counter(m["date"] for m in meta)),
                   ("player row", collections.Counter((r["match"], r["player"]) for r in d["match_records"]))):
        dup = [k for k, v in c.items() if v > 1]
        if dup:
            fails["up"].append(f"duplicate {lab}: {dup[:3]}")
    over = [(r["match"], r["player"], r["stats"].get("Mins")) for r in d["match_records"] if (r["stats"].get("Mins") or 0) > PLAYED_MAX]
    if over:
        fails["up"].append(f"over {PLAYED_MAX} minutes: {over[:3]}")
    if latest in dates:
        tab = dates[latest]
        rec = [r for r in d["match_records"] if r["match"] == tab]
        if rec and all(r["stats"].get("Mins") is None for r in rec):
            fails["up"].append(f"{tab} tab has no minutes yet")
        played = {r["player"] for r in rec if (r["stats"].get("Mins") or 0) > 0}
        foreign = played - games[latest] if games[latest] else set()
        if foreign:
            fails["up"].append(f"{tab} lists players FBref doesn't have for Liverpool: {sorted(foreign)[:5]} (Barts home/away mix-up?)")
    played = sum(1 for m in meta if m["date"] <= latest)
    last_n = max((g.get("n") or 0 for p in d["fatigue_index"].values() for g in p["games"]), default=0)
    if last_n < played:
        fails["up"].append(f"Fatigue Index tab stops at game {last_n} of {played}, so Squad availability is short")


for fn, key in ((check_hqc, "hqc"), (check_pd, "pd"), (check_fi, "fi"), (check_up, "up")):
    try:
        fn()
    except Exception as e:                 # noqa: BLE001
        fails[key].append(f"check crashed: {type(e).__name__}: {e}")

result = dict(latest=latest, dashboards={k: dict(ok=not fails[k], fails=fails[k]) for k in ("hqc", "pd", "fi", "up")}, warns=warns, **counts)
(LOGS / "checks.json").write_text(json.dumps(result, indent=1))
print(json.dumps(result, indent=1))
