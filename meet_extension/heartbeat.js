// No page content, video or microphone data is read. This only wakes the local bridge.
function heartbeat() {
  chrome.runtime.sendMessage({type:'heartbeat'}).catch(() => {});
}
heartbeat();
setInterval(heartbeat, 750);
document.addEventListener('visibilitychange', heartbeat);
