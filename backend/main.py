import asyncio
import json
import os
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
RECORDINGS_DIR = BASE_DIR / "recordings"
TEMP_DIR = BASE_DIR / "temp"

RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="Tab Video Capture Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Recording state
# ---------------------------------------------------------------------------
class RecordingState:
    def __init__(self):
        self.is_recording: bool = False
        self.session_id: Optional[str] = None
        self.start_time: Optional[float] = None
        self.current_file: Optional[Path] = None
        self.bytes_received: int = 0
        self.ffmpeg_process: Optional[subprocess.Popen] = None
        self.temp_webm_path: Optional[Path] = None
        self.temp_webm_file = None


state = RecordingState()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class StatusResponse(BaseModel):
    is_recording: bool
    session_id: Optional[str]
    duration_seconds: Optional[float]
    bytes_received: int
    current_file: Optional[str]
    recordings_count: int


class VideoFile(BaseModel):
    filename: str
    path: str
    size_bytes: int
    created_at: str
    duration_seconds: Optional[float]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def get_video_duration(file_path: Path) -> Optional[float]:
    """Retrieve video duration using ffprobe if available."""
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            return round(float(res.stdout.strip()), 2)
    except Exception:
        pass
    return None


async def start_ffmpeg_pipeline(session_id: str) -> tuple[subprocess.Popen, Path]:
    """Start an ffmpeg process that streams WebM from stdin to MP4."""
    output_path = RECORDINGS_DIR / f"{session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "webm",
        "-i", "pipe:0",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path),
    ]
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return process, output_path


