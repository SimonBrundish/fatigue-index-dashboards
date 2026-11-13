"""Did a Premier League club play yesterday? Gate for the daily 05:40 Fatigue
Index refresh (8 Nov 2026, Simon): refresh after every PL round and every
European / domestic-cup night, without hard-coded dates.

Reads the same cached FBref schedule pages as build.py's load_fixtures().
Prints the games found and exits 0 if there were any, 1 if none. Also exits 0
through FIFA international windows (and a few days after the last international
scraped), so internationals reach the Fatigue Index before the next club game.
  python3 games_yesterday.py                # yesterday
  python3 games_yesterday.py 2026-11-08     # a given date (for testing)
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

CACHE = Path(__file__).resolve().parents[1] / "lfc_data/data/fbref_cache"
OTHER_MINUTES = Path(__file__).resolve().parents[1] / "lfc_data/data/other_minutes.csv"
# FIFA international windows (13 Nov 2026): run every morning through them, since
# the PL schedule shows no games then. Add each new window here; 2027 dates to confirm.
INTL_WINDOWS = [("2026-11-09", "2026-11-17"), ("2027-03-22", "2027-03-30")]
INTL_TAIL_DAYS = 3     # keep running this long after the last international scraped
PL_PAGE = "schedule_ENG-Premier League_2627.html"
# UCL, UEL, UECL, FA Cup, EFL Cup -- as build.py FIXTURE_PAGES
CUP_PAGES = {"cup_sched_8.html": "UCL", "cup_sched_19.html": "UEL", "cup_sched_882.html": "UECL",
             "cup_sched_514.html": "FA Cup", "cup_sched_690.html": "EFL Cup"}


def fixtures(page):
    fp = CACHE / page
    if not fp.exists():
        return []
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", fp.read_text(errors="ignore"), re.S):
        c = {k: re.sub(r"<[^>]+>", "", v).strip()
             for k, v in re.findall(r'data-stat="([a-z_]+)"[^>]*>(.*?)</t[dh]>', tr, re.S)}
        if re.match(r"\d{4}-\d{2}-\d{2}$", c.get("date", "")) and c.get("home_team") and c.get("away_team"):
            strip = lambda s: re.sub(r"\bUtd\b", "United", re.sub(r"^[a-z]{2,3} | [a-z]{2,3}$", "", s))
            rows.append((c["date"], strip(c["home_team"]), strip(c["away_team"])))
    return rows


def international_reason(day):
    """Why internationals mean a run is due after `day`, or "" if they don't."""
    for start, end in INTL_WINDOWS:
        if start <= day <= end:
            return f"{day} is in the {start} to {end} international window"
    if OTHER_MINUTES.exists():
        dates = re.findall(r"^[^,]*,[^,]*,[^,]*,(\d{4}-\d{2}-\d{2}),", OTHER_MINUTES.read_text(), re.M)
        recent = [d for d in dates if d <= day]
        if recent:
            last = max(recent)
            if (dt.date.fromisoformat(day) - dt.date.fromisoformat(last)).days <= INTL_TAIL_DAYS:
                return f"last international scraped was {last}"
    return ""


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else (dt.date.today() - dt.timedelta(days=1)).isoformat()
    pl = fixtures(PL_PAGE)
    if not pl:
        print(f"no cached PL schedule in {CACHE} -- refreshing anyway to be safe")
        return 0
    clubs = {t for _, h, a in pl for t in (h, a)}
    games = [("PL", h, a) for d, h, a in pl if d == day]
    for page, comp in CUP_PAGES.items():
        games += [(comp, h, a) for d, h, a in fixtures(page) if d == day and (h in clubs or a in clubs)]
    games = list(dict.fromkeys(games))      # cup pages can list a tie twice
    intl = international_reason(day)
    for comp, h, a in games:
        print(f"{day}  {comp:22} {h} v {a}")
    print(f"{len(games)} game(s) involving PL clubs on {day}")
    if intl:
        print(f"internationals: {intl}")
    return 0 if games or intl else 1


if __name__ == "__main__":
    sys.exit(main())
