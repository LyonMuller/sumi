from __future__ import annotations
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Lock, Thread
from time import monotonic
import cv2
import numpy as np
from .virtual_output import VirtualOutput
from .gesture import HoldGate
from .gesture_guides import guide_for
from .scene import Frame, Scene
from .vision import Detector, Segmenter
from .effects import Silhouette, TeleportEffect
from .effects_energy import EnergyCharge
from .effects_spirit import SpiritCharge
from .effect_catalog import EFFECTS
from .background import LiveBackground
from .paths import resource_root
from .system import camera_backends

@dataclass(frozen=True)
class Settings:
    camera: int = 0
    camera_backend: int | None = None
    width: int = 1280
    height: int = 720
    fps: int = 30
    hold: float = 1.0
    virtual: str = 'obs'
    effect: str = 'goku'
    dynamic_background: bool = False

class Engine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.dynamic_background = settings.dynamic_background
        self.effect_mode = settings.effect
        self.preview_revision = 0
        # Set on every published frame so a shell can present it without polling.
        self.frame_ready = Event()
        self.stop = Event()
        self.commands: Queue[str] = Queue()
        self.lock = Lock()
        self.raw: tuple[float, Frame] | None = None
        self.observation = (0.0, False, -1)
        self.observation_effect = settings.effect
        self.gesture_progress = 0.0
        self.gesture_release_required = False
        self.silhouette: Silhouette | None = None
        self.need_silhouette = Event()
        self.disappearances: Queue[tuple[float,bool]] = Queue()
        # Sounds for the app to play: (action, name), action is play, loop, stop or stop_all.
        self.sounds: Queue[tuple[str,str]] = Queue()
        self.virtual_active = False
        self.background_status = ''
        self.preview: Frame | None = None
        self.message = 'Abrindo webcam…'
        self.phase = 'opening'
        self.hidden = False
        self.clones = False
        self.clones_count = 0
        self.observation_extra = False
        # Energy wave: (captured at, charge pose held, charge 0..1, where the hands meet in frame pixels).
        self.wave_obs: tuple[float, bool, float, tuple[float, float, float] | None] = (0.0, False, 0.0, None)
        self.observation_seen = 0.0
        self.charging = False
        self.virtual_status = 'Saída virtual desligada'
        self.gesture_error = ''
        self.effect_error = ''
        self.vision_hint = 'Preparando reconhecimento…'
        self.fps = 0.0
        self.progress = 0.0
        self.running = True
        self.thread = Thread(target=self._run, daemon=True, name='video')
        self.thread.start()

    def snapshot(self) -> tuple[Frame | None, str, float]:
        with self.lock:
            notes = [self.message, self.virtual_status, self.gesture_error, self.effect_error, self.background_status]
            return (None if self.preview is None else self.preview.copy(),
                    '\n'.join(note for note in notes if note), self.fps)

    def _set_message(self, text: str) -> None:
        with self.lock:
            self.message = text

    @staticmethod
    def _clones_text(count: int) -> str:
        if count >= 8:
            return f'Clones ativos ({count}). Cruze os dedos para dispensá-los.'
        return f'Clones ativos ({count}). Faça o selo de uma mão para chamar mais, ou cruze os dedos para dispensá-los.'

    def _inference(self) -> None:
        detector: Detector | None = None
        segmenter: Segmenter | None = None
        folder=resource_root()/'models'
        try:
            try:
                detector=Detector(folder)
            except Exception as error:
                self.gesture_error=f'Gesto indisponível: {error}. Use o botão Ativar efeito.'
            segment_attempted=False
            if self.effect_mode in EFFECTS or self.dynamic_background:
                segment_attempted=True
                try:
                    segmenter=Segmenter(folder)
                except Exception as error:
                    self.effect_error=f'Recorte indisponível: {error}. Usando fundo salvo e corte instantâneo.'
            previous=-1.0
            previous_mask=-1.0
            while not self.stop.is_set():
                began=monotonic()
                if not segment_attempted and (self.effect_mode in EFFECTS or self.dynamic_background):
                    segment_attempted=True
                    try: segmenter=Segmenter(folder)
                    except Exception as error: self.effect_error=f'Recorte indisponível: {error}. Usando fundo estático.'
                with self.lock:
                    raw=self.raw
                if raw is not None and raw[0]>previous:
                    previous=raw[0]
                    if detector is not None:
                        try:
                            # While clones stand, the cross dismisses them and the one-hand seal adds a wave.
                            mode='clones' if self.clones else self.effect_mode
                            matched,count=detector.detect(raw[1],raw[0],mode,'puff' if self.clones else None)
                            with self.lock:
                                # A motion pulse lasts one detection: keep it until the render loop has looked at it.
                                seen_at,seen_match,_=self.observation
                                if (guide_for(mode).motion and not matched and seen_match and seen_at>self.observation_seen
                                        and self.observation_effect==mode):
                                    matched=True
                                self.observation=(raw[0],matched,count)
                                self.wave_obs=(raw[0],detector.charging,detector.charge,detector.ball)
                                self.observation_effect=mode
                                self.observation_extra=detector.extra_matched
                                self.gesture_progress=detector.progress
                                self.vision_hint=detector.hint
                        except Exception as error:
                            self.gesture_error=f'Falha no gesto: {error}. Use os controles manuais.'
                            detector.close()
                            detector=None
                            with self.lock:
                                self.observation=(0.0,False,-1)
                                self.wave_obs=(0.0,False,0.0,None)
                    if segmenter is not None and self.need_silhouette.is_set() and raw[0]-previous_mask>=0.16:
                        try:
                            silhouette=segmenter.capture(raw[1],raw[0])
                            previous_mask=raw[0]
                            with self.lock:
                                self.silhouette=silhouette
                        except Exception as error:
                            self.effect_error=f'Recorte indisponível: {error}. Será usado corte instantâneo.'
                            segmenter.close()
                            segmenter=None
                rate=30 if guide_for(self.effect_mode).motion else 15
                self.stop.wait(max(0.001,1/rate-(monotonic()-began)))
        finally:
            if detector is not None: detector.close()
            if segmenter is not None: segmenter.close()

    def _open_capture(self) -> cv2.VideoCapture:
        # An enumerated index must not be reused against a different backend.
        backends=(self.settings.camera_backend,) if self.settings.camera_backend is not None else camera_backends()
        for backend in backends:
            capture=cv2.VideoCapture(self.settings.camera,backend)
            if capture.isOpened():
                # MJPG raises USB throughput on Windows; AVFoundation ignores it.
                capture.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'))
                capture.set(cv2.CAP_PROP_FRAME_WIDTH,self.settings.width)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT,self.settings.height)
                capture.set(cv2.CAP_PROP_FPS,self.settings.fps)
                capture.set(cv2.CAP_PROP_BUFFERSIZE,1)
                return capture
            capture.release()
        raise RuntimeError('Webcam indisponível. Atualize a lista, confira permissões e feche outras aplicações que a utilizam.')

    def _open_virtual(self,width:int,height:int) -> VirtualOutput | None:
        if self.settings.virtual=='off': return None
        try:
            virtual=VirtualOutput(width,height,self.settings.fps,self.settings.virtual)
            self.virtual_status=f'Saída: {virtual.device} · {width} × {height}'
            return virtual
        except (RuntimeError,OSError,ValueError) as error:
            self.virtual_status=f'Saída virtual indisponível: {error}. Instale/libere o driver e reconecte a saída.'
            return None

    def _run(self) -> None:
        capture:cv2.VideoCapture | None=None
        virtual:VirtualOutput | None=None
        inference:Thread | None=None
        scene=Scene()
        adaptive=LiveBackground()
        if scene.background is not None: adaptive.reset(scene.background)
        announced_hidden=False
        clones_on=False
        clones_effect:TeleportEffect | None=None
        gate=HoldGate(self.settings.hold)
        seal_gate=HoldGate(self.settings.hold)
        # Charged effects: a live ball while the pose is held, then a one-shot `action` effect.
        charges={'kamehameha':EnergyCharge(),'genkidama':SpiritCharge()}
        wave_fx=charges['kamehameha']
        wave_was_charging=False
        charge_sound='kamehameha-charge'
        arrival_message_at:float | None=None
        effect:TeleportEffect | None=None
        requested:float | None=None
        calibration:float | None=None
        samples:list[Frame]=[]
        calibration_face=False
        previous_observation=0.0
        virtual_attempted=False
        failed_reads=0
        measured=monotonic()
        count=0
        try:
            capture=self._open_capture()
            inference=Thread(target=self._inference,daemon=True,name='recognition')
            inference.start()
            self.phase='uncalibrated'
            self._set_message('Webcam aberta. Capture e confirme o fundo vazio.')
            while not self.stop.is_set():
                tick=monotonic()
                ok,frame=capture.read()
                if not ok or frame is None:
                    failed_reads+=1
                    gate.reset();seal_gate.reset()
                    self.progress=0
                    self._set_message('Falha de leitura. Tentando recuperar a webcam…')
                    if failed_reads>=15:
                        raise RuntimeError('Webcam desconectada. Pare e inicie novamente para reconectar.')
                    self.stop.wait(0.05)
                    continue
                failed_reads=0
                now=monotonic()
                with self.lock:
                    self.raw=(now,frame)
                    observed_at,matched,faces=self.observation
                    observed_effect=self.observation_effect
                    seal_matched=self.observation_extra
                    motion_progress=self.gesture_progress
                    wave_at,wave_pose,wave_charge,wave_ball=self.wave_obs
                    self.observation_seen=observed_at
                    silhouette=self.silhouette
                height,width=frame.shape[:2]
                gesture_mode='clones' if clones_on else self.effect_mode
                if gesture_mode in charges and charges[gesture_mode] is not wave_fx:
                    wave_fx.reset()
                    wave_fx=charges[gesture_mode]
                    if wave_was_charging: self.sounds.put(('stop',charge_sound))
                    wave_was_charging=False
                summon_requested=False
                if not virtual_attempted:
                    virtual=self._open_virtual(width,height)
                    virtual_attempted=True
                    self.virtual_active=virtual is not None
                while True:
                    try: command=self.commands.get_nowait()
                    except Empty: break
                    gate.reset();seal_gate.reset()
                    previous_observation=now
                    if command in ('restore','calibrate'):
                        wave_fx.reset()
                        self.sounds.put(('stop_all',''))
                        if command=='restore' and (scene.hidden or clones_on): self.sounds.put(('play','restore'))
                    if command=='restore':
                        effect=None
                        requested=None
                        clones_on=False
                        clones_effect=None
                        arrival_message_at=None
                        scene.restore()
                        scene.pending=None
                        calibration=None
                        self._set_message('Imagem ao vivo restaurada.')
                    elif command=='calibrate':
                        effect=None
                        requested=None
                        clones_on=False
                        clones_effect=None
                        arrival_message_at=None
                        calibration=now
                        samples.clear()
                        calibration_face=False
                        scene.pending=None
                    elif command=='confirm':
                        try:
                            scene.confirm()
                            adaptive.reset(scene.background)
                            self._set_message('Fundo confirmado. Prepare o gesto indicado para o efeito selecionado.')
                        except ValueError as error: self._set_message(str(error))
                    elif command=='toggle' and calibration is None and scene.pending is None and effect is None and requested is None:
                        if scene.background is None:
                            self._set_message('Capture e confirme o fundo primeiro.')
                        else: requested=now
                    elif command in ('background:live','background:static'):
                        self.dynamic_background=command=='background:live'
                        if scene.background is not None: adaptive.reset(scene.background)
                        self._set_message('Fundo em movimento ativado.' if self.dynamic_background else 'Fundo estático ativado.')
                    elif command.startswith('effect:'):
                        mode=command.partition(':')[2]
                        if mode in EFFECTS or mode=='instant':
                            self.effect_mode=mode
                            self._set_message('Efeito selecionado para a próxima ativação.')
                    elif command=='virtual':
                        if virtual is not None: virtual.close()
                        virtual=self._open_virtual(width,height)
                        self.virtual_active=virtual is not None
                if calibration is not None:
                    elapsed=now-calibration
                    self._set_message(f'Saia do enquadramento. Capturando em {max(0,4-elapsed):.1f} s…')
                    if elapsed>=3.3:
                        samples.append(frame.copy())
                        samples=samples[-16:]
                        if now-observed_at<0.3 and faces>0: calibration_face=True
                    if elapsed>=4:
                        try:
                            if calibration_face: raise ValueError('Rosto detectado. Repita com o cenário vazio.')
                            scene.propose(samples)
                            self._set_message('Confira o fundo na prévia. Se estiver vazio, confirme abaixo.')
                        except ValueError as error: self._set_message(str(error))
                        samples.clear()
                        calibration=None
                    gate.reset();seal_gate.reset()
                elif scene.pending is None and scene.background is not None and effect is None and requested is None:
                    if now-observed_at>0.3 or observed_effect!=gesture_mode:
                        gate.reset();seal_gate.reset()
                    elif observed_at>previous_observation:
                        previous_observation=observed_at
                        if guide_for(gesture_mode).motion:
                            if matched: requested=now
                        elif guide_for(gesture_mode).kind!='manual' and gate.update(matched,observed_at): requested=now
                        if clones_on and seal_gate.update(seal_matched,observed_at): summon_requested=True
                else:
                    gate.reset();seal_gate.reset()
                guide=guide_for(gesture_mode)
                self.gesture_release_required=(not guide.motion and guide.kind!='manual' and matched and not gate.armed
                    and now-observed_at<.3 and observed_effect==gesture_mode and calibration is None
                    and scene.pending is None and scene.background is not None and effect is None and requested is None)
                self.progress=(motion_progress if guide.motion and now-observed_at<.3 and observed_effect==gesture_mode else 0) if guide.motion else max(gate.progress,seal_gate.progress if clones_on else 0)
                # Energy wave: the ball follows the hands while the charge pose is held (never part of `hidden`).
                if (gesture_mode in charges and calibration is None and scene.pending is None and scene.background is not None
                        and effect is None and requested is None and not scene.hidden
                        and now-wave_at<.3 and observed_effect==gesture_mode):
                    wave_subject=silhouette if silhouette is not None and now-silhouette.captured_at<=.5 and silhouette.frame.shape==frame.shape else None
                    wave_fx.update(now,wave_ball,wave_charge,wave_pose,wave_subject)
                elif requested is None and wave_fx.state!='idle':
                    wave_fx.update(now,None,0.0,False,None)
                if wave_fx.charging and not wave_was_charging:
                    self._set_message('Reunindo energia…' if gesture_mode=='genkidama' else 'Carregando a onda…')
                    charge_sound=f'{gesture_mode}-charge'
                    self.sounds.put(('loop',charge_sound))
                elif wave_was_charging and not wave_fx.charging and requested is None:
                    self._set_message('A esfera se desfez. Erga as duas mãos de novo.' if gesture_mode=='genkidama'
                                      else 'A onda se desfez. Junte as mãos de novo para carregar.')
                    self.sounds.put(('stop',charge_sound))
                wave_was_charging=wave_fx.charging
                if summon_requested and clones_on and clones_effect is not None and effect is None:
                    fresh_now=silhouette if silhouette is not None and now-silhouette.captured_at<=0.5 else None
                    if clones_effect.summon(fresh_now,now):
                        arrival_message_at=now+clones_effect.arrival
                        self.sounds.put(('play','clones-wave'))
                        self._set_message('Mais clones chegando…')
                    else:
                        self._set_message('Máximo de clones.')
                    seal_gate.reset()
                if arrival_message_at is not None and now>=arrival_message_at:
                    arrival_message_at=None
                    if clones_on and clones_effect is not None and effect is None:
                        self._set_message(self._clones_text(clones_effect.count))
                if requested is not None:
                    wants_goku=self.effect_mode in EFFECTS and not self.effect_error
                    fresh=(silhouette is not None and now-silhouette.captured_at<=0.35 and silhouette.frame.shape==frame.shape)
                    action=getattr(EFFECTS.get(self.effect_mode),'action',False)
                    if wants_goku and not fresh and not action and now-requested<0.8:
                        self._set_message('Preparando recorte para o efeito…')
                    elif clones_on and clones_effect is not None:
                        # Any toggle while clones stand dismisses them; the person never hides.
                        try:
                            effect=type(clones_effect)(clones_effect.last_subject,False,now,carry=clones_effect)
                            clones_on=False
                            self.sounds.put(('play','clones'))
                            self._set_message('Dispensando os clones…')
                        except ValueError as error:
                            clones_on=False
                            clones_effect=None
                            self._set_message(str(error))
                        requested=None
                        gate.reset();seal_gate.reset()
                    elif getattr(EFFECTS.get(self.effect_mode),'persistent',False):
                        if scene.hidden:
                            self._set_message('Volte à imagem ao vivo antes de chamar os clones.')
                        elif wants_goku and fresh and silhouette is not None:
                            try:
                                effect=EFFECTS[self.effect_mode](silhouette,True,now)
                                clones_effect=effect
                                clones_on=True
                                self.sounds.put(('play','clones'))
                                self._set_message('Os clones estão chegando…')
                            except ValueError as error:
                                self._set_message(str(error))
                        else:
                            self._set_message('Os clones precisam do recorte da pessoa, que está indisponível.')
                        requested=None
                        gate.reset();seal_gate.reset()
                    elif action:
                        # One-shot that keeps you on stage: fire from where the hands are; the cut-out only adds light.
                        if scene.hidden:
                            self._set_message('Volte à imagem ao vivo antes de disparar a onda.')
                        else:
                            fresh_hands=now-wave_at<.3 and observed_effect==self.effect_mode and wave_ball is not None
                            ball=wave_ball if fresh_hands else wave_fx.ball
                            try:
                                effect=EFFECTS[self.effect_mode](silhouette if fresh and silhouette is not None else None,False,now,
                                                                  ball=ball,charge=wave_charge if fresh_hands else max(wave_fx.level,.7),
                                                                  shape=frame.shape[:2])
                                self.sounds.put(('play',f'{self.effect_mode}-fire'))
                                self._set_message('Esfera lançada!' if self.effect_mode=='genkidama' else 'Onda disparada!')
                            except ValueError as error:
                                self._set_message(str(error))
                        wave_fx.reset()
                        wave_was_charging=False
                        self.sounds.put(('stop',charge_sound))
                        requested=None
                        gate.reset();seal_gate.reset()
                    else:
                        target=not scene.hidden
                        if wants_goku and fresh and silhouette is not None:
                            try:
                                effect_class=EFFECTS[self.effect_mode]
                                effect=effect_class(silhouette,target,now)
                                scene.toggle()
                                self.sounds.put(('play',self.effect_mode))
                                self._set_message('Efeito em andamento…')
                            except ValueError as error:
                                self._set_message(str(error))
                        else:
                            scene.toggle()
                            self._set_message('Corte instantâneo aplicado: recorte indisponível.' if wants_goku else ('Desaparecido.' if scene.hidden else 'Imagem ao vivo.'))
                        requested=None
                        gate.reset();seal_gate.reset()
                try:
                    background=scene.background
                    if self.dynamic_background and background is not None and calibration is None and scene.pending is None:
                        if silhouette is not None and now-silhouette.captured_at<=0.35:
                            adaptive.observe(silhouette.frame,silhouette.mask,silhouette.captured_at)
                        if scene.hidden or effect is not None:
                            background=adaptive.render(frame,scene.background,now)
                            self.background_status=adaptive.status
                        else:
                            self.background_status='Fundo adaptativo aprendendo as áreas visíveis.'
                    else:
                        self.background_status='Fundo estático.' if scene.background is not None else ''
                    if effect is not None and background is not None:
                        output=effect.render(frame,background,now)
                        if effect.finished(now):
                            persistent=getattr(effect,'persistent',False)
                            one_shot=getattr(effect,'action',False)
                            if persistent and not clones_on: clones_effect=None
                            effect=None
                            gate.reset();seal_gate.reset()
                            previous_observation=now
                            self._set_message(self._clones_text(clones_effect.count) if persistent and clones_on and clones_effect is not None else
                                'Onda disparada! Baixe as mãos para carregar de novo.' if one_shot else
                                'Clones dispensados.' if persistent else
                                'Desaparecido. Baixe a mão e repita para voltar.' if scene.hidden else 'Imagem ao vivo. Baixe a mão para armar o próximo gesto.')
                    elif clones_on and clones_effect is not None and not scene.hidden:
                        if silhouette is not None and now-silhouette.captured_at<=0.5:
                            clones_effect.feed(silhouette)
                        output=clones_effect.render_steady(frame,scene.background,now)
                    else:
                        output=scene.render(frame)
                        if scene.hidden and background is not None: output=background.copy()
                        elif wave_fx.active(now): output=wave_fx.render(frame,now)
                except ValueError as error:
                    gate.reset();seal_gate.reset()
                    effect=None
                    requested=None
                    clones_on=False
                    clones_effect=None
                    self._set_message(str(error))
                    output=np.zeros_like(frame)
                self.hidden=scene.hidden
                self.charging=wave_fx.charging
                self.clones=clones_on
                self.clones_count=clones_effect.count if clones_on and clones_effect is not None else 0
                self.phase=('calibrating' if calibration is not None else 'confirm' if scene.pending is not None else
                            'teleporting' if effect is not None or requested is not None else 'uncalibrated' if scene.background is None else
                            'hidden' if scene.hidden else 'holding' if gate.progress>0 or wave_fx.charging else 'ready')
                if scene.background is not None and (self.effect_mode in EFFECTS or self.dynamic_background or clones_on) and (effect is None or clones_on or self.dynamic_background) and calibration is None and scene.pending is None:
                    self.need_silhouette.set()
                else: self.need_silhouette.clear()
                output_sent=False
                if virtual is not None:
                    try:
                        virtual.send(np.ascontiguousarray(output))
                        output_sent=True
                    except (RuntimeError,OSError,ValueError) as error:
                        virtual.close()
                        virtual=None
                        self.virtual_active=False
                        self.virtual_status=f'Falha da câmera virtual: {error}. Use Reconectar saída.'
                if scene.hidden and effect is None and requested is None:
                    if not announced_hidden:
                        self.disappearances.put((monotonic(),output_sent))
                        announced_hidden=True
                else:
                    announced_hidden=False
                count+=1
                if now-measured>=1:
                    self.fps=count/(now-measured)
                    measured,count=now,0
                with self.lock:
                    self.preview=scene.pending.copy() if scene.pending is not None else output
                    self.preview_revision+=1
                self.frame_ready.set()
                self.stop.wait(max(0,1/self.settings.fps-(monotonic()-tick)))
        except Exception as error:
            self.phase='error'
            self._set_message(str(error))
        finally:
            self.stop.set()
            if capture is not None: capture.release()
            if virtual is not None: virtual.close()
            if inference is not None: inference.join(timeout=2)
            if self.phase!='error': self.phase='stopped'
            self.virtual_active=False
            self.running=False
