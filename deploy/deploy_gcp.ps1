<#
.SYNOPSIS
    Automated Google Cloud Run + Secret Manager Provisioning & Deployment Script (PowerShell).
.DESCRIPTION
    1. Enables required Google Cloud APIs (Cloud Run, Artifact Registry, Cloud Build, Secret Manager).
    2. Creates a least-privilege IAM Service Account (agentic-trading-sa).
    3. Generates a 256-bit cryptographic TRADING_API_KEY and stores it in Google Secret Manager.
    4. Creates the Artifact Registry Docker repository.
    5. Triggers Google Cloud Build (cloudbuild.yaml) to build and deploy the hardened container.
.EXAMPLE
    .\deploy\deploy_gcp.ps1 -ProjectId "my-gcp-project-id" -Region "us-central1"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectId,

    [Parameter(Mandatory=$false)]
    [string]$Region = "us-central1",

    [Parameter(Mandatory=$false)]
    [string]$ServiceName = "agentic-trading-bot",

    [Parameter(Mandatory=$false)]
    [string]$RepoName = "trading-repo",

    [Parameter(Mandatory=$false)]
    [string]$AllowedOrigins = "http://localhost:3000,http://127.0.0.1:3000"
)

$ErrorActionPreference = "Stop"

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " AGENTIC TRADING BOT - GOOGLE CLOUD HARDENED DEPLOYMENT" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Project ID:      $ProjectId"
Write-Host "Region:          $Region"
Write-Host "Service Name:    $ServiceName"
Write-Host "----------------------------------------------------------------"

# 1. Verify gcloud CLI is installed
if (-not (Get-Command "gcloud" -ErrorAction SilentlyContinue)) {
    Write-Error "Google Cloud SDK ('gcloud') is not installed or not on PATH. Install it from https://cloud.google.com/sdk/docs/install"
    exit 1
}

gcloud config set project $ProjectId

# 2. Enable Required Google Cloud APIs
Write-Host "[1/6] Enabling Google Cloud APIs..." -ForegroundColor Yellow
gcloud services enable `
    run.googleapis.com `
    artifactregistry.googleapis.com `
    cloudbuild.googleapis.com `
    secretmanager.googleapis.com `
    iam.googleapis.com

# 3. Create Dedicated Least-Privilege Service Account
$SaName = "agentic-trading-sa"
$SaEmail = "$SaName@$ProjectId.iam.gserviceaccount.com"
Write-Host "[2/6] Configuring Least-Privilege Service Account ($SaEmail)..." -ForegroundColor Yellow

$ExistingSa = gcloud iam service-accounts list --filter="email:$SaEmail" --format="value(email)"
if (-not $ExistingSa) {
    gcloud iam service-accounts create $SaName `
        --display-name="Agentic Trading Bot Runtime Service Account"
}

# 4. Create Artifact Registry Repository if not exists
Write-Host "[3/6] Ensuring Artifact Registry Repository '$RepoName' in $Region..." -ForegroundColor Yellow
$ExistingRepo = gcloud artifacts repositories list --location=$Region --filter="name:$RepoName" --format="value(name)"
if (-not $ExistingRepo) {
    gcloud artifacts repositories create $RepoName `
        --repository-format=docker `
        --location=$Region `
        --description="Hardened Agentic Trading Bot Container Repository"
}

# 5. Provision TRADING_API_KEY in Google Secret Manager
Write-Host "[4/6] Provisioning TRADING_API_KEY in Google Secret Manager..." -ForegroundColor Yellow
$ExistingSecret = gcloud secrets list --filter="name:TRADING_API_KEY" --format="value(name)"
if (-not $ExistingSecret) {
    # Generate 32-byte (64-hex char) cryptographic key
    $Bytes = New-Object Byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($Bytes)
    $GeneratedKey = ($Bytes | ForEach-Object { $_.ToString("x2") }) -join ""

    $TempKeyFile = [System.IO.Path]::GetTempFileName()
    try {
        [System.IO.File]::WriteAllText($TempKeyFile, $GeneratedKey)
        gcloud secrets create TRADING_API_KEY --replication-policy="automatic"
        gcloud secrets versions add TRADING_API_KEY --data-file=$TempKeyFile
    } finally {
        Remove-Item -Path $TempKeyFile -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Created new TRADING_API_KEY secret in Secret Manager." -ForegroundColor Green
} else {
    Write-Host "TRADING_API_KEY secret already exists in Secret Manager (reusing latest version)." -ForegroundColor Green
}

# Grant Secret Accessor only to the runtime Service Account
gcloud secrets add-iam-policy-binding TRADING_API_KEY `
    --member="serviceAccount:$SaEmail" `
    --role="roles/secretmanager.secretAccessor" | Out-Null

# 6. Build and Deploy via Cloud Build
Write-Host "[5/6] Submitting hardened build & deploying to Cloud Run..." -ForegroundColor Yellow
gcloud builds submit --config cloudbuild.yaml `
    --substitutions="_REGION=$Region,_REPO_NAME=$RepoName,_SERVICE_NAME=$ServiceName,_SERVICE_ACCOUNT=$SaEmail,_ALLOWED_ORIGINS=$AllowedOrigins"

# 7. Output Deployed Service URL and Verification Command
$ServiceUrl = gcloud run services describe $ServiceName --region=$Region --format="value(status.url)"
Write-Host "================================================================" -ForegroundColor Green
Write-Host " [6/6] DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host "Cloud Run Service URL: $ServiceUrl"
Write-Host "Health Check (Public): $ServiceUrl/api/health"
Write-Host ""
Write-Host "To retrieve your TRADING_API_KEY from Secret Manager:" -ForegroundColor Cyan
Write-Host "  gcloud secrets versions access latest --secret=TRADING_API_KEY"
Write-Host ""
Write-Host "To call the authenticated 200-trade performance endpoint:" -ForegroundColor Cyan
Write-Host "  `$Token = gcloud secrets versions access latest --secret=TRADING_API_KEY"
Write-Host "  Invoke-RestMethod -Uri '$ServiceUrl/api/performance/200-trades' -Headers @{ Authorization = `"Bearer `$Token`" }"
