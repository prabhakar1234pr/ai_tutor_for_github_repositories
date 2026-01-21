#!/bin/bash
# Helper script to show server URLs for common ports
# Usage: source show_server_url.sh or . show_server_url.sh

echo ""
echo "🌐 Server URLs (if your app is running on these ports):"
echo "   Port 3000: http://localhost:3000"
echo "   Port 5000: http://localhost:5000"
echo "   Port 8000: http://localhost:8000"
echo ""
echo "💡 Tip: Modify your server.js to output the URL when it starts:"
echo "   console.log('Server listening on port 5000');"
echo "   console.log('🌐 Open http://localhost:5000 in your browser');"
echo ""
