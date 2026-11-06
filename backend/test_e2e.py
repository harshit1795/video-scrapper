import asyncio
import json
import os
import subprocess
import time
import requests
import websockets

BACKEND_URL = "http://localhost:8765"
WS_URL = "ws://localhost:8765/ws/stream"


def generate_sample_webm() -> bytes:
    """Generate a tiny 2-second valid WebM clip using ffmpeg for testing."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=2",
        "-c:v", "libvpx-vp9",
        "-c:a", "libopus",
        "-f", "webm",
        "pipe:1"
    ]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg sample generation failed: {res.stderr.decode()}")
    return res.stdout


async def run_e2e_test():
    print("=== Tab Video Capture End-to-End Test ===")

    # 1. Health check
    print("\n1. Testing HTTP Health Check...")
    resp = requests.get(f"{BACKEND_URL}/api/health", timeout=5)
    assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
    print("   ✅ Backend health check passed:", resp.json())

    # 2. Status check (initial idle state)
    print("\n2. Testing Initial Status...")
    resp = requests.get(f"{BACKEND_URL}/api/status", timeout=5)
    assert resp.status_code == 200, f"Status check failed: {resp.status_code}"
    status = resp.json()
    assert not status["is_recording"], "Expected is_recording to be False"
    print("   ✅ Status is idle:", status)

    # 3. Simulate Chrome Extension streaming over WebSocket
    print("\n3. Generating synthetic WebM stream with FFmpeg...")
    sample_webm = generate_sample_webm()
    print(f"   Generated {len(sample_webm)} bytes of valid WebM test media.")

    test_session_id = f"test_session_{int(time.time())}"
    print(f"\n4. Connecting WebSocket to {WS_URL} for session '{test_session_id}'...")

    async with websockets.connect(WS_URL) as ws:
        # Send session_start
        await ws.send(json.dumps({
            "type": "session_start",
            "session_id": test_session_id
        }))
        ack = await ws.recv()
        print("   ✅ Received start ack:", ack)

        # Check status while recording
        time.sleep(0.5)
        st = requests.get(f"{BACKEND_URL}/api/status").json()
        assert st["is_recording"], "Expected backend state to report recording active"
        assert st["session_id"] == test_session_id
        print("   ✅ Backend reports active recording session:", st["session_id"])

        # Stream sample WebM in 32KB chunks
        chunk_size = 32 * 1024
        for i in range(0, len(sample_webm), chunk_size):
            chunk = sample_webm[i:i + chunk_size]
            await ws.send(chunk)
            await asyncio.sleep(0.1)
        print("   ✅ Streamed all chunks over WebSocket.")

        # Send session_end
        await ws.send(json.dumps({
            "type": "session_end",
            "session_id": test_session_id
        }))
        ack_end = await ws.recv()
        print("   ✅ Received end ack:", ack_end)

    # Allow FFmpeg pipeline a moment to finalize
    print("\n5. Verifying recording output...")
    time.sleep(2.0)

    # 4. Check list recordings
    resp = requests.get(f"{BACKEND_URL}/api/recordings")
    assert resp.status_code == 200
    recordings = resp.json()
    print(f"   Total recordings found: {len(recordings)}")
    found = [r for r in recordings if test_session_id in r["filename"]]
    assert len(found) > 0, f"Test recording for {test_session_id} not found in {recordings}"
    saved_file = found[0]
    print("   ✅ Saved video found:", saved_file["filename"], f"({saved_file['size_bytes']} bytes)")
    assert saved_file["size_bytes"] > 0, "File is empty"

    # 5. Test download / stream
    print("\n6. Testing Video Stream / Download...")
    v_resp = requests.get(f"{BACKEND_URL}/recordings/{saved_file['filename']}", stream=True)
    assert v_resp.status_code == 200, f"Stream failed: {v_resp.status_code}"
    assert v_resp.headers.get("content-type") == "video/mp4"
    print("   ✅ Video stream endpoint returned HTTP 200 video/mp4")

    # 6. Test delete
    print("\n7. Testing Recording Deletion...")
    del_resp = requests.delete(f"{BACKEND_URL}/api/recordings/{saved_file['filename']}")
    assert del_resp.status_code == 200
    print("   ✅ Deletion API returned success:", del_resp.json())

    # Verify gone
    recordings_after = requests.get(f"{BACKEND_URL}/api/recordings").json()
    assert not any(r["filename"] == saved_file["filename"] for r in recordings_after)
    print("   ✅ Recording successfully removed from disk.")

    print("\n🎉 ALL END-TO-END TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(run_e2e_test())

