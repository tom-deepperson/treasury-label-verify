# Deploy treasury-label-verify to Cloud Run.
# Prerequisite: gcloud authenticated with an account that can deploy to GOOGLE_CLOUD_PROJECT in .env
#   gcloud auth login
#   gcloud config set account YOUR_GCP_ACCOUNT_EMAIL
#   gcloud config set project $env:GOOGLE_CLOUD_PROJECT
# See DEPLOY_AUTH.md if you use multiple Google accounts.

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

function Invoke-Gcloud {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & gcloud @args
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($code -ne 0) {
        throw "gcloud exited ${code}: gcloud $($args -join ' ')"
    }
}

function Get-GcloudValue {
    param([string]$Name)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $raw = & gcloud config get-value $Name 2>&1
    $ErrorActionPreference = $prev
    ($raw | Where-Object { $_ -is [string] -and $_ -notmatch '^\s*$' } | Select-Object -Last 1).ToString().Trim()
}

$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    Write-Error "Missing .env at $envFile. Copy .env.example and fill in secrets."
}

Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    if ($line -match "^([^=]+)=(.*)$") {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim().Trim('"').Trim("'")
        Set-Item -Path "env:$name" -Value $value
    }
}

$ProjectId = $env:GOOGLE_CLOUD_PROJECT
if ([string]::IsNullOrWhiteSpace($ProjectId)) {
    Write-Error "Set GOOGLE_CLOUD_PROJECT in .env before deploying."
}
$Region = if ($env:DEPLOY_REGION) { $env:DEPLOY_REGION } else { "us-east1" }
$Service = "treasury-label-verify"

$required = @("SESSION_SECRET", "REVIEWER_PASSWORD", "DEVELOPER_PASSWORD")
foreach ($key in $required) {
    if (-not (Get-Item "env:$key" -ErrorAction SilentlyContinue) -or [string]::IsNullOrWhiteSpace((Get-Item "env:$key").Value)) {
        Write-Error "Set $key in .env before deploying."
    }
}

Write-Host "Using gcloud account: $(Get-GcloudValue account)"
Write-Host "Using project: $ProjectId"
if ($env:DEPLOY_CONFIRM -ne "y" -and $env:DEPLOY_CONFIRM -ne "Y") {
    $confirm = Read-Host "Continue deploy? (y/N)"
    if ($confirm -ne "y" -and $confirm -ne "Y") { exit 0 }
}

Invoke-Gcloud config set project $ProjectId
Invoke-Gcloud services enable `
    run.googleapis.com `
    cloudbuild.googleapis.com `
    artifactregistry.googleapis.com `
    containerregistry.googleapis.com `
    vision.googleapis.com `
    --quiet

$projectNumber = (Invoke-Gcloud projects describe $ProjectId --format="value(projectNumber)")
$computeSa = "$projectNumber-compute@developer.gserviceaccount.com"
Write-Host "Granting Vision API access to Cloud Run runtime service account: $computeSa"
Invoke-Gcloud projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$computeSa" `
    --role="roles/serviceusage.serviceUsageConsumer" `
    --quiet 2>$null | Out-Null

Write-Host "Building and deploying from source (10-20 min first time)..."

$reviewerUser = if ($env:REVIEWER_USERNAME) { $env:REVIEWER_USERNAME } else { "treasury" }
$devUser = if ($env:DEVELOPER_USERNAME) { $env:DEVELOPER_USERNAME } else { "developer" }

Invoke-Gcloud run deploy $Service `
  --source . `
  --platform managed `
  --region $Region `
  --quiet `
  --allow-unauthenticated `
  --min-instances 1 `
  --memory 4Gi `
  --cpu 2 `
  --concurrency 1 `
  --timeout 300 `
  --set-env-vars "REVIEWER_USERNAME=$reviewerUser,MAX_TESTS=50,USAGE_STORE=file,WARM_OCR=1,OCR_BACKEND=vision,ROTATION_OCR_BACKEND=vision,USE_LLM=1" `
  --set-env-vars "REVIEWER_PASSWORD=$env:REVIEWER_PASSWORD,SESSION_SECRET=$env:SESSION_SECRET" `
  --set-env-vars "DEVELOPER_USERNAME=$devUser,DEVELOPER_PASSWORD=$env:DEVELOPER_PASSWORD" `
  --set-env-vars "GEMINI_API_KEY=$env:GEMINI_API_KEY,OPENAI_API_KEY=$env:OPENAI_API_KEY,ANTHROPIC_API_KEY=$env:ANTHROPIC_API_KEY,GEMINI_MODEL=gemini-3.1-flash-lite" `

$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$url = (& gcloud run services describe $Service --region $Region --format="value(status.url)" 2>&1 | Select-Object -Last 1).ToString().Trim()
$ErrorActionPreference = $prev

Write-Host ""
Write-Host "Deployed: $url"
Write-Host "Health:   $url/health"
Write-Host "Login:    $url/login"
Write-Host ""
Write-Host "Admin (unlimited quota): $devUser / (DEVELOPER_PASSWORD from .env)"
Write-Host "Reviewer (quota applies):  $reviewerUser / (REVIEWER_PASSWORD from .env)"
