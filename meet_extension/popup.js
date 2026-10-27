const app = document.querySelector('#app');
const meeting = document.querySelector('#meeting');

async function render() {
  const { status } = await chrome.storage.local.get('status');
  const fresh = status && Date.now() - status.at < 5000;
  if (!fresh) {
    app.textContent = 'Abra uma aba do Meet para conectar ao Sumi.';
    meeting.textContent = '';
  } else if (!status.app) {
    app.textContent = 'Sumi fechado. Abra o app para conectar.';
    meeting.textContent = '';
  } else {
    app.textContent = 'Conectado ao Sumi.';
    meeting.textContent = status.meeting
      ? `Reunião ${status.meeting} vinculada${status.sounds ? ' · sons na chamada ligados' : ''}.`
      : 'Entre em uma reunião e ela será vinculada sozinha.';
  }
}
render();
setInterval(render, 1000);
