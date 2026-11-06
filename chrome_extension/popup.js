// popup.js — UI controller for Tab Video Capture popup

document.addEventListener('DOMContentLoaded', () => {
  const startBtn   = document.getElementById('startBtn');
  const stopBtn    = document.getElementById('stopBtn');
  const statusEl   = document.getElementById('status');
  const statusDot  = document.getElementById('statusDot');
  const sessionEl  = document.getElementById('session-id');

  // ── Restore state from storage ──────────────────────────────────────────────
  chrome.storage.local.get(['recording', 'session_id'], (result) => {
    updateUI(!!result.recording, result.session_id || null);
  });

  // ── Start Capture ───────────────────────────────────────────────────────────
  startBtn.addEventListener('click', () => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs || tabs.length === 0) return;
      const tabId = tabs[0].id;

      chrome.runtime.sendMessage({ action: 'startCapture', tabId }, (response) => {
        if (chrome.runtime.lastError) {
          console.error('[Popup] startCapture error:', chrome.runtime.lastError.message);
          return;
        }
        if (response && response.success) {
          // Poll storage briefly to get the new session_id written by background
          setTimeout(() => {
            chrome.storage.local.get(['recording', 'session_id'], (result) => {
              updateUI(!!result.recording, result.session_id || null);
            });
          }, 300);
        }
      });
    });
  });

  // ── Stop Capture ────────────────────────────────────────────────────────────
  stopBtn.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'stopCapture' }, (response) => {
      if (chrome.runtime.lastError) {
        console.error('[Popup] stopCapture error:', chrome.runtime.lastError.message);
        return;
      }
      if (response && response.success) {
        updateUI(false, null);
      }
    });
  });

  // ── UI Helper ───────────────────────────────────────────────────────────────
  /**
   * @param {boolean} isRecording
   * @param {string|null} sessionId
   */
  function updateUI(isRecording, sessionId) {
    if (isRecording) {
      statusEl.textContent = 'Recording…';
      statusDot.classList.add('recording');
      startBtn.disabled = true;
      stopBtn.disabled  = false;
      sessionEl.textContent = sessionId ? `Session: ${sessionId}` : '';
    } else {
      statusEl.textContent = 'Idle';
      statusDot.classList.remove('recording');
      startBtn.disabled = false;
      stopBtn.disabled  = true;
      sessionEl.textContent = '';
    }
  }
});
