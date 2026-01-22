#!/bin/bash
# Script to create the workspace VM and get connection details

set -e

echo "🚀 Creating GitGuide Workspace VM..."

# 1. Create Compute Engine VM for workspaces
echo "Creating VM instance..."
gcloud compute instances create gitguide-workspaces \
  --zone=us-central1-a \
  --machine-type=e2-small \
  --boot-disk-size=50GB \
  --boot-disk-type=pd-ssd \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --tags=http-server,https-server

# 2. Configure firewall for VM
echo "Configuring firewall rules..."
gcloud compute firewall-rules create allow-gitguide-workspaces \
  --allow=tcp:8080,tcp:30001-30010 \
  --target-tags=http-server \
  --source-ranges=0.0.0.0/0 \
  2>/dev/null || echo "Firewall rule may already exist"

# 3. Wait for VM to be ready
echo "Waiting for VM to start..."
sleep 30

# 4. Get VM external IP
echo ""
echo "✅ VM created successfully!"
echo ""
echo "📋 VM Details:"
echo "=============="
EXTERNAL_IP=$(gcloud compute instances describe gitguide-workspaces \
  --zone=us-central1-a \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo "VM_HOST: $EXTERNAL_IP"
echo ""
echo "Next steps:"
echo "1. Add VM_HOST=$EXTERNAL_IP to GitHub secrets"
echo "2. Generate SSH key: ssh-keygen -t rsa -b 4096 -f ~/.ssh/gitguide_deploy"
echo "3. Add public key to VM and use private key for VM_SSH_KEY secret"
echo "4. Determine your VM_USER (usually your GCP username)"
