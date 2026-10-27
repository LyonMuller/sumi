"""Local bridge to the Sumi · Meet browser extension.

The extension has a fixed ID (the public key is in its manifest), so the bridge trusts
requests whose Origin is exactly that extension: no code to copy, no tab to link by hand.
Web pages cannot forge Origin and the Host check blocks DNS rebinding. Loopback only.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from threading import Condition,Lock,Thread
from time import monotonic,time
from typing import Callable
import json
import re
import secrets
import sys

EXTENSION_ID='clbhgcnjgdjmgpbpcbmnjlacncfiiipf'
EXTENSION_ORIGIN=f'chrome-extension://{EXTENSION_ID}'
MEETING=re.compile(r'^[a-z]{3}-[a-z]{4}-[a-z]{3}$')
SOUND_NAME=re.compile(r'^[a-z0-9-]{1,40}$')
SOUND_TYPES={'.wav':'audio/wav','.mp3':'audio/mpeg','.m4a':'audio/mp4','.aiff':'audio/aiff','.ogg':'audio/ogg'}
FRESH=4.0          # a tab (or the extension) silent longer than this is gone
EVENT_TTL=3.0      # sounds older than this are stale and never played
LONG_POLL=20.0

@dataclass(frozen=True)
class MeetTarget:
    meeting:str
    tab:int

@dataclass
class LeaveCountdown:
    enabled:bool=False
    delay:float=2.0
    deadline:float | None=None

    def arm(self,now:float,ready:bool) -> bool:
        self.deadline=now+self.delay if self.enabled and ready else None
        return self.deadline is not None

    def cancel(self) -> None:
        self.deadline=None

    def due(self,now:float,hidden:bool,ready:bool) -> bool:
        if not self.enabled or not hidden or not ready:
            self.cancel()
            return False
        if self.deadline is not None and now>=self.deadline:
            self.cancel()
            self.enabled=False
            return True
        return False

class MeetBridge:
    """Finds the open Meet call by itself, closes only that tab on request and streams effect sounds."""
    def __init__(self,port:int=49321,origin:str=EXTENSION_ORIGIN,
                 sound_path:Callable[[str],Path | None] | None=None) -> None:
        self.lock=Lock()
        self.wake=Condition(self.lock)
        self.origin=origin
        self.sound_path=sound_path
        self.target:MeetTarget | None=None
        self.last_seen=0.0                     # the linked tab
        self.extension_seen=0.0                # any tab with the extension
        self.tabs:dict[int,tuple[str,float,bool]]={}   # tab -> (meeting, seen, focused)
        self.pending:dict[str,str|int] | None=None
        self.last_id=''
        self.call_sounds=True
        self.events:deque[tuple[int,float,str,str]]=deque(maxlen=64)
        self.cursor=0
        self.closing=False
        self.note=''
        self.stale_seen=0.0                    # requests from an old/other copy of the extension
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def setup(self) -> None:
                super().setup()
                self.connection.settimeout(LONG_POLL+5)
            def log_message(self,*args:object) -> None: pass
            def authorized(self) -> bool:
                origin=self.headers.get('Origin','')
                if self.headers.get('Host','')!=f'127.0.0.1:{owner.port}': return False
                if origin==owner.origin: return True
                if re.fullmatch(r'chrome-extension://[a-p]{32}',origin) and self.headers.get('X-Sumi-Token') is not None:
                    # The old Sumi extension (linked by code) is still installed instead of this one.
                    with owner.lock: owner.stale_seen=monotonic()
                return False
            def send(self,code:int,body:bytes,kind:str) -> None:
                self.send_response(code)
                self.send_header('Content-Type',kind)
                self.send_header('Cache-Control','no-store')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def reply(self,code:int,data:dict[str,object]) -> None:
                self.send(code,json.dumps(data).encode('utf-8'),'application/json')
            def do_GET(self) -> None:
                self.reply(405 if self.authorized() else 403,{'error':'use POST'})
            def do_POST(self) -> None:
                if not self.authorized():
                    owner._log(f'recusado {self.path} origem={self.headers.get("Origin","")!r} host={self.headers.get("Host","")!r}')
                    self.reply(403,{'error':'unauthorized'}); return
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=2048: raise ValueError('length')
                    data=json.loads(self.rfile.read(length))
                    if not isinstance(data,dict): raise ValueError('object')
                except (ValueError,TypeError):
                    self.reply(400,{'error':'invalid body'}); return
                if self.path=='/sync': self.reply(*owner._sync(data))
                elif self.path=='/result': self.reply(*owner._result(data))
                elif self.path=='/events': self.reply(*owner._events(data))
                elif self.path=='/sound':
                    found=owner._sound(data.get('name'))
                    if found is None: self.reply(404,{'error':'not found'})
                    else: self.send(200,*found)
                else: self.reply(404,{'error':'not found'})
        self.server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
        self.server.daemon_threads=True
        self.port=self.server.server_address[1]
        self.thread=Thread(target=self.server.serve_forever,daemon=True,name='meet-local')
        self.thread.start()

    # Requests from the extension ------------------------------------------------

    def _sync(self,data:dict[str,object]) -> tuple[int,dict[str,object]]:
        """Heartbeat from one browser tab; links the call automatically and hands out the leave command."""
        meeting=data.get('meeting'); tab=data.get('tab'); focused=data.get('focused') is True
        if meeting is not None and (not isinstance(meeting,str) or not MEETING.fullmatch(meeting)
                                    or type(tab) is not int or tab<0):
            self._log(f'aba recusada: reunião={meeting!r} aba={tab!r}')
            return 400,{'error':'invalid target'}
        self._log(f'aba {tab}: ' + (f'reunião {meeting}' if meeting else 'Meet sem reunião aberta'))
        now=monotonic()
        with self.lock:
            if now-self.extension_seen>=FRESH: self._log('extensão conectada')
            self.extension_seen=now
            if isinstance(meeting,str) and type(tab) is int:
                self.tabs[tab]=(meeting,now,focused)
            elif type(tab) is int:
                self.tabs.pop(tab,None)
            self._choose(now)
            command=None
            target=self.target
            if target is not None and isinstance(meeting,str) and type(tab) is int and target==MeetTarget(meeting,tab):
                self.last_seen=now
                if self.pending is not None:
                    if time()*1000<float(self.pending['expires']): command=self.pending
                    else: self.note='Pedido expirado; nenhuma aba foi fechada.'
                    self.pending=None
            linked=None if target is None else {'meeting':target.meeting,'tab':target.tab}
            return 200,{'command':command,'target':linked,'sounds':self.call_sounds}

    def _choose(self,now:float) -> None:
        """Keep the linked call while it is alive; otherwise prefer the focused one, then the newest."""
        for tab in [tab for tab,(_,seen,_) in self.tabs.items() if now-seen>=FRESH]:
            del self.tabs[tab]
        current=self.target
        if current is not None and self.tabs.get(current.tab,('',0.0,False))[0]==current.meeting:
            return
        if not self.tabs:
            if current is not None and now-self.last_seen>=FRESH:
                self.target=None
                self.pending=None
            return
        tab,(meeting,seen,_)=max(self.tabs.items(),key=lambda item:(item[1][2],item[1][1]))
        self.target=MeetTarget(meeting,tab)
        self._log(f'reunião {meeting} vinculada (aba {tab})')
        self.last_seen=seen
        self.pending=None
        self.note=''

    def _result(self,data:dict[str,object]) -> tuple[int,dict[str,object]]:
        with self.lock:
            if data.get('id')==self.last_id:
                self.note=('A aba da reunião foi fechada.' if data.get('closed') is True
                           else 'A extensão recusou fechar: a aba mudou ou a conexão caiu.')
        return 200,{'ok':True}

    def _events(self,data:dict[str,object]) -> tuple[int,dict[str,object]]:
        """Long poll: answers as soon as there is a sound newer than `since`."""
        since=data.get('since')
        deadline=monotonic()+LONG_POLL
        with self.wake:
            if type(since) is not int or since<0 or since>self.cursor:
                return 200,{'cursor':self.cursor,'events':[]}
            while not self.closing and self.cursor==since:
                left=deadline-monotonic()
                if left<=0: break
                self.wake.wait(left)
            now=monotonic()
            fresh=[{'action':action,'name':name} for seq,at,action,name in self.events
                   if seq>since and now-at<EVENT_TTL]
            return 200,{'cursor':self.cursor,'events':fresh}

    def _sound(self,name:object) -> tuple[bytes,str] | None:
        if not isinstance(name,str) or not SOUND_NAME.fullmatch(name) or self.sound_path is None:
            return None
        path=self.sound_path(name)
        if path is None or path.suffix.lower() not in SOUND_TYPES: return None
        try:
            if path.stat().st_size>8_000_000: return None
            return path.read_bytes(),SOUND_TYPES[path.suffix.lower()]
        except OSError:
            return None

    def _log(self,text:str) -> None:
        # Throttled diagnostics in the engine log; never the audio or page contents.
        now=monotonic()
        if text==getattr(self,'_last_log',('',0.0))[0] and now-self._last_log[1]<30: return
        self._last_log=(text,now)
        print(f'[meet] {text}',file=sys.stderr,flush=True)

    # Used by the app --------------------------------------------------------------

    def emit(self,action:str,name:str='') -> None:
        """Queue a sound for the call: action is play, loop, stop or stop_all."""
        with self.wake:
            if not self.call_sounds or self.target is None: return
            self.cursor+=1
            self.events.append((self.cursor,monotonic(),action,name))
            self.wake.notify_all()

    def extension_connected(self) -> bool:
        with self.lock: return monotonic()-self.extension_seen<FRESH

    def connected(self) -> bool:
        with self.lock: return self.target is not None and monotonic()-self.last_seen<FRESH

    @property
    def status(self) -> str:
        now=monotonic()
        with self.lock:
            if now-self.extension_seen>=FRESH and now-self.stale_seen<FRESH*2:
                return ('Extensão antiga detectada. Em chrome://extensions, remova a Sumi · Meet antiga e '
                        'carregue a nova (Ajustes → Meet → Instalar no Chrome…).')
            if now-self.extension_seen>=FRESH:
                return 'Extensão não detectada. Instale a extensão Sumi · Meet no Chrome (Configurações → Meet).'
            if self.note: return self.note
            if self.target is None or now-self.last_seen>=FRESH:
                return 'Extensão conectada. Entre em uma reunião do Meet e ela será vinculada sozinha.'
            return f'Reunião {self.target.meeting} vinculada automaticamente.'

    def request_leave(self,expected:MeetTarget | None=None) -> bool:
        with self.lock:
            if self.target is None or monotonic()-self.last_seen>=FRESH or (expected is not None and self.target!=expected): return False
            self.last_id=secrets.token_hex(12)
            self.pending={'id':self.last_id,'action':'leave','meeting':self.target.meeting,'tab':self.target.tab,'expires':int((time()+4)*1000)}
            self.note=f'Saída solicitada para {self.target.meeting}; aguardando a extensão.'
            return True

    def cancel(self) -> None:
        with self.lock:
            self.pending=None
            if self.note.startswith('Saída solicitada'): self.note=''

    def close(self) -> None:
        with self.wake:
            self.pending=None
            self.closing=True
            self.wake.notify_all()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
