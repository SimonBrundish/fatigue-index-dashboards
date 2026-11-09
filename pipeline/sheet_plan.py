#!/usr/bin/env python3
"""What the UP sheet still needs before Under Pressure can show the latest game.
A shell script can't write to the sheet (that takes the Sheets connector), so
update_all.sh runs this and lists the jobs in its report. Writes ../logs/sheet_todo.json:
  missing_tabs   Barts' games with no match tab yet (tab, meta, [name, mins])
  fi_tab_empty   per-game columns of the "Fatigue Index" tab still blank for a played game:
                 {range, values}, numbers from the match tabs, 0 = unused sub (FBref),
                 blank = not in the squad. Never overwrites a filled cell."""
import csv, json, re
from pathlib import Path

import openpyxl
from openpyxl.utils import column_index_from_string as ci, get_column_letter as L

HERE = Path(__file__).resolve().parent
LA = HERE.parent
OUT = LA / "logs/sheet_todo.json"
FIRST, LAST = 5, 42            # player rows of the Fatigue Index tab
TAB = {"Nottingham Forest": "Forest", "Atletico": "Atletico Madrid"}   # Barts name -> sheet tab, as fill_sheet_from_barts.py
wb = openpyxl.load_workbook(HERE / "up_dashboard_live.xlsx", data_only=True)
barts = json.loads((HERE / "barts_matches.json").read_text())
for m in barts["matches_meta"]:
    m["tab"] = TAB.get(m["tab"], m["tab"])
ws = wb["Fatigue Index"]
ids = dict(re.findall(r'"([A-Za-z\- ]+)": "([0-9a-f]{8})"', (HERE / "pipeline.py").read_text()))
rev = {v: k for k, v in ids.items()}

missing = []
for m in sorted(barts["matches_meta"], key=lambda x: x["date"]):
    if m["tab"] not in wb.sheetnames:
        rows = [[r["player"], r["stats"].get("Mins")] for r in barts["match_records"] if TAB.get(r["match"], r["match"]) == m["tab"]]
        missing.append(dict(tab=m["tab"], date=m["date"], opponent=m["opponent"], venue=m["venue"],
                            competition=m["competition"], score_for=m["score_for"], score_against=m["score_against"], players=rows))


def tab_mins(tab):
    out = {}
    for r in wb[tab].iter_rows(min_row=3, values_only=True):
        if r[0] and r[0] not in out:
            out[r[0]] = r[1]
    return out


games = {}                     # game number -> column, from row 2 of the tab
for c in range(4, ci("BZ") + 1):
    v = ws.cell(2, c).value
    if isinstance(v, (int, float)):
        games[int(v)] = c
gid = {}
for f in ("match_minutes", "cup_europe_minutes"):
    for r in csv.DictReader(open(LA / f"lfc_data/data/{f}.csv")):
        if r["team"] == "Liverpool":
            gid[r["date"]] = r["game_id"]
unused = {}
for r in csv.DictReader(open(LA / "fatigue/data/unused_subs.csv")):
    unused.setdefault(r["game_id"], set()).add(rev.get(r["fbref_id"], r["fbref_id"]))

tabs = [m for m in sorted(barts["matches_meta"], key=lambda x: x["date"]) if m["tab"] in wb.sheetnames]
fills = []
for n, m in enumerate(tabs, 1):
    c = games.get(n)
    if not c or any(isinstance(ws.cell(r, c).value, (int, float)) and ws.cell(r, c).value > 0 for r in range(FIRST, LAST + 1)):
        continue
    mins, un = tab_mins(m["tab"]), unused.get(gid.get(m["date"]), set())
    vals = []
    for r in range(FIRST, LAST + 1):
        name = ws.cell(r, 2).value
        v = mins.get(name)
        vals.append([int(v) if isinstance(v, (int, float)) and v > 0 else (0 if name in un else None)])
    if any(x[0] for x in vals):
        fills.append(dict(tab=m["tab"], game=n, range=f"'Fatigue Index'!{L(c)}{FIRST}:{L(c)}{LAST}", values=vals))

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(dict(missing_tabs=missing, fi_tab_empty=fills), ensure_ascii=False, indent=1))
print(f"sheet todo: {len(missing)} missing tab(s) {[m['tab'] for m in missing]}, {len(fills)} empty Fatigue Index column(s) {[f['tab'] for f in fills]}")
