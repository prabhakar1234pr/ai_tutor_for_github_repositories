# Setting Up HTTPS for VM Workspace Service

This guide shows how to add HTTPS to your GCP VM so WebSocket connections work from your Vercel frontend.

## Option 1: GCP Load Balancer (Recommended for Production)

### Step 1: Reserve a Static IP

```bash
gcloud compute addresses create gitguide-workspaces-ip \
  --region=us-central1
```

Get the IP:
```bash
gcloud compute addresses describe gitguide-workspaces-ip \
  --region=us-central1 \
  --format='get(address)'
```

### Step 2: Create a Health Check

```bash
gcloud compute health-checks create http gitguide-workspaces-health \
  --port=8080 \
  --request-path=/health \
  --check-interval=10s \
  --timeout=5s \
  --unhealthy-threshold=3 \
  --healthy-threshold=2
```

### Step 3: Create a Backend Service

```bash
# Create instance group
gcloud compute instance-groups unmanaged create gitguide-workspaces-group \
  --zone=us-central1-a

# Add your VM to the group
gcloud compute instance-groups unmanaged add-instances gitguide-workspaces-group \
  --zone=us-central1-a \
  --instances=gitguide-workspaces

# Create named port
gcloud compute instance-groups unmanaged set-named-ports gitguide-workspaces-group \
  --zone=us-central1-a \
  --named-ports=http:8080

# Create backend service
gcloud compute backend-services create gitguide-workspaces-backend \
  --protocol=HTTP \
  --health-checks=gitguide-workspaces-health \
  --port-name=http \
  --global

# Add instance group to backend service
gcloud compute backend-services add-backend gitguide-workspaces-backend \
  --global \
  --instance-group=gitguide-workspaces-group \
  --instance-group-zone=us-central1-a
```

### Step 4: Create URL Map

```bash
gcloud compute url-maps create gitguide-workspaces-map \
  --default-service=gitguide-workspaces-backend
```

### Step 5: Create SSL Certificate

You have two options:

#### Option A: Google-Managed Certificate (Easiest)

```bash
# Create certificate (requires domain)
gcloud compute ssl-certificates create gitguide-workspaces-cert \
  --domains=workspaces.yourdomain.com \
  --global

# Note: You'll need to verify domain ownership in Google Search Console
```

#### Option B: Self-Managed Certificate (Quick Setup)

```bash
# Generate certificate using Let's Encrypt (run on VM)
# SSH into your VM first
sudo apt-get update
sudo apt-get install -y certbot

# Get certificate (replace with your domain)
sudo certbot certonly --standalone -d workspaces.yourdomain.com

# Upload to GCP
gcloud compute ssl-certificates create gitguide-workspaces-cert \
  --certificate=/etc/letsencrypt/live/workspaces.yourdomain.com/fullchain.pem \
  --private-key=/etc/letsencrypt/live/workspaces.yourdomain.com/privkey.pem \
  --global
```

### Step 6: Create HTTPS Target Proxy

```bash
gcloud compute target-https-proxies create gitguide-workspaces-https-proxy \
  --url-map=gitguide-workspaces-map \
  --ssl-certificates=gitguide-workspaces-cert
```

### Step 7: Create Forwarding Rule

```bash
gcloud compute forwarding-rules create gitguide-workspaces-https-rule \
  --address=gitguide-workspaces-ip \
  --target-https-proxy=gitguide-workspaces-https-proxy \
  --ports=443 \
  --global
```

### Step 8: Update DNS

Point your domain to the static IP:
```
workspaces.yourdomain.com -> <static-ip-from-step-1>
```

### Step 9: Update Frontend Environment Variable

In Vercel, update:
```
NEXT_PUBLIC_WORKSPACE_API_BASE_URL=https://workspaces.yourdomain.com
```

---

## Option 2: Quick Workaround (Development Only)

If you don't have a domain yet, you can use a temporary solution:

### Use Cloudflare Tunnel (Free)

1. Sign up for Cloudflare (free)
2. Install `cloudflared` on your VM:
   ```bash
   curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
   chmod +x cloudflared
   sudo mv cloudflared /usr/local/bin/
   ```

3. Run tunnel:
   ```bash
   cloudflared tunnel --url http://localhost:8080
   ```

   This gives you a temporary HTTPS URL like: `https://xxxxx.trycloudflare.com`

4. Update frontend:
   ```
   NEXT_PUBLIC_WORKSPACE_API_BASE_URL=https://xxxxx.trycloudflare.com
   ```

**Note:** Cloudflare tunnel URLs change on restart. For production, use Option 1.

---

## Option 3: Use Cloud Run Instead of VM (Alternative)

If Load Balancer setup is too complex, you can deploy the workspace service to Cloud Run:

1. Create a Dockerfile for workspace service
2. Deploy to Cloud Run (automatically gets HTTPS)
3. Update frontend to use Cloud Run URL

This requires refactoring to work with Cloud Run's stateless model (workspace containers would need to be managed differently).

---

## Verification

After setup, test:

```bash
# Test HTTPS endpoint
curl https://workspaces.yourdomain.com/health

# Test WebSocket (in browser console)
const ws = new WebSocket('wss://workspaces.yourdomain.com/api/terminal/workspace-id/connect?token=...');
```

---

## Cost Estimate

- Load Balancer: ~$18/month (always on)
- SSL Certificate: Free (Google-managed) or ~$0 (Let's Encrypt)
- **Total: ~$18/month additional**

---

## Troubleshooting

### Health Check Failing
- Verify VM firewall allows port 8080
- Check `/health` endpoint returns 200
- Verify service is running: `sudo systemctl status gitguide-workspaces`

### SSL Certificate Issues
- Wait 10-15 minutes for Google-managed cert to provision
- Verify DNS is pointing to correct IP
- Check certificate status: `gcloud compute ssl-certificates describe gitguide-workspaces-cert --global`

### WebSocket Still Blocked
- Ensure using `wss://` (not `ws://`)
- Check browser console for mixed content errors
- Verify CORS allows your Vercel domain
