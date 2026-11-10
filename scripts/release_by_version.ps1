<#
.SYNOPSIS
    Sequential versioned Git release & upload script for https://github.com/amirmjou/aitrader
.DESCRIPTION
    Creates clean, milestone-by-milestone commits and annotated SemVer tags (v0.1.0 -> v1.1.0),
    updates pyproject.toml at each step, and pushes all commits and tags to GitHub.
#>

param(
    [string]$RemoteUrl = "https://github.com/amirmjou/aitrader.git",
    [switch]$SkipPush
)

$ErrorActionPreference = "Stop"

# Locate git executable if not in default session PATH
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $possibleGitDirs = @(
        "C:\Program Files\Git\cmd",
        "C:\Program Files\Git\bin",
        "$env:LOCALAPPDATA\Programs\Git\cmd"
    )
    foreach ($dir in $possibleGitDirs) {
        if (Test-Path "$dir\git.exe") {
            $env:Path += ";$dir"
            break
        }
    }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "Git is not installed or not found on PATH. Run: winget install --id Git.Git -e --source winget"
    exit 1
}

function Set-ProjectVersion {
    param([string]$Version)
    $pyprojectPath = Join-Path $PSScriptRoot "..\pyproject.toml"
    $content = Get-Content $pyprojectPath -Raw
    $updated = $content -replace '(?m)^version\s*=\s*"[^"]+"', "version = `"$Version`""
    Set-Content -Path $pyprojectPath -Value $updated -Encoding UTF8 -NoNewline
}

Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".git")) {
    Write-Host "==> Initializing Git repository..." -ForegroundColor Cyan
    git init
    git branch -M main
}

# Configure git user if not already set globally
$userName = git config user.name
if (-not $userName) {
    git config user.name "amirmjou"
    git config user.email "amirmjou@users.noreply.github.com"
}

$existingRemote = git remote
if ($existingRemote -contains "origin") {
    git remote set-url origin $RemoteUrl
} else {
    git remote add origin $RemoteUrl
}

# -------------------------------------------------------------------------
# v0.1.0 — Milestone 1: Core Multi-Agent Graph
# -------------------------------------------------------------------------
Write-Host "==> Creating release v0.1.0 (Core Multi-Agent Graph)..." -ForegroundColor Green
Set-ProjectVersion "0.1.0"
git add .gitignore pyproject.toml requirements.txt PROJECT.md README.md core/
git commit -m "feat(core): initialize multi-agent trading graph and LLM clients (M1)"
git tag -a v0.1.0 -m "v0.1.0: Core Multi-Agent Trading Graph (M1)"

# -------------------------------------------------------------------------
# v0.2.0 — Milestone 2: EVM Execution & 6-Layer Pre-Broadcast Guardrails
# -------------------------------------------------------------------------
Write-Host "==> Creating release v0.2.0 (EVM Execution & Safety Guardrails)..." -ForegroundColor Green
Set-ProjectVersion "0.2.0"
git add pyproject.toml execution/
git commit -m "feat(execution): add dual-engine MetaMask wallet, DEX routers, and 6-layer pre-flight guardrails (M2)"
git tag -a v0.2.0 -m "v0.2.0: EVM Execution Router & Pre-Broadcast Safety Guardrails (M2)"

# -------------------------------------------------------------------------
# v0.3.0 — Milestone 3: Real-Time Visualization UI & Telemetry
# -------------------------------------------------------------------------
Write-Host "==> Creating release v0.3.0 (Visualization UI & Telemetry)..." -ForegroundColor Green
Set-ProjectVersion "0.3.0"
git add pyproject.toml visualization/
git commit -m "feat(visualization): add FastAPI SSE deliberation streaming and WebSocket market telemetry (M3)"
git tag -a v0.3.0 -m "v0.3.0: Real-Time Deliberation & Market Visualization Interface (M3)"

# -------------------------------------------------------------------------
# v0.4.0 — Milestone 4: Crypto Deliberation & Remote Agent Pipeline
# -------------------------------------------------------------------------
Write-Host "==> Creating release v0.4.0 (Crypto Deliberation & Remote Agent)..." -ForegroundColor Green
Set-ProjectVersion "0.4.0"
git add pyproject.toml crypto_pipeline/ingestion/ crypto_pipeline/sizing/ crypto_pipeline/remote_agent/ crypto_pipeline/jev_integration/ crypto_pipeline/pipeline.py
git commit -m "feat(crypto): add CCXT/DeFiLlama feeds, ATR-14 sizer, Jev scorer, and remote agent bridge (M4)"
git tag -a v0.4.0 -m "v0.4.0: Crypto Deliberation & Remote Agent Pipeline (M4)"

# -------------------------------------------------------------------------
# v1.0.0 — Milestone 5: Simulation, E2E Suite & Adversarial Hardening
# -------------------------------------------------------------------------
Write-Host "==> Creating release v1.0.0 (Simulation, E2E & Adversarial Verification)..." -ForegroundColor Green
Set-ProjectVersion "1.0.0"
git add pyproject.toml simulation/ tests/e2e/ tests/adversarial/ tests/unit/ tests/conftest.py TEST_INFRA.md TEST_READY.md
git commit -m "feat(simulation,tests): add paper trader, backtester, and 5-tier E2E + adversarial test suites (M5)"
git tag -a v1.0.0 -m "v1.0.0: Production Release with Full E2E & Adversarial Hardening (M5)"

# -------------------------------------------------------------------------
# v1.1.0 — Milestone 6: Agentic Skills & MetaMask EVM Airdrop Scanner
# -------------------------------------------------------------------------
Write-Host "==> Creating release v1.1.0 (Agentic Skills & MetaMask EVM Airdrop Scanner)..." -ForegroundColor Green
Set-ProjectVersion "1.1.0"
git add pyproject.toml CHANGELOG.md .agents/skills/ .agent/skills/ crypto_pipeline/airdrop_scanner.py crypto_pipeline/__init__.py tests/test_airdrop_scanner.py sessions/ scripts/release_by_version.ps1
git commit -m "feat(skills,airdrop): migrate workflows to skills, add trader-validation-pipeline and MetaMask EVM airdrop scanner"
git tag -a v1.1.0 -m "v1.1.0: Agentic Skills & MetaMask EVM Airdrop Scanner (M6)"

Write-Host "`n==> Created 6 versioned commits and tags:" -ForegroundColor Cyan
git log --oneline --decorate

if (-not $SkipPush) {
    Write-Host "`n==> Pushing main branch and all version tags to $RemoteUrl ..." -ForegroundColor Yellow
    git push -u origin main --tags
    Write-Host "==> Successfully uploaded all versions to $RemoteUrl !" -ForegroundColor Green
} else {
    Write-Host "`n==> SkipPush specified. Run 'git push -u origin main --tags' when ready." -ForegroundColor Yellow
}
