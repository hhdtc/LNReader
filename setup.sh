#!/bin/bash
set -e

echo "=== jpReader Setup ==="

# Backend
echo "[1/3] Setting up Python backend..."
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -q

if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "IMPORTANT: Edit backend/.env and fill in:"
    echo "  GOOGLE_CLIENT_ID"
    echo "  GOOGLE_CLIENT_SECRET"
    echo "  JWT_SECRET"
fi

cd ..

echo "[2/3] Installing Angular dependencies..."
cd frontend
npm install --silent
cd ..

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Before starting:"
echo "  1. Edit backend/.env with your Google OAuth credentials"
echo "  2. In Google Cloud Console, add http://localhost:8000/auth/callback as redirect URI"
echo ""
echo "Run ./start.sh to launch the app."
