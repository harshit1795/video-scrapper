#!/bin/bash
# Start all components of the Tab Video Capture toolchain

set -e
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "╔════════════════════════════════════════╗"
echo "║      Tab Video Capture Toolchain       ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Check FFmpeg
if ! command -v ffmpeg &>/dev/null; then
  echo "❌ FFmpeg not found. Install with: brew install ffmpeg"
  exit 1
fi

# Start backend in background
echo "🚀 Starting Python backend..."
cd "$PROJECT_DIR/backend"
pip3 install -r requirements.txt -q
python3 main.py &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"

# Wait for backend to be ready
sleep 2
if curl -s http://localhost:8765/api/health > /dev/null; then
  echo "   ✅ Backend ready at http://localhost:8765"
else
  echo "   ⚠️  Backend may still be starting..."
fi

echo ""
echo "📱 Starting Flutter app..."
cd "$PROJECT_DIR/flutter_frontend"
flutter run -d macos &
FLUTTER_PID=$!

echo ""
echo "════════════════════════════════════════"
echo "✅ Toolchain running!"
echo "   Backend PID : $BACKEND_PID"
echo "   Flutter PID : $FLUTTER_PID"
echo ""
echo "📌 Next: Load chrome_extension/ in Chrome"
echo "   chrome://extensions → Load unpacked"
echo "════════════════════════════════════════"
echo ""
echo "Press Ctrl+C to stop all processes"

# Wait and cleanup
trap "echo ''; echo 'Stopping...'; kill $BACKEND_PID $FLUTTER_PID 2>/dev/null; exit 0" INT
wait

