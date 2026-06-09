# Deploy auth: personal vs business Google account

Project **`YOUR_GCP_PROJECT_ID`** is on your **personal** Google account.  
`gcloud` may default to your **business** account (`deep-person-licensing`, etc.).

Cloud Run deploy will fail until `gcloud` uses the personal account that owns this project.

## One-time: add personal account to gcloud

In **your own terminal** (browser login required):

```powershell
gcloud auth login
```

Sign in with the **personal** Google account that created `YOUR_GCP_PROJECT_ID`.

List accounts:

```powershell
gcloud auth list
```

## Recommended: separate gcloud configuration

Keeps business and personal projects isolated.

```powershell
gcloud config configurations create treasury-personal
gcloud config configurations activate treasury-personal
gcloud config set account YOUR_PERSONAL_EMAIL@gmail.com
gcloud config set project YOUR_GCP_PROJECT_ID
```

Switch back to business later:

```powershell
gcloud config configurations activate default
```

## Verify before deploy

```powershell
gcloud config get-value account
gcloud config get-value project
```

Expected:

- **account:** your personal email
- **project:** `YOUR_GCP_PROJECT_ID`

Quick access check:

```powershell
gcloud projects describe YOUR_GCP_PROJECT_ID
```

If you see permission errors, you are still on the wrong account.

## Deploy

From `E:\dev\treasury-label-verify` with `.env` filled in:

```powershell
cd E:\dev\treasury-label-verify
.\scripts\deploy.ps1
```

Or run the commands in [README.md](README.md) manually after setting account/project.

## After deploy

- Test with **developer** login (unlimited): `DEVELOPER_USERNAME` / `DEVELOPER_PASSWORD`
- Share **reviewer** login with Treasury only: `treasury` / `REVIEWER_PASSWORD`
- Form field 7: Cloud Run URL printed at end of deploy
