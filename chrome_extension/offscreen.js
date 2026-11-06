// offscreen.js — DOM-based recording & WebSocket streaming for MV3

const WS_URL = 'ws://localhost:8765/ws/stream';

let mediaRecorder = null;
let captureStream = null;
let audioCtx = null;
let wsConnection = null;
let currentSessionId = null;

chrome.runtime.onMessage.addListener(async (message, sender, sendResponse) => {
  if (message.action === 'start-recording') {
    startRecording(message.streamId, message.sessionId);
    sendResponse({ success: true });
  } else if (message.action === 'stop-recording') {
    stopRecording();
    sendResponse({ success: true });
  }
  return true;
});

async function startRecording(streamId, sessionId) {
  currentSessionId = sessionId;
  console.log('[Offscreen] Starting recording with streamId:', streamId, 'sessionId:', sessionId);

  try {
    // 1. Get media stream using the streamId provided by chrome.tabCapture
    const constraints = {
      audio: {
        mandatory: {
          chromeMediaSource: 'tab',
          chromeMediaSourceId: streamId
        }
      },
      video: {
        mandatory: {
          chromeMediaSource: 'tab',
          chromeMediaSourceId: streamId,
          minWidth: 1280,
          minHeight: 720,
          maxWidth: 1920,
          maxHeight: 1080,
          minFrameRate: 30
        }
      }
    };

    captureStream = await navigator.mediaDevices.getUserMedia(constraints);
    console.log('[Offscreen] Acquired media stream:', captureStream.getTracks());

    // 2. Prevent muting by routing audio to destination so user still hears it
    try {
      const audioTracks = captureStream.getAudioTracks();
      if (audioTracks.length > 0) {
        audioCtx = new AudioContext();
        const source = audioCtx.createMediaStreamSource(captureStream);
        source.connect(audioCtx.destination);
      }
    } catch (err) {
      console.warn('[Offscreen] Could not route audio to speakers:', err);
    }

    // 3. Connect WebSocket to local FastAPI backend
    wsConnection = new WebSocket(WS_URL);
    wsConnection.binaryType = 'arraybuffer';

    wsConnection.onopen = () => {
      console.log('[Offscreen] WebSocket connected');
      wsConnection.send(JSON.stringify({
        type: 'session_start',
        session_id: currentSessionId
      }));

      // Start MediaRecorder once WebSocket is ready
      initMediaRecorder();
    };

    wsConnection.onerror = (err) => {
      console.error('[Offscreen] WebSocket error:', err);
    };

    wsConnection.onclose = () => {
      console.log('[Offscreen] WebSocket closed');
      wsConnection = null;
    };

  } catch (error) {
    console.error('[Offscreen] Error starting capture:', error);
    chrome.storage.local.set({ recording: false, lastError: error.message });
  }
}

function initMediaRecorder() {
  let mimeType = 'video/webm;codecs=vp9,opus';
  if (!MediaRecorder.isTypeSupported(mimeType)) {
    mimeType = 'video/webm;codecs=vp8,opus';
    if (!MediaRecorder.isTypeSupported(mimeType)) {
      mimeType = 'video/webm';
    }
  }

  mediaRecorder = new MediaRecorder(captureStream, {
    mimeType: mimeType,
    videoBitsPerSecond: 4000000 // 4 Mbps
  });

  mediaRecorder.ondataavailable = async (event) => {
    if (event.data && event.data.size > 0 && wsConnection && wsConnection.readyState === WebSocket.OPEN) {
      const buffer = await event.data.arrayBuffer();
      wsConnection.send(buffer);
    }
  };

  mediaRecorder.onstart = () => {
    console.log('[Offscreen] MediaRecorder started');
    chrome.storage.local.set({ recording: true, session_id: currentSessionId });
  };

  mediaRecorder.onstop = () => {
    console.log('[Offscreen] MediaRecorder stopped');
    chrome.storage.local.set({ recording: false });

    // Send session end notification
    if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
      wsConnection.send(JSON.stringify({
        type: 'session_end',
        session_id: currentSessionId
      }));
    }

    // Clean up tracks
    if (captureStream) {
      captureStream.getTracks().forEach((track) => track.stop());
      captureStream = null;
    }

    // Close audio context
    if (audioCtx) {
      audioCtx.close().catch(() => {});
      audioCtx = null;
    }

    // Close WebSocket after slight delay to ensure final frame flush
    setTimeout(() => {
      if (wsConnection) {
        wsConnection.close();
      }
      // Note: background service worker can close offscreen document
    }, 1000);
  };

  // Slice stream into 1-second chunks
  mediaRecorder.start(1000);
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  } else if (captureStream) {
    captureStream.getTracks().forEach((track) => track.stop());
    captureStream = null;
  }
}

