# Fix: Vertex AI Embedding Model 404 Error

## Root Cause Found

Your `.env` file has:
```env
GCP_LOCATION=global
```

**Problem:** Vertex AI embedding models require a **specific region** (like `us-central1`), not `"global"`.

The `"global"` location works for some Gemini models but **not for embedding models**.

## Solution

Update your `.env` file:

```env
# Change from:
GCP_LOCATION=global

# To:
GCP_LOCATION=us-central1
```

Or use another supported region:
- `us-central1` (recommended)
- `us-east1`
- `us-west1`
- `europe-west1`
- `asia-southeast1`

## Why This Happens

1. **Gemini models** can use `location="global"` ✅
2. **Embedding models** (textembedding-gecko) require a **specific region** ❌

## Verify Fix

After updating `.env`:

1. Restart containers:
```powershell
docker-compose restart api roadmap workspaces
```

2. Check logs:
```powershell
docker-compose logs -f api | Select-String -Pattern "embedding|Vertex AI"
```

3. You should see:
```
✅ Vertex AI embeddings initialized: textembedding-gecko@003
```

## Match GCP Configuration

**Check your GCP Cloud Run environment variables:**
- What `GCP_LOCATION` is set in Cloud Run?
- If it's `us-central1`, update your local `.env` to match
- If it's `global`, that's the bug - change GCP to `us-central1` too!

This will help you debug if the same issue exists in GCP.
