#!/bin/bash
# Copies the 3 live dashboard HTML files from LiverpoolAnalysis into this repo,
# commits, and pushes to GitHub -- GitHub Pages + the simonbrundish.com/data
# Squarespace embeds pick up the new data automatically, no other steps needed.
set -e
cd "$(dirname "$0")"

# Fatigue Index: the page plus its data folder, as split by fatigue/slim_publish.py
cp ~/LiverpoolAnalysis/fatigue/slim/fatigue-index.html fatigue-index.html
rm -rf fatigue-data && cp -R ~/LiverpoolAnalysis/fatigue/slim/fatigue-data fatigue-data
cp ~/LiverpoolAnalysis/perf_desk.html physical-performance-desk.html
cp ~/LiverpoolAnalysis/dashboard.html high-quality-chances.html
cp ~/LiverpoolAnalysis/city_counterfactual/city-counterfactual.html city-counterfactual.html

git add -A fatigue-index.html fatigue-data physical-performance-desk.html high-quality-chances.html city-counterfactual.html
if git diff --cached --quiet; then
  echo "No changes to push -- dashboards already up to date on GitHub."
  exit 0
fi

git commit -m "Update dashboards ($(date +%Y-%m-%d))"
git push origin main
echo "Pushed -- GitHub Pages and the Squarespace embeds will reflect this shortly."
