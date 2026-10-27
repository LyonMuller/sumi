const token = document.querySelector('#token');
const button = document.querySelector('#pair');
const status = document.querySelector('#status');
const stored = await chrome.storage.local.get('token');
if (typeof stored.token === 'string') token.value = stored.token;
button.addEventListener('click', async () => {
  button.disabled = true;
  try {
    const result = await chrome.runtime.sendMessage({type:'pair',token:token.value.trim()});
    status.textContent = result.ok ? `Aba ${result.meeting} vinculada. Ative o toggle no Sumi quando quiser.` : result.error;
  } catch { status.textContent = 'Não consegui conectar. Abra o Sumi e tente novamente.'; }
  finally { button.disabled = false; }
});
