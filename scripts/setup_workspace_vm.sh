#!/bin/bash
# Initial setup script for workspace VM
# Run this ONCE on the VM before the first deployment

set -e

echo "🚀 Setting up GitGuide Workspace VM..."

# Install Docker
echo "Installing Docker..."
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER

# Install Python 3.10 (default on Ubuntu 22.04)
echo "Installing Python 3.10..."
sudo apt-get install -y python3 python3-venv python3-pip

# Clone repository
echo "Cloning repository..."
sudo mkdir -p /opt
cd /opt
if [ -d "gitguide-backend" ]; then
    echo "Repository already exists, skipping clone..."
else
    sudo git clone https://github.com/prabhakar1234pr/GitGuide-FastAPI.git gitguide-backend
    sudo chown -R $USER:$USER gitguide-backend
fi
cd gitguide-backend

# Setup Python environment
echo "Setting up Python environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install uv
uv pip install -r pyproject.toml

# Build workspace Docker image
echo "Building workspace Docker image..."
docker build -t gitguide-workspace -f docker/Dockerfile.workspace .

# Create systemd service
echo "Creating systemd service..."
sudo tee /etc/systemd/system/gitguide-workspaces.service > /dev/null << 'EOF'
[Unit]
Description=GitGuide Workspaces Service
After=network.target docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/gitguide-backend
ExecStart=/opt/gitguide-backend/.venv/bin/uvicorn app.workspace_service:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable gitguide-workspaces

echo ""
echo "✅ VM setup complete!"
echo ""
echo "⚠️  IMPORTANT: You need to create a .env file with your environment variables"
echo "   at /opt/gitguide-backend/.env before starting the service."
echo ""
echo "Next steps:"
echo "1. Create /opt/gitguide-backend/.env with required environment variables"
echo "2. Start the service: sudo systemctl start gitguide-workspaces"
echo "3. Check status: sudo systemctl status gitguide-workspaces"
