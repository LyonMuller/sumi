// Tells the extension this Meet tab exists (and which call it shows), and passes effect
// sounds to mixer.js. No page content, video or microphone data is read or sent anywhere.
(() => {
  // After the extension is reloaded, the copy already running in this tab loses its
  // connection; it stops quietly and the fresh copy takes over.
  const alive = () => { try { return Boolean(chrome.runtime && chrome.runtime.id); } catch { return false; } };
  let timer = null;

  function heartbeat() {
    if (!alive()) { clearInterval(timer); return; }
    const focused = document.visibilityState === 'visible' && document.hasFocus();
    try {
      chrome.runtime.sendMessage({ type: 'heartbeat', focused, url: location.href }).catch(() => {});
    } catch { clearInterval(timer); }
  }

  timer = setInterval(heartbeat, 1000);
  heartbeat();
  document.addEventListener('visibilitychange', heartbeat);
  window.addEventListener('focus', heartbeat);

  chrome.runtime.onMessage.addListener(message => {
    if (message.type !== 'sfx') return;
    const decode = base64 => {
      if (typeof base64 !== 'string') return undefined;
      const text = atob(base64);
      const bytes = new Uint8Array(text.length);
      for (let i = 0; i < text.length; i++) bytes[i] = text.charCodeAt(i);
      return bytes.buffer;
    };
    const audio = decode(message.audio);
    const tail = decode(message.tail);
    const payload = { source: 'sumi-sfx', action: message.action, name: message.name, audio, tail };
    window.postMessage(payload, location.origin, [audio, tail].filter(Boolean));
  });
})();
