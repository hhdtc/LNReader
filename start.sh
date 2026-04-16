#!/bin/bash

echo "=== Starting jpReader ==="

# Start backend
cd backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

echo "Backend started (PID $BACKEND_PID)"

# Start frontend
cd frontend
npm start &
FRONTEND_PID=$!
cd ..

echo "Frontend started (PID $FRONTEND_PID)"
echo ""
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:4200"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all services."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" EXIT INT TERM
wait
