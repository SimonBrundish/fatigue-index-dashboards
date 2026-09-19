#!/bin/bash
# Copies the 3 live dashboard HTML files from LiverpoolAnalysis into this repo,
# commits, and pushes to GitHub -- GitHub Pages + the simonbrundish.com/data
# Squarespace embeds pick up the new data automatically, no other steps needed.
set -e
cd "$(dirname "$0")"

cp ~/LiverpoolAnalysis/fatigue/fatigue_dashboard.html fatigue-index.html
cp ~/LiverpoolAnalysis/perf_desk.html physical-performance-desk.html
cp ~/LiverpoolAnalysis/dashboard.html high-quality-chances.html

git add fatigue-index.html physical-performance-desk.html high-quality-chances.html
if git diff --cached --quiet; then
  echo "No changes to push -- dashboards already up to date on GitHub."
  exit 0
fi

git commit -m "Update dashboards ($(date +%Y-%m-%d))"
git push origin main
echo "Pushed -- GitHub Pages and the Squarespace embeds will reflect this shortly."
