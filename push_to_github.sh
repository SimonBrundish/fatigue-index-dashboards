#!/bin/bash
# Copies the live dashboards from ~/Documents/LiverpoolAnalysis into this repo,
# commits and pushes to GitHub -- GitHub Pages + the simonbrundish.com/data
# Squarespace embeds pick up the new data automatically.
#   ./push_to_github.sh              # all of them
#   ./push_to_github.sh hqc pd       # only these (update_all.sh passes those that passed its checks)
# Names: fi pd hqc up city
set -e
cd "$(dirname "$0")"
LA="$HOME/Documents/LiverpoolAnalysis"
export GIT_TERMINAL_PROMPT=0

git pull -q --ff-only origin main
[ $# -gt 0 ] && WANT=" $* " || WANT=" fi pd hqc up city "

ADD=()
# Fatigue Index: the page plus its data folder, as split by fatigue/slim_publish.py
if [[ "$WANT" == *" fi "* ]]; then
  cp "$LA/fatigue/slim/fatigue-index.html" fatigue-index.html
  rm -rf fatigue-data && cp -R "$LA/fatigue/slim/fatigue-data" fatigue-data
  ADD+=(fatigue-index.html fatigue-data)
fi
if [[ "$WANT" == *" pd "* ]]; then cp "$LA/perf_desk.html" physical-performance-desk.html; ADD+=(physical-performance-desk.html); fi
if [[ "$WANT" == *" hqc "* ]]; then cp "$LA/dashboard.html" high-quality-chances.html; ADD+=(high-quality-chances.html); fi
# Under Pressure's page is edited here; only its data comes from up_pod
if [[ "$WANT" == *" up "* ]]; then cp "$LA/up_pod/data.json" under-pressure-data.json; ADD+=(under-pressure-data.json); fi
if [[ "$WANT" == *" city "* ]]; then cp "$LA/city_counterfactual/city-counterfactual.html" city-counterfactual.html; ADD+=(city-counterfactual.html); fi

git add -A "${ADD[@]}"
if git diff --cached --quiet; then
  echo "No changes to push -- dashboards already up to date on GitHub."
  exit 0
fi

git commit -q -m "Update dashboards ($(date +%Y-%m-%d))"
git push -q origin main
echo "Pushed $(git rev-parse --short HEAD) -- GitHub Pages and the Squarespace embeds will reflect this shortly."
