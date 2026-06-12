#!/bin/bash
echo "Stopping Veriify..."
pkill -f "python3 app.py" 2>/dev/null
pkill -f "uvicorn" 2>/dev/null
pkill -f "ngrok" 2>/dev/null
echo "✅ Veriify stopped"
