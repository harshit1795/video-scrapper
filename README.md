# 📹 Video Scrapper

> A local video & audio capture toolchain built by **Harshit Gola** that captures media directly from active browser tabs with zero OS-level screen recording permissions.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![Flutter](https://img.shields.io/badge/Flutter-3.x-02569B.svg)](https://flutter.dev/)
[![Chrome Extension](https://img.shields.io/badge/Manifest-V3-brightgreen.svg)](https://developer.chrome.com/docs/extensions/mv3/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-7.x-green.svg)](https://ffmpeg.org/)
[![Creator](https://img.shields.io/badge/Creator-Harshit%20Gola-6C63FF.svg)](#creator)

---

## 💡 The Use Case

### Why Video Scrapper?

Traditional screen recording tools (OBS, QuickTime, macOS Screen Capture) suffer from several major pain points when saving web media:
1. **Intrusive OS Permissions:** They require system-level "Screen Recording" and "Accessibility" permissions, which expose everything on your display (notifications, personal tabs, other windows).
2. **Audio Routing Headaches:** Capturing crisp, internal computer audio usually demands complex virtual audio drivers like BlackHole, Soundflower, or VB-Cable.
3. **Window Obstructions:** Any notification pop-up or window overlaying the video ruins the capture.
4. **Heavy Resource Overhead:** Capturing full desktop displays strains GPU and CPU resources.

### The Solution

**Video Scrapper** bypasses OS-level capture entirely:
* **Tab-Level Isolation:** Leverages the Chromium `chrome.tabCapture` API to tap directly into the active tab's media feed at up to 1080p 60FPS.
* **Pure Digital Audio Passthrough:** Captures 48 kHz stereo digital audio directly from the browser tab without virtual drivers, while keeping your speakers unmuted through Web Audio API routing (`AudioContext.destination`).
* **Real-Time Streaming Pipeline:** Media chunks stream immediately over a local WebSocket to a Python backend, converting on the fly via FFmpeg into a standard, seekable **H.264 / AAC `.mp4`** file.
* **Central Desktop Control Panel:** A Flutter desktop app gives you real-time recording telemetry, session stats, and a video playback gallery.

---

## 🏛 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       CHROME BROWSER                        │
│                                                             │
│  [ Active Tab (YouTube/Vimeo/Stream) ]                      │
│                │                                            │
│                │  chrome.tabCapture.getMediaStreamId()       │
│                ▼                                            │
│  [ Extension Service Worker: background.js ]                │
│                │                                            │
│                ▼                                            │
│  [ Offscreen Document: offscreen.html / offscreen.js ]       │
│      ├── navigator.mediaDevices.getUserMedia()              │
│      ├── AudioContext (mirrors audio to local speakers)     │
│      ├── MediaRecorder (1-second WebM chunks)               │
│      └── WebSocket Client                                   │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ ws://localhost:8765/ws/stream (Binary Chunks)
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                   PYTHON FASTAPI BACKEND                    │
│                                                             │
│  [ WebSocket Receiver (/ws/stream) ]                        │
│      ├── Concurrently writes backup to temp/{id}.webm       │
│      └── Pipes WebM into FFmpeg stdin (pipe:0)               │
│                                                             │
│  [ FFmpeg Real-Time Transcoder ]                            │
│      └── Encodes H.264 (CRF 23) + AAC (128k)                │
│      └── Outputs standard MP4 (+faststart) to recordings/   │
│                                                             │
│  [ REST API Layer ]                                         │
│      ├── GET /api/health                                    │
│      ├── GET /api/status (recording state, duration, bytes) │
│      ├── GET /api/recordings (list saved videos + metadata) │
│      ├── GET /recordings/{file} (stream video playback)     │
│      └── DELETE /api/recordings/{file} (delete recording)   │
└────────────────▲────────────────────────────────────────────┘
                 │
                 │ REST Polling (2s heartbeat) & Video Streaming
                 │
┌────────────────┴────────────────────────────────────────────┐
│                    FLUTTER DESKTOP APP                      │
│                                                             │
│  [ Status Card ] ── Live indicator (Online / 🔴 Recording)  │
│  [ Recordings Gallery ] ── Video list, durations & playback │
│  [ Instructions Panel ] ── Built-in workflow guide          │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 Repository Structure

```
Video Scrapper/
├── README.md                      # Documentation & Architecture
├── start_all.sh                   # One-shot script to run Backend + Flutter App
│
├── chrome_extension/              # Chrome MV3 Extension
│   ├── manifest.json              # MV3 configuration (tabCapture, offscreen, storage)
│   ├── background.js              # Service Worker orchestrating tab streams
│   ├── offscreen.html             # Hidden DOM context for MediaRecorder
│   ├── offscreen.js               # getUserMedia, AudioContext routing & WebSocket streaming
│   ├── popup.html / popup.js      # Popup interface with live status and start/stop buttons
│   └── icons/                     # Extension icons
│
├── backend/                       # Python FastAPI Backend
│   ├── main.py                    # WebSocket server + FFmpeg ingestion & fallback pipeline
│   ├── requirements.txt           # Python dependencies (FastAPI, Uvicorn, WebSockets, etc.)
│   ├── test_e2e.py                # Automated end-to-end integration test suite
│   ├── start.sh                   # Backend startup script
│   ├── temp/                      # Backup raw WebM stream cache
│   └── recordings/                # Final output directory for transcoded .mp4 files
│
└── flutter_frontend/              # Flutter Desktop Control Panel
    ├── lib/
    │   ├── main.dart              # App entrypoint & dark theme configuration
    │   ├── models/                # RecordingStatus & VideoFile models (with duration parsing)
    │   ├── services/              # ApiService (REST client)
    │   ├── providers/             # RecordingProvider (2s polling & reactive state)
    │   ├── screens/               # HomeScreen
    │   └── widgets/               # StatusCard, RecordingsPanel, InstructionsPanel
    └── macos/Runner/              # macOS entitlements (network client & server enabled)
```

---

## 🛠 Prerequisites

Before running the application, make sure you have the following installed:

1. **FFmpeg** (required for video transcoding and metadata probing):
   ```bash
   # On macOS using Homebrew:
   brew install ffmpeg
   ```
2. **Python 3.10+**:
   ```bash
   python3 --version
   ```
3. **Flutter 3.x** (with desktop support):
   ```bash
   flutter --version
   ```
4. **Google Chrome** (or any Chromium-based browser like Brave, Edge).

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/harshit1795/video-scrapper.git
cd "video-scrapper"
```

### 2. Run the Full Application (One-Command Launcher)

Video Scrapper includes a unified launch script that sets up dependencies, starts the Python FastAPI server, and launches the Flutter desktop app simultaneously:

```bash
chmod +x start_all.sh
./start_all.sh
```

---

### 3. Running Components Individually (Alternative)

If you prefer to run each service in its own terminal window:

#### Terminal 1 — Python FastAPI Backend
```bash
cd backend
chmod +x start.sh
./start.sh
```
*The server will start on `http://localhost:8765`.*

#### Terminal 2 — Flutter Desktop Control Panel
```bash
cd flutter_frontend
flutter pub get
flutter run -d macos
```

---

### 4. Load the Chrome Extension

1. Open **Google Chrome** and navigate to:
   ```text
   chrome://extensions
   ```
2. Toggle on **Developer mode** in the top-right corner.
3. Click the **Load unpacked** button (top-left).
4. Select the `chrome_extension` folder from your cloned repository:
   ```text
   /path/to/video-scrapper/chrome_extension
   ```
5. Pin the **Tab Video Capture** icon (📹) to your Chrome toolbar.

---

## 🎬 How to Capture Videos

1. **Open Media:** Navigate to any tab where a video is playing (YouTube, Vimeo, Twitch, internal players, etc.).
2. **Start Capture:** Click the extension icon in Chrome and click **▶ Start Capture**.
   * Tab audio will continue playing normally through your speakers while the stream is recorded.
   * Your Flutter desktop app will immediately update to show:
     ```text
     🔴 Recording Active Tab — Xs elapsed — Y MB received
     ```
3. **Stop & Save:** When done, click the extension icon and select **⏹ Stop Capture**.
4. **Playback:** The finalized H.264/AAC `.mp4` video will appear in the Flutter app's **Recorded Videos** gallery showing its filename, size, and duration.
   * Click the **Open/Play** icon to watch your recording in your browser or default media player.
   * Files are stored on disk in `backend/recordings/`.

---

## 🧪 Automated Testing

Video Scrapper includes a complete end-to-end integration test that verifies synthetic stream generation, WebSocket streaming, FFmpeg transcoding, and REST API functionality without needing a browser:

```bash
cd backend
python3 test_e2e.py
```

To run the Flutter widget tests:
```bash
cd flutter_frontend
flutter test
```

---

## 👤 Creator

Created by **Harshit Gola**  
GitHub: [@harshit1795](https://github.com/harshit1795)

---

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).
