# Quick Setup: Enable Preview Proxy URLs

Your Cloud Load Balancer is **already configured**! You just need to set one environment variable on your VM.

## ✅ What's Already Working

- ✅ Cloud Load Balancer: `workspaces.gitguide.dev` → `136.110.145.242`
- ✅ SSL Certificate: Active and valid
- ✅ Backend Service: Configured and pointing to VM
- ✅ Instance Group: Named port `http:8080` configured correctly
- ✅ Health Check: Working on port 8080

## 🎯 One Step to Complete Setup

### SSH into VM and Set Environment Variable

```bash
# 1. SSH into your VM
gcloud compute ssh gitguide-workspaces --zone=us-central1-a

# 2. Edit the systemd service file
sudo systemctl edit gitguide-workspaces

# 3. Add these lines in the editor:
[Service]
Environment="WORKSPACE_PUBLIC_BASE_URL=https://workspaces.gitguide.dev"
Environment="ENVIRONMENT=production"

# 4. Save and exit (Ctrl+X, then Y, then Enter)

# 5. Reload systemd and restart service
sudo systemctl daemon-reload
sudo systemctl restart gitguide-workspaces

# 6. Verify it's running
sudo systemctl status gitguide-workspaces

# 7. Check logs to confirm
sudo journalctl -u gitguide-workspaces -f
```

### Alternative: Set in .env file

If your service reads from a `.env` file:

```bash
# SSH into VM
gcloud compute ssh gitguide-workspaces --zone=us-central1-a

# Edit .env file
sudo nano /opt/gitguide-backend/.env

# Add these lines:
WORKSPACE_PUBLIC_BASE_URL=https://workspaces.gitguide.dev
ENVIRONMENT=production

# Save and restart
sudo systemctl restart gitguide-workspaces
```

## ✅ Test It Works

After setting the environment variable and restarting:

1. **Test health endpoint:**
   ```bash
   curl https://workspaces.gitguide.dev/health
   ```
   Should return: `{"status":"healthy","service":"workspaces"}`

2. **Test preview proxy (with auth token):**
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" \
     https://workspaces.gitguide.dev/api/preview/{workspace_id}/3000/
   ```

## 🎉 Result

Once the environment variable is set, the preview panel will automatically:

- **Show proxy URLs in production**: `https://workspaces.gitguide.dev/api/preview/{workspace_id}/{port}/`
- **Show localhost URLs locally**: `http://localhost:30001` (when `ENVIRONMENT != "production"`)

The frontend Preview Ports Panel will automatically detect and display the correct URLs based on the environment!
