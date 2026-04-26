@echo off
REM ============================================================
REM  STS2 Analysis — one-time GitHub setup
REM  Run this from inside the sts2-analysis folder
REM ============================================================

echo [1/4] Initialising git repo...
git init
git branch -m main

echo [2/4] Staging all files...
git add -A
git commit -m "Initial commit: STS2 run analysis toolkit"

echo [3/4] Done locally.
echo.
echo [4/4] Push to GitHub:
echo   1. Go to https://github.com/new
echo   2. Name it  sts2-analysis  (keep it empty — no README)
echo   3. Then run:
echo.
echo       git remote add origin https://github.com/YOUR_USERNAME/sts2-analysis.git
echo       git push -u origin main
echo.
pause
