# Deploy authentication (gcloud)

Your Cloud Run project ID lives in **`.env`** as `GOOGLE_CLOUD_PROJECT` (see `.env.example`). Do not commit the real value.

If you use **multiple Google accounts**, `gcloud` may be signed in with an account that does not own the project in `.env`. Cloud Run deploy will fail until `gcloud` uses the account that has Owner or Editor access to that project.

## Sign in with the correct account

In your terminal (browser login required):

```bash
gcloud auth login
```

Sign in with the Google account that owns or can administer your GCP project.

List active accounts:

```bash
gcloud auth list
```

## Recommended: separate gcloud configuration

Use a dedicated configuration when this project uses a different account than your default:

```bash
gcloud config configurations create treasury-label-verify
gcloud config configurations activate treasury-label-verify
gcloud config set account YOUR_GCP_ACCOUNT_EMAIL
gcloud config set project YOUR_GCP_PROJECT_ID
```

(`YOUR_GCP_PROJECT_ID` = value of `GOOGLE_CLOUD_PROJECT` in `.env`.)

Switch back to another configuration later:

```bash
gcloud config configurations activate default
```

## Verify before deploy

```bash
gcloud config get-value account
gcloud config get-value project
```

Expected:

- **account:** the Google account with access to the project
- **project:** matches `GOOGLE_CLOUD_PROJECT` in `.env`

Quick access check:

```bash
gcloud projects describe YOUR_GCP_PROJECT_ID
```

If you see permission errors, switch to the correct account or configuration.

## Deploy

From the project root with `.env` filled in:

**PowerShell (Windows):**

```powershell
.\scripts\deploy.ps1
```

**Command Prompt (Windows):**

```cmd
scripts\deploy.bat
```

**bash (macOS/Linux):**

```bash
export PROJECT_ID="$GOOGLE_CLOUD_PROJECT"   # or source values from .env
export REVIEWER_PASSWORD=...
export SESSION_SECRET=...
export DEVELOPER_PASSWORD=...
./scripts/deploy_cloud_run.sh
```

Or run the commands in [README.md](README.md) manually after setting account and project.

## After deploy

- Note the Cloud Run URL printed at the end of deploy (submission form field 7).
- Share reviewer credentials (`REVIEWER_USERNAME` / `REVIEWER_PASSWORD`) with assessors as instructed.
- Optional admin credentials (`DEVELOPER_USERNAME` / `DEVELOPER_PASSWORD`) bypass the hosted test quota for maintenance; keep them private.
