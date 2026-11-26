#!/usr/bin/env python3
"""2026/27 rows for the UP sheet's "Team Dashboard" tab (17 Nov 2026, Simon).

One row per Liverpool game (columns A:BN, Simon's layout). Inputs come from his
match tabs first (touches, touches in box, PC), then Barts' team tables (xG,
xGOT, xT, possession, opposition touches, shots), then FotMob (long ball %,
kick-off, captain, formation, referee). Derived columns use the formulas his
2024/25 and 2025/26 rows follow. A shell script can't write to the sheet, so
this adds a "team_dashboard" list to ../logs/sheet_todo.json: a full row for a
game the tab doesn't have yet, and only the EMPTY cells of rows already there,
so Simon's own figures are never overwritten. Needs BARTS_LOCAL (a clone of
Barts' repo) and up_dashboard_live.xlsx + data.json from pipeline.py. A game with no Barts
page yet is built from FotMob (no xT, PC or Def lions until Barts posts it).
    BARTS_LOCAL=/path/to/DrBarts2627 python3 team_dashboard.py [--fill-empty]
"""
import csv, datetime as dt, glob, json, sys, zoneinfo
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter as L

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fetch_barts_matches as f  # noqa: E402

TODO = HERE.parent / "logs/sheet_todo.json"
SEASON_START = dt.datetime(2026, 7, 1)
TAB = {"Nottingham Forest": "Forest", "Atletico": "Atletico Madrid", "Brugge a": "Club Brugge a"}   # Barts name -> sheet tab
NAME = {"Newcastle United": "Newcastle", "Nottingham Forest": "Forest", "Ipswich Town": "Ipswich",
        "Tottenham Hotspur": "Spurs", "AFC Bournemouth": "Bournemouth", "Manchester City": "Man City",
        "Manchester United": "Man Utd", "Brighton & Hove Albion": "Brighton", "Crystal Palace": "Palace"}
COMP = {"PL": "PL", "UCL": "CL", "EFLC": "Caribu"}
CAPTAIN = {"Konstantinos": "Kostas"}
ANFIELD = 6868
HQC, HQC_FOTMOB = 0.27, 0.18     # per-shot xG lines: Barts (Opta), FotMob stand-in


