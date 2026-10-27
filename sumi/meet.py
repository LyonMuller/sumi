from __future__ import annotations
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from threading import Lock,Thread
from time import monotonic,time
from urllib.parse import urlparse,parse_qs
import hmac
import json
import re
import secrets
from .paths import data_file

MEETING=re.compile(r'^[a-z]{3}-[a-z]{4}-[a-z]{3}$')

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
    """Loopback-only, authenticated, single-tab command bridge. No public endpoints."""
    def __init__(self,port:int=49321,key_path:Path | None=None,token:str | None=None) -> None:
        self.lock=Lock()
        if token is None:
            key_path=key_path or data_file('.meet_pairing_key')
            if key_path.exists(): token=key_path.read_text(encoding='utf-8').strip()
            else:
                token=secrets.token_urlsafe(32)
                key_path.write_text(token,encoding='utf-8')
            if len(token)<32: raise ValueError('Código de conexão inválido. Remova .meet_pairing_key e reinicie.')
        self.token=token
        self.target:MeetTarget | None=None
        self.last_seen=0.0
        self.pending:dict[str,str|int] | None=None
        self.last_id=''
        self.status='Meet não vinculado. Configure a extensão local.'
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def setup(self) -> None:
                super().setup()
                self.connection.settimeout(3)
            def log_message(self,*args:object) -> None: pass
            def authorized(self) -> bool:
                origin=self.headers.get('Origin','')
                local_host=self.headers.get('Host','')==f'127.0.0.1:{owner.port}'
                extension_origin=not origin or re.fullmatch(r'chrome-extension://[a-p]{32}',origin) is not None
                return local_host and extension_origin and hmac.compare_digest(self.headers.get('X-Sumi-Token',''),owner.token)
            def reply(self,code:int,data:dict[str,object]) -> None:
                body=json.dumps(data).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type','application/json')
                self.send_header('Cache-Control','no-store')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def do_GET(self) -> None:
                if not self.authorized():
                    self.reply(403,{'error':'unauthorized'}); return
                parsed=urlparse(self.path)
                if parsed.path!='/command': self.reply(404,{'error':'not found'}); return
                query=parse_qs(parsed.query)
                try: tab=int(query.get('tab',[''])[0])
                except ValueError: self.reply(400,{'error':'tab'}); return
                meeting=query.get('meeting',[''])[0]
                with owner.lock:
                    target=owner.target
                    command=None
                    if target is not None and target==MeetTarget(meeting,tab):
                        owner.last_seen=monotonic()
                        if owner.pending is not None:
                            if time()*1000<float(owner.pending['expires']): command=owner.pending
                            else: owner.status='Pedido expirado; nenhuma aba foi fechada.'
                            owner.pending=None
                    self.reply(200,{'command':command})
            def do_POST(self) -> None:
                if not self.authorized():
                    self.reply(403,{'error':'unauthorized'}); return
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=2048: raise ValueError('length')
                    data=json.loads(self.rfile.read(length))
                    if not isinstance(data,dict): raise ValueError('object')
                except (ValueError,TypeError):
                    self.reply(400,{'error':'invalid body'}); return
                if self.path=='/pair':
                    meeting=data.get('meeting'); tab=data.get('tab')
                    if not isinstance(meeting,str) or not MEETING.fullmatch(meeting) or type(tab) is not int or tab<0:
                        self.reply(400,{'error':'invalid target'}); return
                    with owner.lock:
                        owner.target=MeetTarget(meeting,tab)
                        owner.last_seen=monotonic()
                        owner.pending=None
                        owner.status=f'Meet vinculado: {meeting}. Saída automática desligada até ser ativada no aplicativo.'
                    self.reply(200,{'ok':True})
                elif self.path=='/result':
                    with owner.lock:
                        if data.get('id')==owner.last_id:
                            owner.status='A aba vinculada do Meet foi fechada.' if data.get('closed') is True else 'A extensão recusou fechar: aba mudou ou conexão interrompida.'
                    self.reply(200,{'ok':True})
                else: self.reply(404,{'error':'not found'})
        self.server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
        self.server.daemon_threads=True
        self.port=self.server.server_address[1]
        self.thread=Thread(target=self.server.serve_forever,daemon=True,name='meet-local')
        self.thread.start()

    def connected(self) -> bool:
        with self.lock: return self.target is not None and monotonic()-self.last_seen<4

    def request_leave(self,expected:MeetTarget | None=None) -> bool:
        with self.lock:
            if self.target is None or monotonic()-self.last_seen>=4 or (expected is not None and self.target!=expected): return False
            self.last_id=secrets.token_hex(12)
            self.pending={'id':self.last_id,'action':'leave','meeting':self.target.meeting,'tab':self.target.tab,'expires':int((time()+4)*1000)}
            self.status=f'Saída solicitada para {self.target.meeting}; aguardando a extensão.'
            return True

    def cancel(self) -> None:
        with self.lock: self.pending=None

    def close(self) -> None:
        self.cancel()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
