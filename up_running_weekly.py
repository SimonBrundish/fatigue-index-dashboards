#!/usr/bin/env python3
"""Add weekly running load (distance, HSR, sprint) per Liverpool player to the
Under Pressure data file, for the "Running load" charts on the Fatigue Index tab.

Source: the Fatigue Index per-match series (fatigue-data/series.json), which is
FotMob/Opta tracking with Simon's own Champions League distances from the UP sheet,
and FI estimates for untracked competitions (cups, internationals).

Usage: python3 up_running_weekly.py SERIES_JSON UP_DATA_JSON
(rewrites UP_DATA_JSON in place with a `running_weekly` key)

Definitions (same as Simon's UP sheet):
  distance = total km
  HSR      = metres at 19.8-25.2 km/h  (FI "hi" minus sprint metres)
  sprint   = metres above 25.2 km/h
Matches with minutes but no tracking are estimated from the player's own
per-minute rate over his last 10 tracked games (or his overall rate) and flagged.
"""
import json, sys
from datetime import date, timedelta

# UP sheet short name -> FBref id (same ids the Fatigue Index uses)
IDS = {"Alisson": "7a2e46a8", "Mamardashvilli": "d4b73232", "Frimpong": "74f2e748", "Bradley": "bbd67769",
       "Tsimi": "f315ca93", "Kerkez": "0ad53bdc", "Gomez": "7a11550b", "Araujo": "2bef2bca", "Jacquet": "cef70c94",
       "VVD": "e06683ca", "Endo": "c149016b", "Mac": "83d074ff", "Gravenberch": "b8e740fb", "Szobo": "934e1968",
       "Barcola": "a0d55a09", "Munoz": "f8b5680f", "Chiesa": "b0f7e36c", "Gakpo": "1971591f", "Wirtz": "e7fcf289",
       "Ekiike": "5b92d896", "Isak": "8e92be30", "Nyoni": "1d3b3d77", "Rio": "022eca88", "McConnell": "bf973eeb",
       "Koumas": "d77edba6", "Woodman": "19e50035", "Chambers": "7d6af698"}
# week 1 = Monday of the week of Liverpool's first competitive game (matches FI_SEASON_START in under-pressure.html)
SEASONS = [("25/26", date(2025, 8, 10)), ("26/27", date(2026, 8, 23))]


def monday(d):
    return d - timedelta(days=d.weekday())


def season_of(d):
    cur = None
    for s, start in SEASONS:
        if d >= monday(start):
            cur = (s, monday(start))
    return cur


def build(series):
    out = {}
    # every player's weeks run to the squad's last week, so weeks out (injury, rest) show as drops
    last_week = {}
    for fid in IDS.values():
        for r in series.get(fid, []):
            so = season_of(date.fromisoformat(r["d"]))
            if so:
                wk = (date.fromisoformat(r["d"]) - so[1]).days // 7 + 1
                last_week[so[0]] = max(last_week.get(so[0], 0), wk)
    for name, fid in IDS.items():
        rows = sorted((r for r in series.get(fid, []) if (r.get("m") or 0) > 0), key=lambda r: r["d"])
        if not rows:
            continue
        tracked = [r for r in rows if r.get("km") and r.get("hi") is not None and r.get("sp") is not None]
        weeks = {}
        for r in rows:
            d = date.fromisoformat(r["d"])
            so = season_of(d)
            if not so:
                continue
            s, w1 = so
            wk = (d - w1).days // 7 + 1
            km, hi, sp, est = r.get("km"), r.get("hi"), r.get("sp"), bool(r.get("est"))
            if not (km and hi is not None and sp is not None):
                prior = [t for t in tracked if t["d"] < r["d"]][-10:] or tracked
                if not prior:
                    continue
                mins = sum(t["m"] for t in prior)
                km = r["m"] * sum(t["km"] for t in prior) / mins
                hi = r["m"] * sum(t["hi"] for t in prior) / mins
                sp = r["m"] * sum(t["sp"] for t in prior) / mins
                est = True
            b = weeks.setdefault((s, wk), {"km": 0.0, "hsr": 0.0, "sp": 0.0, "games": 0, "est": 0})
            b["km"] += km
            b["hsr"] += max(0.0, hi - sp)
            b["sp"] += sp
            b["games"] += 1
            b["est"] += est
        per = {}
        for s, _ in SEASONS:
            if not any(k[0] == s for k in weeks):
                continue
            last = last_week[s]
            per[s] = []
            for wk in range(1, last + 1):
                b = weeks.get((s, wk))
                per[s].append({"week": wk, "km": round(b["km"], 1), "hsr": round(b["hsr"]), "sp": round(b["sp"]),
                               "games": b["games"], "est": b["est"]} if b else
                              {"week": wk, "km": 0, "hsr": 0, "sp": 0, "games": 0, "est": 0})
        out[name] = per
    return out


if __name__ == "__main__":
    series = json.load(open(sys.argv[1]))["series"]
    data = json.load(open(sys.argv[2]))
    data["running_weekly"] = build(series)
    json.dump(data, open(sys.argv[2], "w"), separators=(",", ":"), ensure_ascii=False)
    print(f"running_weekly: {len(data['running_weekly'])} players")
