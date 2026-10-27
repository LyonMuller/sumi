import tempfile
import threading
import time
import unittest
from pathlib import Path

from sumi.effect_catalog import EFFECTS
from sumi.sounds import SoundBank, SoundPlayer
from tools.package_release import ROOT, release_files

EXTRA = ('kamehameha-charge', 'kamehameha-charge-loop', 'kamehameha-fire', 'restore', 'clones-wave')


class FakeProc:
    def __init__(self, args, block):
        self.args = args
        self.terminated = threading.Event()
        self.block = block

    def poll(self):
        return 0 if self.terminated.is_set() or not self.block else None

    def wait(self):
        if self.block:
            self.terminated.wait(2)
        else:
            time.sleep(0.01)

    def terminate(self):
        self.terminated.set()

    kill = terminate


class FakeRunner:
    def __init__(self, block=True):
        self.block = block
        self.calls = []

    def __call__(self, args):
        proc = FakeProc(args, self.block)
        self.calls.append(proc)
        return proc


def wait_for(cond, timeout=1.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.005)
    return cond()


class SoundTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.over = Path(tmp.name) / 'sons'
        self.bund = Path(tmp.name) / 'bundled'
        self.over.mkdir()
        self.bund.mkdir()
        (self.bund / 'goku.wav').write_bytes(b'x')
        self.bank = SoundBank(self.over, self.bund, platform='darwin')

    def player(self, runner=None, **kw):
        runner = runner or FakeRunner()
        p = SoundPlayer(self.bank, runner=runner, platform='darwin', **kw)
        self.addCleanup(p.stop_all)
        return p, runner

    def test_override_beats_bundled(self):
        self.assertEqual(self.bank.path('goku'), self.bund / 'goku.wav')
        (self.over / 'goku.mp3').write_bytes(b'x')
        self.assertEqual(self.bank.path('goku'), self.over / 'goku.mp3')
        (self.over / 'goku.wav').write_bytes(b'x')
        self.assertEqual(self.bank.path('goku'), self.over / 'goku.wav')
        self.assertIn('goku', self.bank.names())

    def test_non_wav_override_only_on_macos(self):
        (self.over / 'goku.mp3').write_bytes(b'x')
        win = SoundBank(self.over, self.bund, platform='win32')
        self.assertEqual(win.path('goku'), self.bund / 'goku.wav')

    def test_unknown_or_bad_name_is_noop(self):
        self.assertIsNone(self.bank.path('nada'))
        self.assertIsNone(self.bank.path('../goku'))
        player, runner = self.player()
        player.play('nada')
        player.loop('nada')
        player.stop('nada')
        self.assertEqual(runner.calls, [])

    def test_play_uses_afplay_with_volume(self):
        player, runner = self.player(volume=0.5)
        player.play('goku')
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(runner.calls[0].args, ['afplay', '-v', '0.50', str(self.bund / 'goku.wav')])

    def test_loop_is_idempotent_and_stop_kills(self):
        player, runner = self.player()
        player.loop('goku')
        player.loop('goku')
        self.assertTrue(wait_for(lambda: len(runner.calls) == 1))
        time.sleep(0.05)
        self.assertEqual(len(runner.calls), 1)
        self.assertTrue(player.is_looping('goku'))
        player.stop('goku')
        self.assertTrue(runner.calls[0].terminated.is_set())
        self.assertFalse(player.is_looping('goku'))

    def test_loop_restarts_when_sound_ends(self):
        player, runner = self.player(FakeRunner(block=False))
        player.loop('goku')
        self.assertTrue(wait_for(lambda: len(runner.calls) >= 3))
        player.stop_all()
        count = len(runner.calls)
        time.sleep(0.1)
        self.assertLessEqual(len(runner.calls), count + 1)

    def test_loop_plays_intro_once_then_repeats_tail(self):
        (self.bund / 'goku-loop.wav').write_bytes(b'x')
        player, runner = self.player(FakeRunner(block=False))
        player.loop('goku')
        self.assertTrue(wait_for(lambda: len(runner.calls) >= 3))
        player.stop_all()
        files = [c.args[-1] for c in runner.calls]
        self.assertEqual(files[0], str(self.bund / 'goku.wav'))
        self.assertTrue(all(f == str(self.bund / 'goku-loop.wav') for f in files[1:]))

    def test_stop_all_kills_everything(self):
        player, runner = self.player()
        player.play('goku')
        player.loop('goku')
        wait_for(lambda: len(runner.calls) == 2)
        player.stop_all()
        self.assertTrue(all(p.terminated.is_set() for p in runner.calls))

    def test_disabled_does_nothing(self):
        player, runner = self.player(enabled=False)
        player.play('goku')
        player.loop('goku')
        time.sleep(0.03)
        self.assertEqual(runner.calls, [])
        player.enabled = True
        player.play('goku')
        self.assertEqual(len(runner.calls), 1)

    def test_runner_errors_never_propagate(self):
        def boom(args):
            raise FileNotFoundError('afplay')
        player, _ = self.player(boom)
        player.play('goku')
        player.loop('goku')
        player.stop('goku')
        player.stop_all()

    def test_other_platform_is_noop(self):
        runner = FakeRunner()
        player = SoundPlayer(self.bank, runner=runner, platform='linux')
        player.play('goku')
        player.loop('goku')
        self.assertEqual(runner.calls, [])

    def test_every_effect_has_a_bundled_sound(self):
        bank = SoundBank(self.over, ROOT / 'assets' / 'sounds')
        included = set(release_files())
        # Charged effects (`action`) play `<name>-charge` and `<name>-fire` instead of their own name.
        for name in (*(k for k, e in EFFECTS.items() if not getattr(e, 'action', False)), *EXTRA):
            path = bank.path(name)
            self.assertIsNotNone(path, name)
            self.assertIn(path, included, name)
            self.assertLess(path.stat().st_size, 250_000, name)


    def test_spirit_bomb_borrows_the_wave_sounds_until_it_has_its_own(self):
        bank = SoundBank(self.over, ROOT / 'assets' / 'sounds')
        self.assertEqual(bank.path('genkidama-fire'), bank.path('kamehameha-fire'))
        self.assertEqual(bank.path('genkidama-charge'), bank.path('kamehameha-charge'))
        (self.over / 'genkidama-fire.wav').write_bytes(b'x')
        self.assertEqual(bank.path('genkidama-fire'), self.over / 'genkidama-fire.wav')


if __name__ == '__main__':
    unittest.main()
