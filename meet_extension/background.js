import { meetingCode, matchesCommand, validEvent } from './protocol.js';
const BASE = 'http://127.0.0.1:49321';
const syncing = new Set();
const audio = new Map();          // sound name -> base64, fetched once from the app
let soundsTab = null;             // the linked call that receives sounds
let listening = false;

/** @param {string} endpoint @param {object} body @param {number} [timeout] */
async function post(endpoint, body, timeout = 2500) {
  const response = await fetch(BASE + endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(timeout), cache: 'no-store'
  });
  if (!response.ok) throw new Error(`Sumi respondeu ${response.status}`);
  return response;
}

async function remember(status) {
  await chrome.storage.local.set({ status: { ...status, at: Date.now() } });
}

/** One heartbeat from a Meet tab: tells the app where the call is and runs a pending leave. */
async function sync(tab, focused, frameUrl) {
  if (syncing.has(tab.id)) return;
  syncing.add(tab.id);
  // The tab URL can be missing (site access limited); the top frame's own URL is always there.
  const code = meetingCode(tab.url) || meetingCode(frameUrl);
  try {
    let data;
    try {
      data = await (await post('/sync', { meeting: code, tab: tab.id, focused })).json();
    } catch {
      await remember({ app: false });
      return;
    }
    const target = data.target;
    await remember({ app: true, meeting: target ? target.meeting : null, sounds: data.sounds === true });
    if (target && target.tab === tab.id && data.sounds === true) listen(tab.id);
    else if (soundsTab === tab.id) soundsTab = null;
    const command = data.command;
    if (!code || !matchesCommand(command, tab.id, code, Date.now())) return;
    let closed = false;
    try {
      const current = await chrome.tabs.get(tab.id);
      if ((current.url === undefined || meetingCode(current.url) === code) && matchesCommand(command, tab.id, code, Date.now())) {
        // Closing the linked tab leaves the call, without touching other tabs or windows.
        await chrome.tabs.remove(tab.id);
        closed = true;
      }
    } finally {
      await post('/result', { id: command.id, closed }).catch(() => {});
    }
  } finally { syncing.delete(tab.id); }
}

/** @param {string} name */
async function sound(name) {
  if (!audio.has(name)) {
    const bytes = new Uint8Array(await (await post('/sound', { name }, 5000)).arrayBuffer());
    let text = '';
    for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    audio.set(name, btoa(text));
  }
  return audio.get(name);
}

/** Long poll for effect sounds while a linked call wants them. */
function listen(tabId) {
  soundsTab = tabId;
  if (listening) return;
  listening = true;
  (async () => {
    let cursor = -1;
    while (soundsTab !== null) {
      try {
        const data = await (await post('/events', { since: cursor }, 25000)).json();
        const fresh = cursor >= 0;
        cursor = typeof data.cursor === 'number' ? data.cursor : -1;
        if (!fresh || !Array.isArray(data.events)) continue;
        for (const event of data.events) {
          if (!validEvent(event) || soundsTab === null) continue;
          const message = { type: 'sfx', action: event.action, name: event.name };
          if (event.action === 'play' || event.action === 'loop') {
            message.audio = await sound(event.name).catch(() => null);
            if (message.audio === null) continue;
            // Optional `<name>-loop`: the intro plays once, then only that part repeats.
            if (event.action === 'loop') message.tail = await sound(`${event.name}-loop`).catch(() => null);
          }
          chrome.tabs.sendMessage(soundsTab, message).catch(() => {});
        }
      } catch {
        await new Promise(resolve => setTimeout(resolve, 1000));
        cursor = -1;
      }
    }
    listening = false;
  })();
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message.type === 'heartbeat' && sender.tab && typeof sender.tab.id === 'number') {
    sync(sender.tab, message.focused === true, sender.frameId === 0 ? sender.url : undefined).then(() => respond({ ok: true })).catch(() => respond({ ok: false }));
    return true;
  }
  return false;
});

// Tabs opened before the extension was installed or reloaded get no content script:
// connect them now. Their sounds only start after the Meet tab is reloaded (the
// microphone was opened before the mixer existed).
chrome.runtime.onInstalled.addListener(async () => {
  const tabs = await chrome.tabs.query({ url: 'https://meet.google.com/*' }).catch(() => []);
  for (const tab of tabs) {
    if (typeof tab.id !== 'number') continue;
    chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['heartbeat.js'] }).catch(() => {});
  }
});
