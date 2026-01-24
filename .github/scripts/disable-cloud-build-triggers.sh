#!/usr/bin/env bash
# Disable Cloud Build triggers so GitHub Actions is the single deployment source.
# Run once after switching to GitHub Actions CI/CD.
#
# Prerequisites: gcloud CLI, authenticated to project gitguide-backend
#
# Usage: from repo root: ./.github/scripts/disable-cloud-build-triggers.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

PROJECT_ID="${GCP_PROJECT_ID:-gitguide-backend}"

echo "Disabling Cloud Build triggers for $PROJECT_ID..."

# Trigger names (from: gcloud builds triggers list)
API_TRIGGER="rmgpgab-gitguide-api-us-central1-prabhakar1234pr-ai-tutor-folwi"
ROADMAP_TRIGGER="rmgpgab-gitguide-roadmap-us-central1-prabhakar1234pr-ai-tutocvd"

for name in "$API_TRIGGER" "$ROADMAP_TRIGGER"; do
  if gcloud builds triggers describe "$name" --project="$PROJECT_ID" &>/dev/null; then
    gcloud builds triggers delete "$name" --project="$PROJECT_ID" --quiet
    echo "Deleted trigger: $name"
  else
    echo "Trigger not found (already deleted?): $name"
  fi
done

echo "Done. GitHub Actions is now the single deployment source."
