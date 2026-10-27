/** @param {string | undefined} address @returns {string | null} */
export function meetingCode(address) {
  try {
    const url = new URL(address || '');
    if (url.protocol !== 'https:' || url.hostname !== 'meet.google.com') return null;
    const match = /^\/([a-z]{3}-[a-z]{4}-[a-z]{3})\/?$/.exec(url.pathname);
    return match ? match[1] : null;
  } catch { return null; }
}

/** @param {object} command @param {number} tab @param {string} meeting @param {number} now */
export function matchesCommand(command, tab, meeting, now) {
  return command !== null && typeof command === 'object' &&
    command.action === 'leave' && typeof command.id === 'string' &&
    command.tab === tab && command.meeting === meeting &&
    typeof command.expires === 'number' && command.expires > now && command.expires - now <= 5000;
}