async def finalize_recording(session_id: Optional[str]):
    """Finalize the recording with fallback conversion from raw WebM."""
    print(f"[Backend] Finalizing recording for session: {session_id}")

    # 1. Close the raw backup WebM file
    if state.temp_webm_file:
        try:
            state.temp_webm_file.flush()
            state.temp_webm_file.close()
        except Exception as e:
            print(f"[Backend] Error closing temp webm file: {e}")
        state.temp_webm_file = None

    # 2. Close pipe and terminate/wait for FFmpeg stdin process
    pipe_success = False
    if state.ffmpeg_process:
        try:
            if state.ffmpeg_process.stdin and not state.ffmpeg_process.stdin.closed:
                state.ffmpeg_process.stdin.close()
            stdout, stderr = state.ffmpeg_process.communicate(timeout=10)
            if state.ffmpeg_process.returncode == 0:
                pipe_success = True
            elif stderr:
                print(f"[ffmpeg stderr] {stderr.decode(errors='replace')}")
        except subprocess.TimeoutExpired:
            print("[Backend] FFmpeg pipe process timed out; killing...")
            state.ffmpeg_process.kill()
            state.ffmpeg_process.communicate()
        except Exception as e:
            print(f"[Backend] Note on FFmpeg pipe finalization: {e}")
        finally:
            state.ffmpeg_process = None

    # 3. Fallback check: if output mp4 doesn't exist or is empty (< 1KB), convert from saved WebM
    output_path = state.current_file
    if output_path and (not output_path.exists() or output_path.stat().st_size < 1024):
        if state.temp_webm_path and state.temp_webm_path.exists() and state.temp_webm_path.stat().st_size > 0:
            print(f"[Backend] Running fallback transcoding from {state.temp_webm_path} -> {output_path}")
            fallback_cmd = [
                "ffmpeg", "-y",
                "-i", str(state.temp_webm_path),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                str(output_path),
            ]
            res = subprocess.run(fallback_cmd, capture_output=True, text=True)
            if res.returncode == 0 and output_path.exists():
                print(f"[Backend] Fallback transcode succeeded! Output: {output_path.name} ({output_path.stat().st_size} bytes)")
            else:
                print(f"[Backend] Fallback transcode error: {res.stderr}")

    state.is_recording = False
    print(f"[Backend] Session {session_id} finalized.")


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------
@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    client_session_id: Optional[str] = None
    print("[Backend] Extension WebSocket connected")

    try:
        while True:
            message = await websocket.receive()

            if "text" in message:
                data = json.loads(message["text"])

                if data.get("type") == "session_start":
                    client_session_id = data.get("session_id") or str(uuid.uuid4())
                    state.session_id = client_session_id
                    state.is_recording = True
                    state.start_time = time.time()
                    state.bytes_received = 0

                    # 1. Open raw WebM backup stream
                    state.temp_webm_path = TEMP_DIR / f"{client_session_id}.webm"
                    state.temp_webm_file = open(state.temp_webm_path, "wb")

                    # 2. Start FFmpeg pipe process
                    state.ffmpeg_process, state.current_file = await start_ffmpeg_pipeline(client_session_id)
                    print(f"[Backend] Recording started: session={client_session_id}, target={state.current_file.name}")

                    await websocket.send_text(json.dumps({"type": "ack", "status": "recording_started"}))

                elif data.get("type") == "session_end":
                    await finalize_recording(client_session_id)
                    await websocket.send_text(json.dumps({"type": "ack", "status": "recording_stopped"}))

            elif "bytes" in message:
                chunk = message["bytes"]
                state.bytes_received += len(chunk)

                # Write to raw backup
                if state.temp_webm_file:
                    try:
                        state.temp_webm_file.write(chunk)
                    except Exception as e:
                        print(f"[Backend] Error writing to temp webm: {e}")

                # Write to FFmpeg stdin pipe
                if state.ffmpeg_process and state.ffmpeg_process.stdin:
                    try:
                        state.ffmpeg_process.stdin.write(chunk)
                        state.ffmpeg_process.stdin.flush()
                    except BrokenPipeError:
                        # Pipe broken; fallback at finalize_recording will convert temp_webm
                        pass
                    except Exception as e:
                        print(f"[Backend] Stdin write error: {e}")

    except WebSocketDisconnect:
        print(f"[Backend] WebSocket disconnected: session={client_session_id}")
        if state.is_recording:
            await finalize_recording(client_session_id)
    except RuntimeError as e:
        if "disconnect message has been received" in str(e):
            print(f"[Backend] WebSocket closed cleanly for session={client_session_id}")
            if state.is_recording:
                await finalize_recording(client_session_id)
        else:
            print(f"[Backend] Runtime error: {e}")
            if state.is_recording:
                await finalize_recording(client_session_id)
    except Exception as e:
        print(f"[Backend] WebSocket error: {e}")
        if state.is_recording:
            await finalize_recording(client_session_id)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "service": "tab-video-capture-backend",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/status", response_model=StatusResponse)
async def get_status():
    duration = (
        round(time.time() - state.start_time, 1)
        if state.start_time and state.is_recording
        else None
    )
    return StatusResponse(
        is_recording=state.is_recording,
        session_id=state.session_id,
        duration_seconds=duration,
        bytes_received=state.bytes_received,
        current_file=str(state.current_file.name) if state.current_file else None,
        recordings_count=len(list(RECORDINGS_DIR.glob("*.mp4"))),
    )


@app.get("/api/recordings", response_model=list[VideoFile])
async def list_recordings():
    files: list[VideoFile] = []
    for mp4 in sorted(RECORDINGS_DIR.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True):
        stat = mp4.stat()
        files.append(
            VideoFile(
                filename=mp4.name,
                path=f"/recordings/{mp4.name}",
                size_bytes=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_ctime).isoformat(),
                duration_seconds=get_video_duration(mp4),
            )
        )
    return files


@app.get("/recordings/{filename}")
async def serve_recording(filename: str):
    file_path = RECORDINGS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Recording not found")
    return FileResponse(str(file_path), media_type="video/mp4", filename=filename)


@app.delete("/api/recordings/{filename}")
async def delete_recording(filename: str):
    file_path = RECORDINGS_DIR / filename
    if file_path.exists():
        file_path.unlink()
        return {"success": True, "deleted": filename}
    raise HTTPException(status_code=404, detail="File not found")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765, ws_ping_interval=20, ws_ping_timeout=20)
