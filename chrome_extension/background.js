// background.js — MV3 Service Worker orchestrating Tab Capture & Offscreen Document

let isRecording = false;
let currentSessionId = null;

function generateSessionId() {
  return `session_${Date.now()}`;
}

async function ensureOffscreenDocument() {
  if ('getContexts' in chrome.runtime) {
    const existing = await chrome.runtime.getContexts({
      contextTypes: ['OFFSCREEN_DOCUMENT']
    });
    if (existing.length > 0) {
      return;
    }
  }

  try {
    await chrome.offscreen.createDocument({
      url: 'offscreen.html',
      reasons: ['USER_MEDIA'],
      justification: 'Recording tab audio and video stream via MediaRecorder'
    });
    console.log('[Background] Offscreen document created');
  } catch (err) {
    if (!err.message.includes('Only a single offscreen document may be created')) {
      console.error('[Background] Failed to create offscreen document:', err);
      throw err;
    }
  }
}

async function startCapture(tabId) {
  currentSessionId = generateSessionId();

  // 1. Obtain stream ID for the target tab
  chrome.tabCapture.getMediaStreamId({ targetTabId: tabId }, async (streamId) => {
    if (chrome.runtime.lastError || !streamId) {
      const err = chrome.runtime.lastError?.message || 'Failed to get media stream ID';
      console.error('[Background] getMediaStreamId error:', err);
      chrome.storage.local.set({ recording: false, lastError: err });
      return;
    }

    console.log('[Background] Got streamId for tab', tabId, ':', streamId);

    // 2. Ensure offscreen document is ready
    await ensureOffscreenDocument();

    // 3. Delegate recording to offscreen document
    isRecording = true;
    await chrome.storage.local.set({ recording: true, session_id: currentSessionId });

    chrome.runtime.sendMessage({
      action: 'start-recording',
      streamId: streamId,
      sessionId: currentSessionId
    });
  });
}

async function stopCapture() {
  isRecording = false;
  await chrome.storage.local.set({ recording: false });

  // Signal offscreen document to finalize recording
  chrome.runtime.sendMessage({ action: 'stop-recording' }, () => {
    if (chrome.runtime.lastError) {
      // Offscreen might have already closed, which is fine
    }
  });

  // Close offscreen document after brief grace period for cleanup
  setTimeout(async () => {
    try {
      await chrome.offscreen.closeDocument();
      console.log('[Background] Offscreen document closed');
    } catch (_) {}
  }, 2000);
}

// ─── Message Router ───────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  switch (message.action) {
    case 'startCapture':
      startCapture(message.tabId);
      sendResponse({ success: true, sessionId: currentSessionId });
      break;

    case 'stopCapture':
      stopCapture();
      sendResponse({ success: true });
      break;

    case 'getStatus':
      chrome.storage.local.get(['recording', 'session_id'], (data) => {
        sendResponse({
          isRecording: !!data.recording,
          sessionId: data.session_id || null
        });
      });
      return true; // async response

    default:
      // Other messages may be intended for offscreen or popup
      break;
  }
  return false;
});
