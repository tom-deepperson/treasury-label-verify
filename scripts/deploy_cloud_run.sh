#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-east1}"
SERVICE="treasury-label-verify"

gcloud builds submit --tag "gcr.io/${PROJECT_ID}/${SERVICE}"

gcloud run deploy "${SERVICE}" \
  --image "gcr.io/${PROJECT_ID}/${SERVICE}" \
  --platform managed \
  --region "${REGION}" \
  --allow-unauthenticated \
  --min-instances 1 \
  --memory 2Gi \
  --timeout 300 \
  --set-env-vars "REVIEWER_USERNAME=${REVIEWER_USERNAME:-treasury},MAX_TESTS=50,USAGE_STORE=file,WARM_OCR=1" \
  --set-env-vars "REVIEWER_PASSWORD=${REVIEWER_PASSWORD:?Set REVIEWER_PASSWORD},SESSION_SECRET=${SESSION_SECRET:?Set SESSION_SECRET}" \
  --set-env-vars "DEVELOPER_USERNAME=${DEVELOPER_USERNAME:-developer},DEVELOPER_PASSWORD=${DEVELOPER_PASSWORD:-}" \
  --set-env-vars "OPENAI_API_KEY=${OPENAI_API_KEY:-},ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-},GEMINI_API_KEY=${GEMINI_API_KEY:-}"

echo "Deployed. Fetch URL with:"
echo "gcloud run services describe ${SERVICE} --region ${REGION} --format='value(status.url)'"
