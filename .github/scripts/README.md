# Scripts

## disable-cloud-build-triggers.sh

Disables Cloud Build triggers so **GitHub Actions** is the single deployment source.

**When to run:** Once, after switching to GitHub Actions for CI/CD.

**Prerequisites:** `gcloud` CLI, authenticated to `gitguide-backend`.

**Usage (from repo root):**

```bash
chmod +x .github/scripts/disable-cloud-build-triggers.sh
./.github/scripts/disable-cloud-build-triggers.sh
```

Override project: `GCP_PROJECT_ID=my-project ./.github/scripts/disable-cloud-build-triggers.sh`
