# Deploy treasury-label-verify to Cloud Run (personal GCP project).
# Prerequisite: gcloud logged in with the account that owns YOUR_GCP_PROJECT_ID
#   gcloud auth login
#   gcloud config set account YOUR_PERSONAL_EMAIL
#   gcloud config set project YOUR_GCP_PROJECT_ID

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent

Set-Location $Root

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

$ProjectId = if ($env:GOOGLE_CLOUD_PROJECT) { $env:GOOGLE_CLOUD_PROJECT } else { "YOUR_GCP_PROJECT_ID" }
$Region = if ($env:DEPLOY_REGION) { $env:DEPLOY_REGION } else { "us-east1" }
$Service = "treasury-label-verify"

$required = @("SESSION_SECRET", "REVIEWER_PASSWORD", "DEVELOPER_PASSWORD")
foreach ($key in $required) {
    if (-not (Get-Item "env:$key" -ErrorAction SilentlyContinue) -or [string]::IsNullOrWhiteSpace((Get-Item "env:$key").Value)) {
        Write-Error "Set $key in .env before deploying."
    }
}

Write-Host "Using gcloud account: $(gcloud config get-value account 2>$null)"
Write-Host "Using project: $ProjectId"
$confirm = Read-Host "Continue deploy? (y/N)"
if ($confirm -ne "y" -and $confirm -ne "Y") { exit 0 }

gcloud config set project $ProjectId
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --quiet

Write-Host "Building container (10-20 min first time)..."
gcloud builds submit --tag "gcr.io/$ProjectId/$Service"

$reviewerUser = if ($env:REVIEWER_USERNAME) { $env:REVIEWER_USERNAME } else { "treasury" }
$devUser = if ($env:DEVELOPER_USERNAME) { $env:DEVELOPER_USERNAME } else { "developer" }

gcloud run deploy $Service `
  --image "gcr.io/$ProjectId/$Service" `
  --platform managed `
  --region $Region `
  --allow-unauthenticated `
  --min-instances 1 `
  --memory 2Gi `
  --cpu 2 `
  --timeout 300 `
  --set-env-vars "REVIEWER_USERNAME=$reviewerUser,MAX_TESTS=10,USAGE_STORE=file,WARM_OCR=1" `
  --set-env-vars "REVIEWER_PASSWORD=$env:REVIEWER_PASSWORD,SESSION_SECRET=$env:SESSION_SECRET" `
  --set-env-vars "DEVELOPER_USERNAME=$devUser,DEVELOPER_PASSWORD=$env:DEVELOPER_PASSWORD" `
  --set-env-vars "GEMINI_API_KEY=$env:GEMINI_API_KEY,OPENAI_API_KEY=$env:OPENAI_API_KEY,ANTHROPIC_API_KEY=$env:ANTHROPIC_API_KEY"

$url = gcloud run services describe $Service --region $Region --format="value(status.url)"
Write-Host ""
Write-Host "Deployed: $url"
Write-Host "Health:   $url/health"
Write-Host "Login:    $url/login"
Write-Host ""
Write-Host "Developer: $devUser / (DEVELOPER_PASSWORD from .env)"
Write-Host "Reviewer:  $reviewerUser / (REVIEWER_PASSWORD from .env - share with Treasury only)"
