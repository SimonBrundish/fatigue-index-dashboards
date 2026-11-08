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
Matches with minutes but no tracking are estimated and flagged. The FI's own
estimates (rows marked est) are ignored and redone here, because the FI scales a
player's per-minute rate from however few tracked minutes he has: Nyoni's 1-minute
cameo (0.3 km) became 27.5 km for a 94-minute PL2 game. Here the rate comes from his
last 10 tracked games of 20+ minutes, shrunk towards the squad rate (outfield or
goalkeeper) with 270 minutes' weight, so a player with little tracking gets a
squad-like figure and a regular starter keeps his own.
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
GK = {"Alisson", "Mamardashvilli", "Woodman"}
PRIOR_MINS = 270   # weight of the squad rate, in minutes
MIN_GAME = 20      # tracked games shorter than this don't set a player's rate


def is_tracked(r):
    return bool(r.get("km")) and r.get("hi") is not None and r.get("sp") is not None and not r.get("est")


def squad_rates(series):
    """pooled per-minute km/hi/sp over every tracked game of 60+ minutes, outfield and keepers apart"""
    out = {}
    for grp in (True, False):
        rows = [r for n, f in IDS.items() if (n in GK) == grp for r in series.get(f, [])
                if is_tracked(r) and (r.get("m") or 0) >= 60]
        mins = sum(r["m"] for r in rows)
        out[grp] = {k: sum(r[k] for r in rows) / mins for k in ("km", "hi", "sp")}
    return out


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
    rates = squad_rates(series)
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
        tracked = [r for r in rows if is_tracked(r) and r["m"] >= MIN_GAME]
        sq = rates[name in GK]
        weeks = {}
        for r in rows:
            d = date.fromisoformat(r["d"])
            so = season_of(d)
            if not so:
                continue
            s, w1 = so
            wk = (d - w1).days // 7 + 1
            est = False
            if is_tracked(r):
                km, hi, sp = r["km"], r["hi"], r["sp"]
            else:
                prior = [t for t in tracked if t["d"] < r["d"]][-10:] or tracked[:10]
                mins = sum(t["m"] for t in prior)
                rate = {k: (sum(t[k] for t in prior) + PRIOR_MINS * sq[k]) / (mins + PRIOR_MINS) for k in ("km", "hi", "sp")}
                km, hi, sp = (r["m"] * rate[k] for k in ("km", "hi", "sp"))
                est = True
            b = weeks.setdefault((s, wk), {"km": 0.0, "hsr": 0.0, "sp": 0.0, "games": 0, "est": 0, "g": []})
            # one entry per game for the hover: date, competition where the FI names one, estimated flag
            b["g"].append([r["d"], r.get("c") or "", int(est)])
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
                               "games": b["games"], "est": b["est"], "g": b["g"]} if b else
                              {"week": wk, "km": 0, "hsr": 0, "sp": 0, "games": 0, "est": 0})
        out[name] = per
    return out


if __name__ == "__main__":
    series = json.load(open(sys.argv[1]))["series"]
    data = json.load(open(sys.argv[2]))
    data["running_weekly"] = build(series)
    json.dump(data, open(sys.argv[2], "w"), separators=(",", ":"), ensure_ascii=False)
    print(f"running_weekly: {len(data['running_weekly'])} players")
