# STS2 Analysis — push to GitHub
# Right-click -> "Run with PowerShell"

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$remote     = "https://github.com/jac726/sts2analysis.git"

Write-Host ""
Write-Host "=== STS2 Analysis - GitHub Push ===" -ForegroundColor Cyan
Write-Host "Working in: $projectDir"
Write-Host ""

Set-Location $projectDir

# Remove any broken .git folder from a previous attempt
if (Test-Path ".git") {
    Write-Host "Removing old .git folder..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force ".git"
    Write-Host "  Removed." -ForegroundColor Green
}

Write-Host "Initialising fresh git repo..." -ForegroundColor Cyan
git init
git branch -M main
git config user.email "jchurch939@gmail.com"
git config user.name  "jac726"

Write-Host "Staging all files..." -ForegroundColor Cyan
git add -A
git status --short

Write-Host "Committing..." -ForegroundColor Cyan
git commit -m "Initial commit: STS2 run analysis toolkit"

Write-Host "Pushing to GitHub..." -ForegroundColor Cyan
git remote add origin $remote
git push -u origin main

Write-Host ""
Write-Host "Done! Live at: https://github.com/jac726/sts2analysis" -ForegroundColor Green
Write-Host ""
pause
