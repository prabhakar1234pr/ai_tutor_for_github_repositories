# Preview Proxy Setup Guide

## Overview

The preview proxy allows users to access development servers running in Docker containers via proxy URLs like:
- `https://workspaces.yourdomain.com/api/preview/{workspace_id}/3000/`

This avoids port conflicts and works for multiple concurrent users.

## Current Status

✅ **Backend Code**: Already implemented
- API routes: `/api/preview/{workspace_id}/{port}/{path}`
- URL generation logic
- Container IP detection and proxying

❌ **Infrastructure**: Needs configuration
- Reverse proxy (nginx or Cloud Load Balancer)
- Domain name and SSL certificates
- Environment variables

## Setup Options

### Option 1: Nginx on VM (Simpler, Good for Testing)

1. **Install Nginx on your VM:**
   ```bash
   sudo apt-get update
   sudo apt-get install -y nginx certbot python3-certbot-nginx
   ```

2. **Create Nginx config** (`/etc/nginx/sites-available/gitguide-workspaces`):
   ```nginx
   server {
       listen 80;
       server_name workspaces.yourdomain.com;
       return 301 https://$server_name$request_uri;
   }

   server {
       listen 443 ssl http2;
       server_name workspaces.yourdomain.com;

       ssl_certificate /etc/letsencrypt/live/workspaces.yourdomain.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/workspaces.yourdomain.com/privkey.pem;

       location / {
           proxy_pass http://127.0.0.1:8080;
           proxy_http_version 1.1;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           proxy_set_header X-Forwarded-Host $host;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_connect_timeout 300s;
           proxy_send_timeout 300s;
           proxy_read_timeout 300s;
       }
   }
   ```

3. **Enable the site:**
   ```bash
   sudo ln -s /etc/nginx/sites-available/gitguide-workspaces /etc/nginx/sites-enabled/
   sudo nginx -t  # Test configuration
   sudo systemctl reload nginx
   ```

4. **Get SSL certificate:**
   ```bash
   sudo certbot --nginx -d workspaces.yourdomain.com
   ```

5. **Set environment variable on VM:**
   ```bash
   # Add to /opt/gitguide-backend/.env or systemd service
   WORKSPACE_PUBLIC_BASE_URL=https://workspaces.yourdomain.com
   ENVIRONMENT=production
   ```

6. **Restart the workspace service:**
   ```bash
   sudo systemctl restart gitguide-workspaces
   ```

### Option 2: GCP Cloud Load Balancer (Production, Scalable)

1. **Create a Cloud Load Balancer:**
   ```bash
   # Create backend service
   gcloud compute backend-services create gitguide-workspaces-backend \
       --protocol HTTP \
       --health-checks gitguide-workspaces-health-check \
       --global

   # Add VM instance as backend
   gcloud compute backend-services add-backend gitguide-workspaces-backend \
       --instance-group gitguide-workspaces-group \
       --instance-group-zone us-central1-a \
       --global

   # Create URL map
   gcloud compute url-maps create gitguide-workspaces-map \
       --default-service gitguide-workspaces-backend

   # Create HTTPS proxy
   gcloud compute target-https-proxies create gitguide-workspaces-https-proxy \
       --url-map gitguide-workspaces-map \
       --ssl-certificates your-ssl-cert

   # Create forwarding rule
   gcloud compute forwarding-rules create gitguide-workspaces-https-rule \
       --global \
       --target-https-proxy gitguide-workspaces-https-proxy \
       --ports 443
   ```

2. **Set environment variable:**
   ```bash
   WORKSPACE_PUBLIC_BASE_URL=https://workspaces.yourdomain.com
   ENVIRONMENT=production
   ```

## How It Works

1. **User starts dev server** in terminal (e.g., `npm run dev` on port 3000)
2. **Backend detects** the server from terminal output
3. **Backend generates URL**: `https://workspaces.yourdomain.com/api/preview/{workspace_id}/3000/`
4. **User clicks Preview button** → Opens proxy URL
5. **Nginx/Load Balancer** → Forwards to FastAPI backend (port 8080)
6. **FastAPI backend** → Proxies to container's internal IP:port
7. **Container** → Serves the dev server response

## Testing

After setup, test with:

```bash
# Check if backend is running
curl http://localhost:8080/health

# Test preview proxy (replace with actual workspace_id and port)
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://workspaces.yourdomain.com/api/preview/{workspace_id}/3000/
```

## Troubleshooting

- **"Connection refused"**: Check if FastAPI backend is running on port 8080
- **"502 Bad Gateway"**: Check nginx/load balancer logs
- **"Container not reachable"**: Verify Docker containers are running and network is accessible
- **URLs still showing localhost**: Check `WORKSPACE_PUBLIC_BASE_URL` environment variable is set

## Local Development

For local development, the system automatically uses `localhost:{host_port}` URLs (e.g., `http://localhost:30001`) when:
- `ENVIRONMENT != "production"` OR
- `WORKSPACE_PUBLIC_BASE_URL` is not set

No reverse proxy needed for local development!
