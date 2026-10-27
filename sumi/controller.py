"""Session logic shared by every interface: no widgets, no Tk, no Swift.

An interface calls the action methods and renders ``tick()`` about 30 times per second.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from time import monotonic
from typing import Callable
import sys
import webbrowser

from .devices import CameraDevice, list_cameras
from .effect_catalog import DESCRIPTIONS, LABELS
from .engine import Engine, Settings
from .gesture_guides import guide_for
from .meet import LeaveCountdown, MeetBridge
from .paths import extension_folder
from .preferences import BACKGROUND_DEFAULT_REVISION, apply_background_default, load_preferences, save_preferences
from .scene import Frame
from .sounds import SoundBank, SoundPlayer
from .system import camera_permission_hint, output_choices

PHASES = {
    'opening': 'Abrindo câmera', 'uncalibrated': 'Prepare o fundo', 'calibrating': 'Capturando fundo',
    'confirm': 'Confira o fundo vazio', 'ready': 'Ao vivo', 'holding': 'Preparando gesto',
    'teleporting': 'Efeito em andamento', 'hidden': 'Desaparecido', 'error': 'Verifique a câmera',
    'stopped': 'Câmera parada',
}
STEPS = {
    'uncalibrated': 'Capture o cenário vazio antes de usar o efeito.',
    'calibrating': 'Saia do enquadramento e aguarde a captura.',
    'confirm': 'A prévia mostra o fundo capturado. Confirme somente se estiver vazio.',
    'hidden': 'Você desapareceu. Repita o gesto ou clique Reaparecer.',
    'ready': 'Faça o gesto indicado abaixo ou use Ativar efeito.',
    'holding': 'Mantenha a posição até completar a barra.',
    'teleporting': 'Efeito em andamento. F8 cancela e restaura.',
}
RESOLUTIONS = ('1280 × 720', '640 × 480')
HOLD_TIMES = ('0.8', '1.0', '1.5', '2.0')
LEAVE_DELAYS = ('2', '3', '5')
CAPTURE_TIMES = ('3', '5', '10')
SNAP_DELAYS = ('0', '1', '2', '3')
OBS_DOWNLOAD = 'https://obsproject.com/download'
PRIMARY_PHASES = ('uncalibrated', 'confirm', 'ready', 'holding', 'hidden')
RECALIBRATE_PHASES = ('confirm', 'ready', 'holding', 'hidden')


@dataclass
class ViewState:
    """Everything an interface needs to draw one moment of the session."""
    running: bool
    phase: str
    phase_label: str
    hidden: bool
    step: str
    hint: str
    status: str
    progress: float
    fps: float
    performance: str
    primary_label: str
    primary_enabled: bool
    recalibrate_enabled: bool
    start_label: str
    start_enabled: bool
    inputs_enabled: bool
    refresh_enabled: bool
    cameras: list[str]
    camera: str
    effect: str
    effects: list[str]
    resolution: str
    hold: str
    output: str
    outputs: list[str]
    dynamic_background: bool
    background_description: str
    guide_title: str
    guide_instruction: str
    guide_image: str
    guide_steps: list[str]
    output_help: str
    virtual_active: bool
    meet_available: bool
    meet_connected: bool
    meet_status: str
    main_notice: str
    leave_enabled: bool
    leave_delay: str
    leave_countdown: float | None
    capture_time: str
    snap_delay: str
    preview_revision: int
    frame: Frame | None = field(default=None, repr=False)
    clones: bool = False
    clones_count: int = 0
    sounds: bool = True
    call_sounds: bool = True
    meet_extension: bool = False

    def public(self) -> dict[str, object]:
        """JSON-ready copy without the video frame."""
        return {key: value for key, value in self.__dict__.items() if key != 'frame'}


def choose(value: str | None, allowed: tuple[str, ...] | list[str], default: str) -> str:
    return value if value in allowed else default


class Controller:
    def __init__(self, *, preferences_path: Path | None = None,
                 engine_factory: Callable[[Settings], Engine] = Engine,
                 camera_lister: Callable[[], list[CameraDevice]] = list_cameras,
                 bridge_factory: Callable[[], MeetBridge] | None = MeetBridge,
                 open_url: Callable[[str], object] = webbrowser.open,
                 player_factory: Callable[[SoundBank], SoundPlayer] = SoundPlayer) -> None:
        self.preferences_path = preferences_path
        self.engine_factory = engine_factory
        self.camera_lister = camera_lister
        self.open_url = open_url
        self.engine: Engine | None = None
        self.devices: list[CameraDevice] = []
        self.device_events: Queue[tuple[list[CameraDevice], str]] = Queue()
        self.scanning = False
        self.preferences = load_preferences(preferences_path)
        apply_background_default(self.preferences)
        effect = self.preferences.get('effect', 'Teleporte anime')
        if effect == 'Anime · teleporte':
            effect = 'Teleporte anime'
        if effect == 'Puf! · fumaça':
            effect = 'Kawarimi · tronco'
        self.effect = choose(effect, list(LABELS), 'Teleporte anime')
        self.resolution = choose(self.preferences.get('resolution'), RESOLUTIONS, RESOLUTIONS[0])
        self.hold = choose(self.preferences.get('hold'), HOLD_TIMES, '1.0')
        self.capture_time = choose(self.preferences.get('capture_time'), CAPTURE_TIMES, '5')
        self.snap_delay = choose(self.preferences.get('snap_delay'), SNAP_DELAYS, '2')
        self.output = choose(self.preferences.get('backend'), list(output_choices()), 'OBS Virtual Camera')
        self.dynamic = self.preferences.get('background', 'static') == 'live'
        self.sounds = self.preferences.get('sounds', True) is not False
        self.call_sounds = self.preferences.get('call_sounds', True) is not False
        self.sound_bank = SoundBank()
        self.player = player_factory(self.sound_bank)
        self.player.enabled = self.sounds
        self.camera = 'Buscando sua câmera…'
        self.state_text = 'Câmera desligada'
        self.step = 'Sua câmera só liga quando você clicar em Iniciar.'
        self.hint = ''
        self.status = 'Nenhuma imagem está sendo capturada.'
        self.performance = 'Sem áudio'
        self.output_help = ('No Meet, escolha OBS Virtual Camera. Se ainda não instalou o OBS, '
                            'clique em Preparar vídeo para o Meet.')
        self.bridge: MeetBridge | None = None
        self.bridge_error = ''
        if bridge_factory is not None:
            try:
                self.bridge = bridge_factory()
            except (OSError, ValueError) as error:
                self.bridge_error = f'Integração Meet indisponível: {error}'
        else:
            self.bridge_error = 'Integração Meet desligada.'
        if self.bridge is not None:
            self.bridge.sound_path = self.sound_bank.path
            self.bridge.call_sounds = self.call_sounds
        self.countdown = LeaveCountdown()
        self.bound_target = None
        self.leave_enabled = False
        self.leave_delay = '2'
        self.leave_note = ''
        self.meet_status = self.bridge_error or 'Extensão não detectada. O vídeo funciona sem ela.'
        self.main_notice = ''

    # Preferences and options ------------------------------------------------

    def _save(self, failure: str) -> None:
        try:
            save_preferences(self.preferences, self.preferences_path)
        except OSError:
            self.status = failure

    def _engine_running(self) -> bool:
        return self.engine is not None and self.engine.running

    def set_effect(self, label: str) -> None:
        if label not in LABELS:
            raise ValueError('Efeito desconhecido.')
        self.effect = label
        mode = LABELS[label]
        self.hint = DESCRIPTIONS[mode]
        if self.engine is not None and self.engine.running:
            self.engine.commands.put('effect:' + mode)
        self.preferences['effect'] = label
        self._save('Não consegui salvar o efeito; ele continua válido nesta sessão.')

    def set_background(self, dynamic: bool) -> None:
        self.dynamic = bool(dynamic)
        if self.engine is not None and self.engine.running:
            self.engine.commands.put('background:live' if self.dynamic else 'background:static')
        self.preferences['background'] = 'live' if self.dynamic else 'static'
        self._save('Não consegui salvar a preferência; a troca continua válida nesta sessão.')

    def set_sounds(self, enabled: bool) -> None:
        self.sounds = bool(enabled)
        self.player.enabled = self.sounds
        if not self.sounds:
            self.player.stop_all()
        self.preferences['sounds'] = self.sounds
        self._save('Não consegui salvar a preferência; a troca continua válida nesta sessão.')

    def set_call_sounds(self, enabled: bool) -> None:
        self.call_sounds = bool(enabled)
        if self.bridge is not None:
            if not self.call_sounds:
                self.bridge.emit('stop_all')
            self.bridge.call_sounds = self.call_sounds
        self.preferences['call_sounds'] = self.call_sounds
        self._save('Não consegui salvar a preferência; a troca continua válida nesta sessão.')

    def _set_option(self, name: str, value: str, allowed: tuple[str, ...] | list[str]) -> None:
        if self._engine_running():
            raise ValueError('Pare a câmera antes de mudar esta opção.')
        if value not in allowed:
            raise ValueError('Opção inválida.')
        setattr(self, name, value)

    def set_camera(self, label: str) -> None:
        self._set_option('camera', label, [device.label for device in self.devices])

    def set_resolution(self, value: str) -> None:
        self._set_option('resolution', value, RESOLUTIONS)

    def set_hold(self, value: str) -> None:
        self._set_option('hold', value, HOLD_TIMES)

    def set_output(self, label: str) -> None:
        self._set_option('output', label, list(output_choices()))

    def set_capture_time(self, value: str) -> None:
        """Seconds of countdown before the background capture; applies to the next capture."""
        if value not in CAPTURE_TIMES:
            raise ValueError('Opção inválida.')
        self.capture_time = value
        if self.engine is not None:
            self.engine.capture_seconds = float(value)
        self._remember(capture_time=value)

    def set_snap_delay(self, value: str) -> None:
        """Pause between the snap and the dust effect, time for a line before vanishing."""
        if value not in SNAP_DELAYS:
            raise ValueError('Opção inválida.')
        self.snap_delay = value
        if self.engine is not None:
            self.engine.snap_delay = float(value)
        self._remember(snap_delay=value)

    def _remember(self, **values: object) -> None:
        self.preferences.update(values)
        try:
            save_preferences(self.preferences, self.preferences_path)
        except OSError:
            pass

    def set_leave_delay(self, value: str) -> None:
        if value not in LEAVE_DELAYS:
            raise ValueError('Opção inválida.')
        self.leave_delay = value

    # Cameras ------------------------------------------------------------------

    def refresh_devices(self) -> None:
        if self.scanning or self._engine_running():
            return
        self.scanning = True

        def scan() -> None:
            try:
                self.device_events.put((self.camera_lister(), ''))
            except Exception as error:
                self.device_events.put(([], str(error)))
        Thread(target=scan, daemon=True, name='camera-list').start()

    def accept_devices(self) -> bool:
        try:
            devices, error = self.device_events.get_nowait()
        except Empty:
            return False
        self.devices = devices
        self.scanning = False
        if devices:
            current = next((d for d in devices if d.label == self.camera), None)
            preferred = next((d for d in devices if d.path and d.path == self.preferences.get('camera_path')), None)
            selected = current or preferred or next((d for d in devices if not d.virtual), devices[0])
            self.camera = selected.label
        else:
            self.camera = 'Nenhuma webcam encontrada'
            self.status = f'Não encontrei webcams. Conecte a câmera e clique Atualizar. {error}'.strip()
            self.step = 'Conecte sua webcam. Em Configurar → Câmera, clique em Atualizar lista.'
            self.hint = error or camera_permission_hint()
        return True

    # Session ------------------------------------------------------------------

    def start(self) -> None:
        if self.engine is not None and self.engine.thread.is_alive():
            self.stop()
            return
        device = next((d for d in self.devices if d.label == self.camera), None)
        if device is None:
            self.status = 'Selecione uma webcam disponível.'
            return
        width, height = (int(value.strip()) for value in self.resolution.split('×'))
        self.engine = self.engine_factory(Settings(
            camera=device.index, camera_backend=device.backend, width=width, height=height,
            hold=float(self.hold), virtual=output_choices()[self.output], effect=LABELS[self.effect],
            dynamic_background=self.dynamic, capture_seconds=float(self.capture_time),
            snap_delay=float(self.snap_delay)))
        self.preferences = {'camera_path': device.path, 'resolution': self.resolution, 'backend': self.output,
                            'hold': self.hold, 'effect': self.effect,
                            'background': 'live' if self.dynamic else 'static',
                            'sounds': self.sounds, 'call_sounds': self.call_sounds,
                            'capture_time': self.capture_time, 'snap_delay': self.snap_delay,
                            # Keep the marker so the next launch respects the chosen background.
                            'background_default_revision': BACKGROUND_DEFAULT_REVISION}
        try:
            save_preferences(self.preferences, self.preferences_path)
        except OSError:
            self.engine._set_message('Não consegui salvar as preferências. A sessão continua normalmente.')

    def primary_action(self) -> None:
        if self.engine is None or not self.engine.running:
            self.start()
            return
        phase = self.engine.phase
        self.command('confirm' if phase == 'confirm' else 'calibrate' if phase == 'uncalibrated' else 'toggle')

    def command(self, name: str) -> None:
        if name in ('restore', 'calibrate') or (name == 'toggle' and self.engine is not None and self.engine.hidden):
            self.countdown.cancel()
            if self.bridge is not None:
                self.bridge.cancel()
            self.leave_note = 'Saída automática cancelada.'
        if self.engine is not None and self.engine.running:
            self.engine.commands.put(name)

    def stop(self) -> None:
        self.countdown.cancel()
        self._silence()
        if self.bridge is not None:
            self.bridge.cancel()
        if self.engine is not None:
            self.engine.stop.set()

    def wait_for_frame(self, timeout: float) -> bool:
        """Block until the engine publishes a frame. False on timeout or with no camera running."""
        engine = self.engine
        ready = getattr(engine, 'frame_ready', None)
        if engine is None or ready is None or not engine.thread.is_alive():
            return False
        arrived = ready.wait(timeout)
        # Clearing before tick() reads the snapshot means no frame is ever skipped.
        ready.clear()
        return arrived

    def stopped(self) -> bool:
        return self.engine is None or not self.engine.thread.is_alive()

    def close(self) -> None:
        """Ask everything to stop. Call ``stopped()`` until True before exiting."""
        self.stop()
        if self.bridge is not None:
            self.bridge.close()
            self.bridge = None

    # Call output and Meet -----------------------------------------------------

    def prepare_meet(self) -> None:
        if self.engine is not None and self.engine.running:
            self.status = 'Pare a câmera antes de preparar a saída para o Meet.'
            return
        if self.scanning:
            self.status = 'Aguarde a busca de câmeras terminar e tente novamente.'
            return
        if not any('obs' in device.name.lower() and 'virtual' in device.name.lower() for device in self.devices):
            self.output_help = ('Não encontrei OBS Virtual Camera. Instale o OBS pelo site oficial; depois clique em '
                                'Atualizar lista na aba Câmera. Não é preciso manter o OBS aberto.')
            self.status = ('Abrindo o download oficial do OBS. A instalação é feita por você; '
                           'o app não instala drivers automaticamente.')
            self.open_url(OBS_DOWNLOAD)
            return
        self.output = 'OBS Virtual Camera'
        self.status = ('Pronto para iniciar. No Meet, escolha OBS Virtual Camera e desative desfoque/fundo virtual. '
                       'Deixe a câmera virtual parada no OBS.')

    # Sounds -------------------------------------------------------------------

    def _silence(self) -> None:
        self.player.stop_all()
        if self.bridge is not None:
            self.bridge.emit('stop_all')

    def _poll_sounds(self) -> None:
        engine = self.engine
        queue = getattr(engine, 'sounds', None)
        if queue is None:
            return
        while True:
            try:
                action, name = queue.get_nowait()
            except Empty:
                return
            if action == 'stop_all':
                self.player.stop_all()
            elif action == 'loop':
                self.player.loop(name)
            elif action == 'stop':
                self.player.stop(name)
            else:
                self.player.play(name)
            if self.bridge is not None:
                self.bridge.emit(action, name)
            print(f'[som] {action} {name}', file=sys.stderr, flush=True)

    def extension_path(self) -> Path | None:
        try:
            return extension_folder()
        except OSError:
            self.leave_note = ('Não consegui preparar a pasta da extensão. Confira o acesso à sua pasta de dados '
                               'e tente novamente.')
            return None

    def set_leave(self, enabled: bool) -> None:
        self.leave_enabled = bool(enabled)
        if self.leave_enabled and (self.bridge is None or not self.bridge.connected()):
            self.leave_enabled = False
            self.leave_note = 'Abra a reunião no Meet com a extensão instalada antes de ativar a saída automática.'
        else:
            self.leave_note = ('Saída automática ativada somente para a aba vinculada.' if self.leave_enabled
                               else 'Saída automática desligada.')
        self.countdown.enabled = self.leave_enabled
        self.countdown.cancel()
        if self.bridge is not None:
            self.bridge.cancel()

    def _poll_meet(self) -> None:
        if self.bridge is None:
            self.meet_status = self.bridge_error
            self.main_notice = ''
            return
        if self.bridge.target != self.bound_target:
            self.bound_target = self.bridge.target
            self.leave_enabled = False
            self.countdown.enabled = False
            self.countdown.cancel()
            self.leave_note = ''
        connected = self.bridge.connected()
        engine = self.engine
        ready = connected and engine is not None and engine.running and engine.virtual_active
        if engine is not None:
            while True:
                try:
                    when, sent = engine.disappearances.get_nowait()
                except Empty:
                    break
                if self.leave_enabled:
                    self.countdown.enabled = True
                    self.countdown.delay = float(self.leave_delay)
                    armed = self.countdown.arm(monotonic(), ready and sent and monotonic() - when < 1)
                    self.leave_note = '' if armed else ('Não saí do Meet: vincule a extensão e mantenha a câmera '
                                                        'virtual ativa.')
        hidden = engine is not None and engine.hidden and engine.phase == 'hidden'
        if self.countdown.due(monotonic(), hidden, ready):
            requested = self.bridge.request_leave(self.bound_target)
            self.leave_enabled = False
            self.leave_note = '' if requested else 'Não saí do Meet: a extensão não está conectada.'
        if self.countdown.deadline is not None:
            remaining = max(0, self.countdown.deadline - monotonic())
            self.meet_status = f'Saindo do Meet em {remaining:.1f} s. F8 ou desativar o toggle cancela.'
        else:
            self.meet_status = self.leave_note or self.bridge.status
        output_missing = (engine is not None and engine.running and engine.settings.virtual != 'off'
                          and not engine.virtual_active)
        self.main_notice = (self.meet_status if self.countdown.deadline is not None else
                            'Saída automática do Meet ativada' if self.leave_enabled else
                            'Saída virtual indisponível · abra Configurar → Meet' if output_missing else '')

    # Rendering ----------------------------------------------------------------

    def background_description(self) -> str:
        return ('Áreas visíveis ao vivo. O espaço atrás de você usa o fundo aprendido.' if self.dynamic
                else 'Usa a captura vazia inteira. Mais leve e previsível.')

    def tick(self) -> ViewState:
        """Advance pending work and return what the interface should show now."""
        self.accept_devices()
        engine = self.engine
        frame: Frame | None = None
        revision = -1
        progress = 0.0
        fps = 0.0
        phase = 'stopped' if engine is None else engine.phase
        running = engine is not None and engine.running
        if engine is not None:
            frame, status, fps = engine.snapshot()
            revision = engine.preview_revision
            progress = engine.progress
            self.state_text = PHASES.get(phase, phase)
            self.status = status
            self.performance = f'{fps:.1f} FPS · {self.effect}'
            self.hint = engine.vision_hint if phase in ('ready', 'holding', 'hidden') else ''
            self.step = (status.split('\n')[0] if phase == 'error'
                         else STEPS.get(phase, 'Inicie a câmera para continuar.'))
            if phase in ('ready', 'hidden'):
                if engine.effect_error:
                    self.hint = engine.effect_error
                elif engine.gesture_error:
                    self.hint = engine.gesture_error
                elif engine.gesture_release_required:
                    self.hint = 'Baixe ou relaxe a mão por um instante; depois faça o gesto para iniciar a barra.'
                elif engine.message.startswith(('Não ', 'Falha', 'Recorte', 'Modelo')):
                    self.hint = engine.message
        self._poll_sounds()
        self._poll_meet()
        hidden = engine is not None and engine.hidden
        clones = engine is not None and getattr(engine, 'clones', False) is True
        if running:
            primary = (f'Capturar fundo ({self.capture_time} s)' if phase == 'uncalibrated' else 'Confirmar fundo vazio'
                       if phase == 'confirm' else 'Reaparecer' if hidden else 'Dispensar clones' if clones else
                       'Disparar onda' if LABELS.get(self.effect) == 'kamehameha' else
                       'Lançar esfera' if LABELS.get(self.effect) == 'genkidama' else 'Ativar efeito')
            primary_enabled = phase in PRIMARY_PHASES
            start_label = 'Parando…' if engine is not None and engine.stop.is_set() else 'Parar câmera'
            start_enabled = start_label == 'Parar câmera'
        else:
            primary, primary_enabled = 'Iniciar câmera', bool(self.devices)
            start_label, start_enabled = 'Iniciar câmera', bool(self.devices) and not self.scanning
        guide = guide_for(LABELS[self.effect])
        instruction = guide.instruction
        if not guide.motion and guide.kind != 'manual':
            instruction += f' Segure por {self.hold} s.'
        return ViewState(
            running=running, phase=phase, phase_label=self.state_text, hidden=hidden, step=self.step,
            hint=self.hint, status=self.status, progress=progress, fps=fps, performance=self.performance,
            primary_label=primary, primary_enabled=primary_enabled,
            recalibrate_enabled=running and phase in RECALIBRATE_PHASES,
            start_label=start_label, start_enabled=start_enabled,
            inputs_enabled=not running, refresh_enabled=not running and not self.scanning,
            cameras=[device.label for device in self.devices], camera=self.camera,
            effect=self.effect, effects=list(LABELS), resolution=self.resolution, hold=self.hold,
            output=self.output, outputs=list(output_choices()), dynamic_background=self.dynamic,
            background_description=self.background_description(),
            guide_title=guide.title, guide_instruction=instruction, guide_image=guide.image,
            guide_steps=list(guide.steps), output_help=self.output_help,
            virtual_active=engine is not None and engine.virtual_active,
            meet_available=self.bridge is not None,
            meet_connected=self.bridge is not None and self.bridge.connected(),
            meet_extension=self.bridge is not None and self.bridge.extension_connected(),
            sounds=self.sounds, call_sounds=self.call_sounds,
            meet_status=self.meet_status, main_notice=self.main_notice,
            leave_enabled=self.leave_enabled, leave_delay=self.leave_delay,
            capture_time=self.capture_time, snap_delay=self.snap_delay,
            leave_countdown=(None if self.countdown.deadline is None
                             else max(0.0, self.countdown.deadline - monotonic())),
            preview_revision=revision, frame=frame, clones=clones,
            clones_count=int(getattr(engine, 'clones_count', 0)) if clones else 0)
