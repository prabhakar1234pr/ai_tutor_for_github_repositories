# PowerShell script to create the workspace VM and get connection details

Write-Host "🚀 Creating GitGuide Workspace VM..." -ForegroundColor Green

# 1. Create Compute Engine VM for workspaces
Write-Host "Creating VM instance..." -ForegroundColor Yellow
gcloud compute instances create gitguide-workspaces `
  --zone=us-central1-a `
  --machine-type=e2-small `
  --boot-disk-size=50GB `
  --boot-disk-type=pd-ssd `
  --image-family=ubuntu-2204-lts `
  --image-project=ubuntu-os-cloud `
  --tags=http-server,https-server

# 2. Configure firewall for VM
Write-Host "Configuring firewall rules..." -ForegroundColor Yellow
gcloud compute firewall-rules create allow-gitguide-workspaces `
  --allow=tcp:8080,tcp:30001-30010 `
  --target-tags=http-server `
  --source-ranges=0.0.0.0/0 `
  2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Firewall rule may already exist" -ForegroundColor Yellow
}

# 3. Wait for VM to be ready
Write-Host "Waiting for VM to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 30

# 4. Get VM external IP
Write-Host ""
Write-Host "✅ VM created successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 VM Details:" -ForegroundColor Cyan
Write-Host "==============" -ForegroundColor Cyan

$EXTERNAL_IP = gcloud compute instances describe gitguide-workspaces `
  --zone=us-central1-a `
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'

Write-Host "VM_HOST: $EXTERNAL_IP" -ForegroundColor White
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Add VM_HOST=$EXTERNAL_IP to GitHub secrets"
Write-Host "2. Generate SSH key: ssh-keygen -t rsa -b 4096 -f ~/.ssh/gitguide_deploy"
Write-Host "3. Add public key to VM and use private key for VM_SSH_KEY secret"
Write-Host "4. Determine your VM_USER (usually your GCP username)"
