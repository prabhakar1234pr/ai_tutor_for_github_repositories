#!/bin/bash
# Set environment variables for preview proxy on the workspace VM.
# Run via: gcloud compute ssh gitguide-workspaces --zone=us-central1-a --command "bash /tmp/vm-set-preview-env.sh"

set -e
sudo mkdir -p /etc/systemd/system/gitguide-workspaces.service.d
printf '%s\n' '[Service]' 'Environment="WORKSPACE_PUBLIC_BASE_URL=https://workspaces.gitguide.dev"' 'Environment="ENVIRONMENT=production"' | sudo tee /etc/systemd/system/gitguide-workspaces.service.d/override.conf > /dev/null
sudo systemctl daemon-reload
sudo systemctl restart gitguide-workspaces
echo "Done. Service restarted."
sudo systemctl status gitguide-workspaces