def num(v):
    try:
        return float(str(v).replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def fotmob_matches():
    """{date: (match json, kick-off UTC)} for Liverpool's FotMob match files."""
    out = {}
    for p in glob.glob(str(HERE.parent / "understat_bulk/data/fotmob_md/*.json")):
        d = json.load(open(p)); g = d.get("general", {})
        if "Liverpool" in (g.get("homeTeam", {}).get("name"), g.get("awayTeam", {}).get("name")):
            t = dt.datetime.strptime(g["matchTimeUTC"], "%a, %b %d, %Y, %H:%M UTC").replace(tzinfo=dt.timezone.utc)
            out[t.date().isoformat()] = (d, t)
    return out


def fotmob_stats(d):
    """{stat key: [home, away]} from the full-match stats."""
    out = {}

    def walk(o):
        if isinstance(o, dict):
            s = o.get("stats")
            if "key" in o and isinstance(s, list) and len(s) == 2 and o["key"] not in out and any(x is not None for x in s):
                out[o["key"]] = s
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(d["content"]["stats"]["Periods"]["All"])
    return out


def r2(x, d=2):
    if x is None:
        return None
    x = round(x, d)
    return 0.0 if x == 0 else x


def derive(v):
    """Simon's derived columns, as reproduced from his 2024/25 and 2025/26 rows."""
    g = v.get

    def div(a, b, d=2, zero=None):
        if a is None or b is None:
            return None
        return r2(a / b, d) if b else zero

    def sub(a, b):
        return None if a is None or b is None else r2(a - b)
    pct = lambda a, b, d=2: None if a is None or not b else r2(a / b * 100, d)
    v["AB"] = sub(g("O"), g("P")); v["AC"] = sub(g("M"), g("O")); v["AD"] = sub(g("N"), g("P"))
    v["AE"] = pct(g("Q"), g("O")); v["AF"] = pct(g("Q"), g("S")); v["AG"] = pct(g("R"), g("T"))
    v["AH"] = div(g("S"), g("Y"))
    v["AI"] = pct(g("Y"), g("X"), 1); v["AJ"] = pct(g("AA"), g("Z"), 1)
    v["AK"] = None if v["AI"] is None or v["AJ"] is None else r2(g("Y") / g("X") * 100 - g("AA") / g("Z") * 100, 1)
    v["AL"] = sub(g("Q"), g("R")); v["AM"] = sub(g("Q"), g("O"))
    v["AN"] = div(g("Y"), g("O")); v["AO"] = div(g("AA"), g("R"))
    v["AP"] = sub(g("N"), g("R")); v["AQ"] = v["AB"]
    v["AR"] = div(g("Y"), g("M"), zero=0); v["AS"] = div(g("AA"), g("N"), zero=0)
    v["AT"] = None if g("X") is None or g("Z") is None else g("X") + g("Z")
    v["AU"] = None if not v["AT"] or g("Y") is None else r2((g("Y") + g("AA")) / v["AT"] * 100)
    v["BA"] = pct(g("AW"), g("AY"), 1); v["BB"] = pct(g("AX"), g("AZ"), 1)
    v["BD"] = pct(g("AA"), g("Z"))
    v["BE"] = None if g("Q") is None or g("R") is None else r2(g("Q") + g("R"))
    v["BF"] = None if g("Y") is None else (round(g("Y") / g("AW")) if g("AW") else 30)     # 30 = his no-HQC value
    v["BG"] = None if g("AA") is None else (round(g("AA") / g("AX")) if g("AX") else 30)
    v["BH"] = div(g("Q"), g("AY"))
    v["BJ"] = None if g("X") is None or g("AV") is None else g("X") + g("AV")
    v["BI"] = div(g("Z"), v["BJ"])
    v["BK"] = pct(v["BJ"], g("X"))
    v["BL"] = div(g("P"), g("AZ")); v["BM"] = div(g("Q"), g("AY")); v["BN"] = div(g("R"), g("AZ"))
    return v


def build_row(n, m, wb, hist, fm, lfc_shots):
    tab = m["tab"]; home = m["venue"] == "H"
    d, t = fm.get(m["date"], (None, None))
    st = fotmob_stats(d) if d else {}
    i_me = 0 if home else 1
    xt = {}
    if m.get("source"):
        T = f.tables(f.get(m["source"].split(", ", 1)[1]))
        summ = T["Match Summary - Full Time"]["rows"]
        me = summ["Liverpool"]; opp = next(x for k, x in summ.items() if k != "Liverpool")
        known = sorted({r["player"] for r in json.load(open(HERE / "barts_matches.json"))["match_records"]
                        if TAB.get(r["match"], r["match"]) == tab})
        for e in (e for k, es in T["_all"].items() if k.endswith("Player Match Possession Summary") for e in es):
            side = "L" if any(f.sheet_name(x, known) in known for x in e["rows"]) else "O"
            xt.setdefault(side, round(sum(num(x.get("xT")) or 0 for x in e["rows"].values()), 2))
    else:
        # no Barts page yet: the same summary from FotMob (no xT or possession control there)
        def side(i):
            s = lambda k: (st.get(k) or [None, None])[i]
            ps = [p for p in d["content"]["playerStats"].values() if (p.get("teamId") == 8650) == (i == i_me)]
            tch = sum((g.get("stats", {}).get("Touches", {}).get("stat") or {}).get("value") or 0
                      for p in ps for g in p.get("stats", []))
            return {"xG": s("expected_goals"), "xGOT": s("expected_goals_on_target"), "Possession %": s("BallPossesion"),
                    "Touches": tch, "PKBox Touches": s("touches_opp_box"), "Total Shots": s("total_shots"),
                    "Possession Control": None}
        me, opp = side(i_me), side(1 - i_me)
    # Simon's match tab: sums over the players who played
    tot = dict(X=0.0, Y=0.0, AV=0.0); have_pc = False
    if tab in wb.sheetnames:
        sh = wb[tab]; C = {}
        for j, h in enumerate(c.value for c in sh[1]):
            C.setdefault(h, j)
        seen = set()
        for r in sh.iter_rows(min_row=3, values_only=True):
            if not r[0] or r[0] in seen or not num(r[1]):
                continue
            seen.add(r[0])
            for k, h in (("X", "Touches"), ("Y", "Touches inside box"), ("AV", "PC")):
                x = num(r[C[h]]) if h in C and C[h] < len(r) else None
                if x is not None:
                    tot[k] += x; have_pc |= k == "AV"
    def long_ball_pct(i):
        a, p = st.get("long_balls_accurate"), st.get("passes")
        if not a or not p or not num(p[i]):
            return None
        return r2(num(str(a[i]).split(" ")[0]) / num(p[i]) * 100, 1)
    lineup = d["content"]["lineup"]["homeTeam" if home else "awayTeam"] if d else {}
    capt = next((p["name"].split()[0] for p in lineup.get("starters", []) if p.get("isCaptain")), None)
    shots = lfc_shots.get(m["date"], {}).get("shots", [])
    if not shots and d:                 # HQC's shot log follows Barts; before he posts, FotMob's shot map
        shots = [{"team": "Liverpool" if s["teamId"] == 8650 else "opp", "xg": s.get("expectedGoals")}
                 for s in d["content"].get("shotmap", {}).get("shots", []) if not s.get("isOwnGoal")]

    def hqc(ours):
        c = 0
        for s in shots:
            if (s["team"] == "Liverpool") != ours:
                continue
            x = s.get("opta_xg")
            c += (x > HQC) if x is not None else ((s.get("xg") or 0) > HQC_FOTMOB)
        return c
    gf, ga = m["score_for"], m["score_against"]
    team = NAME.get(m["opponent"], m["opponent"])
    pitch = ANFIELD if home else next((int(r[5]) for r in reversed(hist) if r[1] and r[1].replace(" a", "") == team
                                       and r[3] == "Away" and isinstance(r[5], (int, float))), None)
    fo = lineup.get("formation")
    v = dict(A=n, B=team, C=COMP.get(m["competition"], m["competition"]), D="Home" if home else "Away",
             E=dt.date.fromisoformat(m["date"]).strftime("%d/%m/%Y"), F=pitch,
             G=t.astimezone(zoneinfo.ZoneInfo("Europe/London")).strftime("%H:%M") if t else None,
             H=CAPTAIN.get(capt, capt), I=int(fo.replace("-", "")) if fo else None,
             J=(d["content"]["matchFacts"]["infoBox"].get("Referee") or {}).get("text") if d else None,
             L=3 if gf > ga else 1 if gf == ga else 0, M=gf, N=ga,
             O=num(me["xG"]), P=num(opp["xG"]), Q=num(me["xGOT"]), R=num(opp["xGOT"]),
             S=xt.get("L"), T=xt.get("O"), U=long_ball_pct(i_me), V=long_ball_pct(1 - i_me),
             W=round(num(me["Possession %"])) if num(me["Possession %"]) is not None else None,
             X=int(tot["X"]) if tot["X"] else int(num(me["Touches"])),
             Y=int(tot["Y"]) if tot["Y"] else int(num(me["PKBox Touches"])),
             Z=int(num(opp["Touches"])), AA=int(num(opp["PKBox Touches"])),
             AV=int(tot["AV"]) if have_pc else (int(num(me["Possession Control"])) if num(me["Possession Control"]) is not None else None),
             AW=hqc(True), AX=hqc(False), AY=int(num(me["Total Shots"])), AZ=int(num(opp["Total Shots"])))
    derive(v)
    return [v.get(L(c)) for c in range(1, 67)]


def main():
    wb = openpyxl.load_workbook(HERE / "up_dashboard_live.xlsx", data_only=True)
    ws = wb["Team Dashboard"]
    rows = [[ws.cell(r, c).value for c in range(1, 67)] for r in range(2, ws.max_row + 1)]
    hist = [r for r in rows if isinstance(r[4], dt.datetime) and r[4] < SEASON_START]
    have = {}       # game number -> sheet row
    last = 1
    for i, r in enumerate(rows, 2):
        if any(x not in (None, "") for x in r):
            last = i
        if isinstance(r[4], dt.datetime) and r[4] >= SEASON_START and isinstance(r[0], (int, float)):
            have[int(r[0])] = i
    # every game the pipeline knows (Barts or a hand-made tab), with Barts' page where he has one
    barts = {TAB.get(m["tab"], m["tab"]): m for m in json.load(open(HERE / "barts_matches.json"))["matches_meta"]}
    meta = sorted(({**m, **({"source": barts[m["tab"]]["source"]} if m["tab"] in barts else {})}
                   for m in json.load(open(HERE / "data.json"))["matches_meta"]), key=lambda m: m["date"])
    fill_empty = "--fill-empty" in sys.argv
    fm = fotmob_matches()
    lfc_shots = {g["date"]: g for g in json.load(open(HERE.parent / "understat_bulk/lfc_shots.json"))["games"]}
    built, todo = [], []
    for n, m in enumerate(meta, 1):
        if n in have and not fill_empty:
            continue                        # each page takes ~1 min to parse; existing rows are Simon's
        row = build_row(n, m, wb, hist, fm, lfc_shots)
        built.append(row)
        if n in have:
            r = have[n]
            cur = rows[r - 2]
            fill = [v if cur[c] in (None, "") else None for c, v in enumerate(row)]
            if any(x is not None for x in fill):
                todo.append(dict(game=n, tab=m["tab"], kind="empty cells", range=f"'Team Dashboard'!A{r}:BN{r}", values=[fill]))
        else:
            last += 1
            todo.append(dict(game=n, tab=m["tab"], kind="new row", range=f"'Team Dashboard'!A{last}:BN{last}", values=[row]))
    with open(HERE / "team_dashboard_new_rows.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([ws.cell(1, c).value or "" for c in range(1, 67)])
        w.writerows([["" if x is None else x for x in r] for r in built])
    t = json.loads(TODO.read_text()) if TODO.exists() else {}
    t["team_dashboard"] = todo
    TODO.write_text(json.dumps(t, ensure_ascii=False, indent=1))
    print(f"team dashboard: {len(built)} games, {sum(x['kind'] == 'new row' for x in todo)} new row(s), "
          f"{sum(x['kind'] == 'empty cells' for x in todo)} row(s) with empty cells to fill")


if __name__ == "__main__":
    main()
