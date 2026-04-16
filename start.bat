@echo off
echo === Starting jpReader ===
echo.

REM Kill any previous jpReader backend/frontend processes
taskkill /FI "WINDOWTITLE eq jpReader Backend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq jpReader Frontend*" /F >nul 2>&1
REM Also kill any orphaned process still holding port 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING"') do taskkill /F /PID %%a >nul 2>&1
timeout /t 1 /nobreak >nul

REM Start backend
echo Starting Python backend (port 8000)...
start "jpReader Backend" cmd /k "cd /d %~dp0backend && call venv\Scripts\activate.bat && uvicorn main:app --reload --host 0.0.0.0 --port 8000"

REM Wait a moment for backend to start
timeout /t 2 /nobreak >nul

REM Start frontend
echo Starting Angular frontend (port 4200)...
start "jpReader Frontend" cmd /k "cd /d %~dp0frontend && npm start"

echo.
echo jpReader is starting...
echo  Backend:  http://localhost:8000
echo  Frontend: http://localhost:4200
echo  API Docs: http://localhost:8000/docs
echo.
timeout /t 4 /nobreak >nul
start http://localhost:4200
