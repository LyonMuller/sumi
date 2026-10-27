import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from time import monotonic
from sumi.meet import EXTENSION_ORIGIN,LeaveCountdown,MeetBridge,MeetTarget

class CountdownTests(unittest.TestCase):
    def test_default_off_and_no_output_does_not_arm(self):
        timer=LeaveCountdown()
        self.assertFalse(timer.arm(10,True))
        timer.enabled=True
        self.assertFalse(timer.arm(10,False))
    def test_fires_once_after_delay(self):
        timer=LeaveCountdown(enabled=True,delay=2)
        timer.arm(10,True)
        self.assertFalse(timer.due(11.9,True,True))
        self.assertTrue(timer.due(12,True,True))
        self.assertFalse(timer.due(13,True,True))
        self.assertFalse(timer.enabled)
    def test_restore_disconnect_and_toggle_off_cancel(self):
        for hidden,ready,enabled in ((False,True,True),(True,False,True),(True,True,False)):
            timer=LeaveCountdown(enabled=True); timer.arm(10,True); timer.enabled=enabled
            self.assertFalse(timer.due(13,hidden,ready)); self.assertIsNone(timer.deadline)
    def test_manual_cancel(self):
        timer=LeaveCountdown(enabled=True); timer.arm(10,True); timer.cancel()
        self.assertFalse(timer.due(13,True,True))

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.folder=Path(tempfile.mkdtemp())
        (self.folder/'puff.wav').write_bytes(b'RIFFfake')
        self.bridge=MeetBridge(port=0,sound_path=lambda name:(self.folder/f'{name}.wav') if (self.folder/f'{name}.wav').exists() else None)
        self.addCleanup(self.bridge.close)
    def raw(self,path,body,headers=None):
        request=urllib.request.Request(f'http://127.0.0.1:{self.bridge.port}'+path,data=json.dumps(body).encode(),
            headers={'Origin':EXTENSION_ORIGIN,'Content-Type':'application/json',**(headers or {})})
        try:
            with urllib.request.urlopen(request,timeout=25) as response: return response.read()
        except urllib.error.HTTPError as error:
            error.close()
            raise
    def request(self,path,body,headers=None):
        return json.loads(self.raw(path,body,headers))
    def sync(self,tab=17,meeting='abc-defg-hij',focused=True):
        return self.request('/sync',{'meeting':meeting,'tab':tab,'focused':focused})

    def test_links_the_open_meeting_without_any_code(self):
        self.assertFalse(self.bridge.extension_connected())
        self.assertIn('não detectada',self.bridge.status)
        data=self.sync()
        self.assertEqual(data['target'],{'meeting':'abc-defg-hij','tab':17})
        self.assertTrue(self.bridge.connected())
        self.assertIn('vinculada automaticamente',self.bridge.status)
    def test_extension_without_meeting_is_detected_but_not_linked(self):
        data=self.request('/sync',{'meeting':None,'tab':3,'focused':True})
        self.assertIsNone(data['target'])
        self.assertTrue(self.bridge.extension_connected())
        self.assertFalse(self.bridge.connected())
    def test_keeps_the_linked_call_and_prefers_focus_for_a_new_one(self):
        self.sync(17,'abc-defg-hij',False)
        self.sync(18,'xxx-yyyy-zzz',True)
        self.assertEqual(self.bridge.target,MeetTarget('abc-defg-hij',17))
        self.request('/sync',{'meeting':None,'tab':17,'focused':False})   # left the call
        self.sync(18,'xxx-yyyy-zzz',True)
        self.assertEqual(self.bridge.target,MeetTarget('xxx-yyyy-zzz',18))
    def test_rejects_foreign_origins_and_hosts(self):
        for extra in ({'Origin':'https://evil.test'},{'Origin':'chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'},
                      {'Origin':''},{'Host':'evil.test'}):
            with self.assertRaises(urllib.error.HTTPError) as caught: self.raw('/sync',{'meeting':None,'tab':1},extra)
            self.assertEqual(caught.exception.code,403)
        self.assertFalse(self.bridge.extension_connected())
    def test_invalid_target_rejected(self):
        for body in ({'meeting':'https://evil.test','tab':17},{'meeting':'abc-defg-hij','tab':True},{'meeting':'abc-defg-hij','tab':-1}):
            with self.assertRaises(urllib.error.HTTPError): self.request('/sync',body)
    def test_only_linked_tab_receives_leave_and_only_once(self):
        self.sync(17); self.sync(18,'xxx-yyyy-zzz',False)
        self.assertTrue(self.bridge.request_leave(MeetTarget('abc-defg-hij',17)))
        self.assertIsNone(self.sync(18,'xxx-yyyy-zzz',False)['command'])
        command=self.sync(17)['command']
        self.assertEqual(command['action'],'leave')
        self.assertIsNone(self.sync(17)['command'])
        self.request('/result',{'id':command['id'],'closed':True})
        self.assertIn('foi fechada',self.bridge.status)
    def test_cancel_and_expiry_prevent_delivery(self):
        self.sync(); self.bridge.request_leave(); self.bridge.cancel()
        self.assertIsNone(self.sync()['command'])
        self.bridge.request_leave()
        with self.bridge.lock: self.bridge.pending['expires']=0
        self.assertIsNone(self.sync()['command'])
    def test_changed_target_and_silent_browser_block_dispatch(self):
        self.sync()
        self.assertFalse(self.bridge.request_leave(MeetTarget('xxx-yyyy-zzz',18)))
        self.bridge.last_seen=monotonic()-10
        self.assertFalse(self.bridge.connected())
        self.assertFalse(self.bridge.request_leave())
    def test_sound_events_long_poll(self):
        self.sync()
        start=self.request('/events',{'since':-1})
        self.assertEqual(start['events'],[])
        threading.Timer(.2,lambda:self.bridge.emit('play','puff')).start()
        began=monotonic()
        data=self.request('/events',{'since':start['cursor']})
        self.assertLess(monotonic()-began,5)
        self.assertEqual(data['events'],[{'action':'play','name':'puff'}])
    def test_no_sounds_without_a_call_or_when_disabled(self):
        self.bridge.emit('play','puff')
        self.assertEqual(self.bridge.cursor,0)
        self.sync(); self.bridge.call_sounds=False
        self.bridge.emit('play','puff')
        self.assertEqual(self.bridge.cursor,0)
        self.assertFalse(self.sync()['sounds'])
    def test_serves_only_known_sound_names(self):
        self.assertEqual(self.raw('/sound',{'name':'puff'}),b'RIFFfake')
        for name in ('missing','../puff','PUFF',3):
            with self.assertRaises(urllib.error.HTTPError) as caught: self.raw('/sound',{'name':name})
            self.assertEqual(caught.exception.code,404)

    def test_old_extension_is_reported(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.raw('/sync',{'meeting':None,'tab':1},{'Origin':'chrome-extension://picnbjkiajphnbbjpdgabdlhbcokdjei','X-Sumi-Token':'x'})
        self.assertIn('Extensão antiga',self.bridge.status)

if __name__=='__main__': unittest.main()
