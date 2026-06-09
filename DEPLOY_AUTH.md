# Deploy auth: personal vs business Google account

Your Cloud Run project ID lives in **`.env`** as `GOOGLE_CLOUD_PROJECT` (see `.env.example`). Do not commit the real value.

`gcloud` may default to your **business** account (`deep-person-licensing`, etc.) while the take-home project is on your **personal** account.

Cloud Run deploy will fail until `gcloud` uses the personal account that owns the project in `.env`.

## One-time: add personal account to gcloud

In **your own terminal** (browser login required):

```powershell
gcloud auth login
```

Sign in with the **personal** Google account that owns your GCP project.

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

(`YOUR_GCP_PROJECT_ID` = value of `GOOGLE_CLOUD_PROJECT` in `.env`.)

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
- **project:** matches `GOOGLE_CLOUD_PROJECT` in `.env`

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
