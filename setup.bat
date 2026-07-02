@echo off
echo === LNreader Setup ===
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ from python.org
    pause
    exit /b 1
)

REM Check Node
node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js not found. Install from nodejs.org
    pause
    exit /b 1
)

echo [1/4] Creating backend virtual environment...
cd backend
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat
echo [2/4] Installing Python dependencies...
pip install -r requirements.txt --quiet

echo [3/4] Setting up .env file...
if not exist .env (
    copy .env.example .env
    echo.
    echo IMPORTANT: Edit backend\.env and set your Google OAuth credentials!
    echo  - GOOGLE_CLIENT_ID
    echo  - GOOGLE_CLIENT_SECRET
    echo  - JWT_SECRET (any long random string)
    echo.
)

cd ..
echo [4/4] Installing Angular dependencies...
cd frontend
call npm install --silent
cd ..

echo.
echo === Setup complete! ===
echo.
echo To start the app, run: start.bat
echo.
echo Before starting, make sure to:
echo 1. Edit backend\.env with your Google OAuth credentials
echo 2. In Google Cloud Console, add http://localhost:8000/auth/callback as redirect URI
echo.
pause
