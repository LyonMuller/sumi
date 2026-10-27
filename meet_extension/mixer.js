// Runs in the Meet page. Adds Sumi's effect sounds to the microphone sent to the call:
// the microphone track is mixed with a sound bus through Web Audio. Nothing is recorded,
// read or sent elsewhere. Muting in Meet silences both, as expected. On any error the
// original microphone is returned untouched.
(() => {
  const devices = navigator.mediaDevices;
  if (!devices || !devices.getUserMedia || devices.__sumiMixer) return;
  Object.defineProperty(devices, '__sumiMixer', { value: true });
  const original = devices.getUserMedia.bind(devices);
  let context = null;
  let bus = null;
  const decoded = new Map();
  const loops = new Map();

  function audio() {
    if (!context) {
      context = new AudioContext();
      bus = context.createGain();
      bus.gain.value = 0.85;
    }
    if (context.state === 'suspended') context.resume().catch(() => {});
    return context;
  }

  // Chrome may start the context suspended until the page gets a click or key press;
  // the microphone passes through it, so resume at the first chance.
  for (const type of ['pointerdown', 'keydown', 'touchstart']) {
    window.addEventListener(type, () => { if (context && context.state === 'suspended') context.resume().catch(() => {}); },
                            { capture: true, passive: true });
  }

  /** The mixed track looks and behaves like the microphone for Meet's own controls. */
  function disguise(mixed, mic, cleanup) {
    const stop = mixed.stop.bind(mixed);
    Object.defineProperties(mixed, {
      label: { get: () => mic.label },
      stop: { value: () => { stop(); mic.stop(); cleanup(); } },
      getSettings: { value: () => mic.getSettings() },
      getCapabilities: { value: () => mic.getCapabilities() },
      getConstraints: { value: () => mic.getConstraints() },
      applyConstraints: { value: constraints => mic.applyConstraints(constraints) },
    });
    mic.addEventListener('ended', () => { cleanup(); mixed.dispatchEvent(new Event('ended')); });
  }

  devices.getUserMedia = async function (constraints) {
    const stream = await original(constraints);
    const mic = stream.getAudioTracks()[0];
    if (!constraints || !constraints.audio || !mic) return stream;
    try {
      const ctx = audio();
      // Never risk a silent microphone: without a running context, hand Meet the real one.
      if (ctx.state !== 'running') await Promise.race([ctx.resume(), new Promise(r => setTimeout(r, 300))]).catch(() => {});
      if (ctx.state !== 'running') return stream;
      const source = ctx.createMediaStreamSource(new MediaStream([mic]));
      const destination = ctx.createMediaStreamDestination();
      source.connect(destination);
      bus.connect(destination);
      const mixed = destination.stream.getAudioTracks()[0];
      disguise(mixed, mic, () => {
        try { source.disconnect(); bus.disconnect(destination); } catch { /* already gone */ }
      });
      return new MediaStream([...stream.getVideoTracks(), mixed]);
    } catch {
      return stream;
    }
  };

  async function buffer(name, data) {
    if (!decoded.has(name) && data) decoded.set(name, await audio().decodeAudioData(data));
    return decoded.get(name);
  }

  function stop(name) {
    const entry = loops.get(name);
    if (!entry) return;
    loops.delete(name);
    try { entry.node.stop(); } catch { /* already stopped */ }
  }

  function start(sound, loop) {
    const node = context.createBufferSource();
    node.buffer = sound;
    node.loop = loop;
    node.connect(bus);
    node.start();
    return node;
  }

  window.addEventListener('message', async event => {
    const data = event.data;
    if (event.source !== window || !data || data.source !== 'sumi-sfx' || !context) return;
    try {
      if (data.action === 'stop_all') { [...loops.keys()].forEach(stop); return; }
      if (data.action === 'stop') { stop(data.name); return; }
      const sound = await buffer(data.name, data.audio);
      if (!sound || (data.action === 'loop' && loops.has(data.name))) return;
      if (data.action !== 'loop') { start(sound, false); return; }
      const tail = data.tail ? await buffer(`${data.name}-loop`, data.tail) : null;
      const entry = { node: start(sound, !tail) };
      loops.set(data.name, entry);
      if (tail) {
        entry.node.onended = () => { if (loops.get(data.name) === entry) entry.node = start(tail, true); };
      }
    } catch { /* a broken sound never affects the call */ }
  });
})();
