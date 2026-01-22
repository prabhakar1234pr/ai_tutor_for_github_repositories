# Backend Logs Debugging Guide

How to check and debug your GCP backend logs.

## Quick Access Methods

### Method 1: GCP Console (Web UI) - Easiest

#### For Cloud Run Services:

1. **Go to Cloud Run:**
   - [GCP Console](https://console.cloud.google.com) → **Cloud Run**
   - Or direct link: https://console.cloud.google.com/run

2. **Select Your Service:**
   - Click on `gitguide-api` (main API)
   - Or `gitguide-roadmap` (roadmap service)

3. **View Logs:**
   - Click **"LOGS"** tab at the top
   - Or click **"View Logs"** button
   - This opens Cloud Logging

4. **Filter Logs:**
   - Use the filter bar to search for errors
   - Example filters:
     - `severity>=ERROR` - Show only errors
     - `textPayload=~"error"` - Search for "error" text
     - `timestamp>="2026-01-22T00:00:00Z"` - Filter by time

#### For Workspace VM:

1. **Go to Compute Engine:**
   - [GCP Console](https://console.cloud.google.com) → **Compute Engine** → **VM instances**
   - Click on `gitguide-workspaces`

2. **View Logs:**
   - Click **"SSH"** button to connect
   - Or click **"View logs"** in the VM details

3. **Check Systemd Service Logs:**
   ```bash
   sudo journalctl -u gitguide-workspaces -f  # Follow logs in real-time
   sudo journalctl -u gitguide-workspaces -n 100  # Last 100 lines
   ```

---

### Method 2: Command Line (gcloud) - Fastest

#### Check Cloud Run Logs:

```bash
# View recent logs for API service
gcloud run services logs read gitguide-api --region=us-central1 --limit=50

# View recent logs for Roadmap service
gcloud run services logs read gitguide-roadmap --region=us-central1 --limit=50

# Follow logs in real-time (like tail -f)
gcloud run services logs tail gitguide-api --region=us-central1

# Filter for errors only
gcloud run services logs read gitguide-api --region=us-central1 --limit=100 | grep -i error

# View logs from last hour
gcloud run services logs read gitguide-api --region=us-central1 --limit=500 --since=1h
```

#### Check VM Service Logs:

```bash
# SSH into VM and check systemd logs
gcloud compute ssh gitguide-workspaces --zone=us-central1-a --command="sudo journalctl -u gitguide-workspaces -n 100 --no-pager"

# Follow logs in real-time
gcloud compute ssh gitguide-workspaces --zone=us-central1-a --command="sudo journalctl -u gitguide-workspaces -f"
```

---

## Method 3: Cloud Logging (Advanced)

### Access Cloud Logging Directly:

1. **Go to Cloud Logging:**
   - [GCP Console](https://console.cloud.google.com/logs)
   - Or: GCP Console → **Logging** → **Logs Explorer**

2. **Filter by Resource:**
   - Resource type: `Cloud Run Revision`
   - Resource name: `gitguide-api` or `gitguide-roadmap`

3. **Use Query Language:**
   ```
   resource.type="cloud_run_revision"
   resource.labels.service_name="gitguide-api"
   severity>=ERROR
   ```

---

## Common Debugging Scenarios

### 1. Check for API Errors

**In GCP Console:**
```
Cloud Run → gitguide-api → LOGS → Filter: severity>=ERROR
```

**Command Line:**
```bash
gcloud run services logs read gitguide-api --region=us-central1 --limit=200 | grep -i -E "(error|exception|failed|500|400)"
```

### 2. Check Recent Requests

**Command Line:**
```bash
# Last 50 log entries
gcloud run services logs read gitguide-api --region=us-central1 --limit=50

# With timestamps
gcloud run services logs read gitguide-api --region=us-central1 --limit=50 --format="table(timestamp,textPayload)"
```

### 3. Check Specific Endpoint Errors

**In Cloud Logging:**
```
Filter: textPayload=~"/api/projects/create" AND severity>=ERROR
```

**Command Line:**
```bash
gcloud run services logs read gitguide-api --region=us-central1 --limit=500 | grep -A 5 -B 5 "/api/projects/create"
```

### 4. Check VM Service Status

**Command Line:**
```bash
# Check if service is running
gcloud compute ssh gitguide-workspaces --zone=us-central1-a --command="sudo systemctl status gitguide-workspaces --no-pager"

# View recent errors
gcloud compute ssh gitguide-workspaces --zone=us-central1-a --command="sudo journalctl -u gitguide-workspaces -p err --no-pager -n 50"
```

### 5. Check Database Connection Issues

**In Cloud Logging:**
```
Filter: textPayload=~"(database|supabase|connection|timeout)"
```

**Command Line:**
```bash
gcloud run services logs read gitguide-api --region=us-central1 --limit=500 | grep -i -E "(database|supabase|connection|timeout)"
```

---

## Useful Log Filters

### In Cloud Logging (GCP Console):

```
# All errors
severity>=ERROR

# Specific error message
textPayload=~"ImportError"

# Time range (last hour)
timestamp>="2026-01-22T23:00:00Z"

# Combine filters
resource.labels.service_name="gitguide-api" AND severity>=ERROR AND textPayload=~"500"
```

### Command Line Filters:

```bash
# Errors only
gcloud run services logs read gitguide-api --region=us-central1 --limit=500 | grep -i error

# Exceptions
gcloud run services logs read gitguide-api --region=us-central1 --limit=500 | grep -i exception

# HTTP 500 errors
gcloud run services logs read gitguide-api --region=us-central1 --limit=500 | grep "500"

# Specific time range
gcloud run services logs read gitguide-api --region=us-central1 --since=2h --limit=500
```

---

## Quick Debugging Commands

### Check All Services Status:

```bash
# Cloud Run services
gcloud run services list --region=us-central1

# VM status
gcloud compute instances describe gitguide-workspaces --zone=us-central1-a --format="value(status)"
```

### Check Recent Errors Across All Services:

```bash
# API service errors
echo "=== API Service Errors ==="
gcloud run services logs read gitguide-api --region=us-central1 --limit=100 | grep -i error | tail -20

# Roadmap service errors
echo "=== Roadmap Service Errors ==="
gcloud run services logs read gitguide-roadmap --region=us-central1 --limit=100 | grep -i error | tail -20

# VM service errors
echo "=== VM Service Errors ==="
gcloud compute ssh gitguide-workspaces --zone=us-central1-a --command="sudo journalctl -u gitguide-workspaces -p err --no-pager -n 20"
```

---

## Export Logs for Analysis

### Export to File:

```bash
# Export API logs to file
gcloud run services logs read gitguide-api --region=us-central1 --limit=1000 > api_logs.txt

# Export with timestamps
gcloud run services logs read gitguide-api --region=us-central1 --limit=1000 --format=json > api_logs.json
```

---

## Real-Time Monitoring

### Watch Logs Live:

```bash
# Cloud Run - live tail
gcloud run services logs tail gitguide-api --region=us-central1

# VM - live tail
gcloud compute ssh gitguide-workspaces --zone=us-central1-a --command="sudo journalctl -u gitguide-workspaces -f"
```

---

## Troubleshooting Common Issues

### Issue: Can't See Logs

**Solution:**
- Ensure you're logged in: `gcloud auth login`
- Check project: `gcloud config get-value project`
- Verify service name: `gcloud run services list --region=us-central1`

### Issue: Too Many Logs

**Solution:**
- Use filters: `severity>=ERROR`
- Limit results: `--limit=50`
- Use time range: `--since=1h`

### Issue: Logs Not Showing Recent Errors

**Solution:**
- Check log retention (Cloud Run keeps logs for 30 days)
- Try different time ranges
- Check if service is actually receiving requests

---

## Quick Reference

| Service | Log Location | Command |
|---------|-------------|---------|
| **API** | Cloud Run → gitguide-api → LOGS | `gcloud run services logs read gitguide-api --region=us-central1` |
| **Roadmap** | Cloud Run → gitguide-roadmap → LOGS | `gcloud run services logs read gitguide-roadmap --region=us-central1` |
| **VM** | Compute Engine → VM → SSH | `gcloud compute ssh gitguide-workspaces --zone=us-central1-a` then `sudo journalctl -u gitguide-workspaces` |

---

## Pro Tips

1. **Use Cloud Logging UI** for visual filtering and searching
2. **Use command line** for quick checks and automation
3. **Set up log-based alerts** in GCP for critical errors
4. **Export logs** if you need to share with team or analyze offline
5. **Check logs immediately after deployment** to catch issues early

---

## Next Steps

After identifying errors in logs:
1. Check the error message and stack trace
2. Look for related errors around the same time
3. Check if it's a configuration issue (env vars, CORS, etc.)
4. Test the specific endpoint that's failing
5. Fix the code and redeploy
