#!/bin/bash

# Always run from the project folder, regardless of where it's invoked from.
cd "$(dirname "$0")"

echo "🚀 Starting Veriify..."
echo ""

# Start PostgreSQL
echo "📦 Starting PostgreSQL..."
brew services start postgresql@17
sleep 2

# Check if veriify database exists, create if not
echo "🗄️ Checking database..."
psql -d veriify -c "SELECT 1;" > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Creating veriify database..."
    python3 setup_db.py
fi

# Check if Ollama is running
echo "🤖 Starting Ollama..."
pgrep -x ollama > /dev/null || ollama serve &
sleep 2

# Start FastAPI backend
echo "⚡ Starting Veriify backend..."
python3 app.py &
BACKEND_PID=$!
sleep 3

# Check if ngrok is installed
if command -v ngrok &> /dev/null; then
    echo ""
    echo "🌐 Starting ngrok tunnel..."
    echo ""
    echo "════════════════════════════════════"
    echo "  Share this link with your friends:"
    echo "════════════════════════════════════"
    ngrok http 8000
else
    echo ""
    echo "════════════════════════════════════"
    echo "  App running at: http://localhost:8000"
    echo "  Install ngrok to share publicly:"
    echo "  brew install ngrok"
    echo "════════════════════════════════════"
    wait $BACKEND_PID
fi
