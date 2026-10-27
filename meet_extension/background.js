import { meetingCode, matchesCommand } from './protocol.js';
const BASE = 'http://127.0.0.1:49321';
let inFlight = false;

/** @param {string} endpoint @param {string} token @param {object | undefined} body */
async function request(endpoint, token, body) {
  const response = await fetch(BASE + endpoint, {
    method: body ? 'POST' : 'GET',
    headers: { 'X-Sumi-Token': token, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(2500), cache: 'no-store'
  });
  if (!response.ok) throw new Error('Abra o Sumi e confira o código de conexão.');
  return response.json();
}

/** @param {chrome.runtime.MessageSender} sender */
async function poll(sender) {
  if (inFlight || !sender.tab || typeof sender.tab.id !== 'number') return;
  const tabId = sender.tab.id;
  const code = meetingCode(sender.tab.url);
  if (!code) return;
  const stored = await chrome.storage.local.get('binding');
  const binding = stored.binding;
  if (!binding || binding.tab !== tabId || binding.meeting !== code || typeof binding.token !== 'string') return;
  inFlight = true;
  try {
    const data = await request(`/command?meeting=${code}&tab=${tabId}`, binding.token);
    const command = data.command;
    if (!matchesCommand(command, tabId, code, Date.now())) return;
    let closed = false;
    try {
      const current = await chrome.tabs.get(tabId);
      if (meetingCode(current.url) === code && matchesCommand(command, tabId, code, Date.now())) {
        // Closing the explicitly bound tab leaves the call, without touching other tabs/windows.
        await chrome.tabs.remove(tabId);
        closed = true;
      }
    } finally {
      await request('/result', binding.token, { id: command.id, closed });
      if (closed) await chrome.storage.local.remove('binding');
    }
  } finally { inFlight = false; }
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message.type === 'heartbeat' && sender.tab) {
    poll(sender).then(() => respond({ok:true})).catch(() => respond({ok:false}));
    return true;
  }
  if (message.type === 'pair' && sender.url === chrome.runtime.getURL('popup.html')) {
    (async () => {
      const [tab] = await chrome.tabs.query({active:true,currentWindow:true});
      const code = meetingCode(tab?.url);
      if (!code || typeof tab.id !== 'number') throw new Error('Abra a aba da reunião do Meet e clique na extensão nela.');
      if (typeof message.token !== 'string' || message.token.length < 32) throw new Error('Cole o código copiado do Sumi.');
      await request('/pair', message.token, {meeting:code,tab:tab.id});
      await chrome.storage.local.set({binding:{meeting:code,tab:tab.id,token:message.token}});
      await chrome.storage.local.set({token:message.token});
      return {ok:true,meeting:code};
    })().then(respond).catch(error => respond({ok:false,error:error.message}));
    return true;
  }
  return false;
});
