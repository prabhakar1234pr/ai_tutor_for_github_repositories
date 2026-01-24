# 403 Forbidden Error - Authentication Fix

## Problem
The main API is getting `403 Forbidden` when calling the roadmap service, indicating the authentication token is not being verified correctly.

## Root Cause
FastAPI/Starlette normalizes HTTP headers to lowercase. When we send `X-Internal-Token`, it may be received as `x-internal-token` in the Request object.

## Solution Applied

### 1. Enhanced Header Detection
Updated `verify_internal_auth()` in `app/roadmap_service.py` to check multiple header name variations:
- `X-Internal-Token` (original)
- `x-internal-token` (lowercase)
- `X-INTERNAL-TOKEN` (uppercase)

### 2. Improved Logging
Added detailed logging to help diagnose issues:
- Logs all header keys received
- Logs token presence and length
- Logs masked token values for security
- Logs full token comparison details on mismatch

### 3. Better Error Messages
Enhanced error logging in `roadmap_client.py`:
- Logs response body on 403 errors
- Logs token being sent (last 20 chars)
- Logs full request details

## Code Changes

### `app/roadmap_service.py`
```python
async def verify_internal_auth(request: Request):
    # Try multiple header name variations
    x_internal_token = (
        request.headers.get("X-Internal-Token")
        or request.headers.get("x-internal-token")
        or request.headers.get("X-INTERNAL-TOKEN")
    )
    # ... detailed logging ...
```

### `app/services/roadmap_client.py`
```python
# Added 403 error logging
if response.status_code == 403:
    logger.error("❌ 403 FORBIDDEN - AUTH FAILED")
    logger.error(f"   Response Body: {response.text}")
    # ... more details ...
```

## Deployment Status

**Commit:** Latest changes pushed to GitHub
**Status:** Waiting for GitHub Actions deployment

## Next Steps

1. **Wait for deployment** - GitHub Actions will deploy both services
2. **Check logs after deployment:**
   ```bash
   # Main API logs
   gcloud run services logs tail gitguide-api --region=us-central1

   # Roadmap service logs
   gcloud run services logs tail gitguide-roadmap --region=us-central1
   ```

3. **Look for these log messages:**
   - `🔐 INTERNAL AUTH VERIFICATION` - Shows token verification
   - `✅ Internal auth token verified successfully` - Success!
   - `❌ NO TOKEN RECEIVED IN HEADERS` - Header not being sent/received
   - `❌ TOKEN MISMATCH` - Tokens don't match (will show full values)

## Troubleshooting

If 403 still occurs after deployment:

1. **Check if token is being sent:**
   - Look in main API logs for: `📤 Sending headers: X-Internal-Token=...`
   - Look in roadmap service logs for: `All headers keys: [...]`

2. **Check if token matches:**
   - Compare token values in logs (first/last 20 chars)
   - Verify both services have the same `INTERNAL_AUTH_TOKEN` env var

3. **Check Cloud Run environment variables:**
   ```bash
   # Main API
   gcloud run services describe gitguide-api --region=us-central1 \
     --format='value(spec.template.spec.containers[0].env)' | grep INTERNAL_AUTH_TOKEN

   # Roadmap Service
   gcloud run services describe gitguide-roadmap --region=us-central1 \
     --format='value(spec.template.spec.containers[0].env)' | grep INTERNAL_AUTH_TOKEN
   ```

4. **Verify tokens match:**
   - Both should have the exact same value
   - No extra whitespace or newlines
   - Same case (though shouldn't matter)

## Expected Behavior After Fix

1. Main API sends request with `X-Internal-Token` header
2. Roadmap service receives header (in any case variation)
3. Token is extracted and compared
4. If match: `✅ Internal auth token verified successfully`
5. Request proceeds to LangGraph workflow

The enhanced logging will show exactly what's happening at each step!
