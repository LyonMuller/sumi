import json
import unittest
import urllib.request
import urllib.error
from time import monotonic
from unittest.mock import patch
from sumi.meet import LeaveCountdown,MeetBridge,MeetTarget

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
        self.bridge=MeetBridge(port=0,token='test-token-'+'x'*32)
        self.addCleanup(self.bridge.close)
    def request(self,path,body=None,token=None):
        request=urllib.request.Request(f'http://127.0.0.1:{self.bridge.port}'+path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'X-Sumi-Token':token or self.bridge.token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=3) as response: return json.load(response)
        except urllib.error.HTTPError as error:
            error.close()
            raise
    def pair(self):
        self.request('/pair',{'meeting':'abc-defg-hij','tab':17})
    def test_rejects_unauthorized_requests(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/command?meeting=abc-defg-hij&tab=17',token='wrong')
        self.assertEqual(caught.exception.code,403)
    def test_invalid_target_rejected(self):
        for body in ({'meeting':'https://evil.test','tab':17},{'meeting':'abc-defg-hij','tab':True}):
            with self.assertRaises(urllib.error.HTTPError): self.request('/pair',body)
    def test_web_origins_and_non_loopback_host_are_rejected_even_with_token(self):
        for extra in ({'Origin':'https://evil.test'}, {'Host':'evil.test'}, {'Origin':'chrome-extension://invalid/extra'}):
            headers={'X-Sumi-Token':self.bridge.token,**extra}
            request=urllib.request.Request(f'http://127.0.0.1:{self.bridge.port}/command?meeting=abc-defg-hij&tab=17',headers=headers)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request,timeout=3)
            caught.exception.close()
            self.assertEqual(caught.exception.code,403)
    def test_only_bound_tab_can_consume_command_and_only_once(self):
        self.pair(); self.assertTrue(self.bridge.request_leave(MeetTarget('abc-defg-hij',17)))
        self.assertIsNone(self.request('/command?meeting=abc-defg-hij&tab=18')['command'])
        command=self.request('/command?meeting=abc-defg-hij&tab=17')['command']
        self.assertEqual(command['action'],'leave')
        self.assertIsNone(self.request('/command?meeting=abc-defg-hij&tab=17')['command'])
        self.request('/result',{'id':command['id'],'closed':True})
        self.assertIn('foi fechada',self.bridge.status)
    def test_cancel_and_expiry_prevent_delivery(self):
        self.pair(); self.bridge.request_leave(); self.bridge.cancel()
        self.assertIsNone(self.request('/command?meeting=abc-defg-hij&tab=17')['command'])
        self.bridge.request_leave()
        with self.bridge.lock: self.bridge.pending['expires']=0
        self.assertIsNone(self.request('/command?meeting=abc-defg-hij&tab=17')['command'])
    def test_changed_binding_and_disconnected_browser_block_dispatch(self):
        self.pair()
        self.assertFalse(self.bridge.request_leave(MeetTarget('xxx-yyyy-zzz',18)))
        self.bridge.last_seen=monotonic()-10
        self.assertFalse(self.bridge.connected())
        self.assertFalse(self.bridge.request_leave())

if __name__=='__main__': unittest.main()
