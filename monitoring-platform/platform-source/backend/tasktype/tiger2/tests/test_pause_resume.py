"""Pause/continue must actually suspend and resume the process.

The failure this guards against is a no-op that still reports ok:True. If the
command does not reach the process, a paused run keeps burning CPU while the
user is told it stopped -- worse, a SIGTERM-based "pause" would kill the run
and destroy the accumulated state it was supposed to protect. So these assert
on real process state from /proc (T vs R/S), not on the return value.
"""
import os
import signal
import subprocess
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from lib import namd_control  # noqa: E402


def _state(pid):
    """Linux process state letter from /proc, e.g. R/S/T."""
    try:
        with open(f"/proc/{pid}/stat") as fh:
            fields = fh.read().rsplit(")", 1)[1].split()
        return fields[0]
    except (OSError, IndexError):
        return None


def _wait_for_state(pid, wanted, tries=100):
    for _ in range(tries):
        if _state(pid) in wanted:
            return True
        time.sleep(0.02)
    return False


class _Ssh:
    """Applies the recorded signal commands to a local PID.

    Stands in for SSHClient so the signal path runs without a remote host.
    """

    def __init__(self, pid):
        self.pid = pid
        self.calls = []

    def exec(self, cmd, timeout=None):
        self.calls.append(cmd)
        if cmd.startswith("pgrep -fc"):
            # Pretend the pattern matches, so the tests exercise the count path
            # as well as the signal.
            return ("1\n", "", 0)
        if "-STOP" in cmd:
            os.kill(self.pid, signal.SIGSTOP)
            return ("DONE", "", 0)
        if "-CONT" in cmd:
            os.kill(self.pid, signal.SIGCONT)
            return ("DONE", "", 0)
        return ("", "", 0)


class _Cfg:
    pgrep_pattern = staticmethod(lambda: "am3_test_marker")


class TestNamdPause(unittest.TestCase):
    def setUp(self):
        # A child that burns CPU, so it is genuinely R while running.
        self.proc = subprocess.Popen(
            [sys.executable, "-c", "x=0\nwhile True: x+=1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.ssh = _Ssh(self.proc.pid)
        _wait_for_state(self.proc.pid, {"R", "S"})

    def tearDown(self):
        os.kill(self.proc.pid, signal.SIGCONT)
        self.proc.kill()
        self.proc.wait()

    def test_pause_suspends_and_continue_resumes(self):
        namd_control.pause(self.ssh, _Cfg())
        self.assertTrue(_wait_for_state(self.proc.pid, {"T"}),
                        "pause must leave the process stopped")

        namd_control.resume(self.ssh, _Cfg())
        self.assertTrue(_wait_for_state(self.proc.pid, {"R", "S"}),
                        "continue must resume the process")

    def test_pause_is_not_a_kill(self):
        namd_control.pause(self.ssh, _Cfg())
        time.sleep(0.2)
        self.assertIsNotNone(_state(self.proc.pid), "process must still exist")
        self.assertIsNone(self.proc.poll(), "pause must not kill the process")

    def test_uses_stop_and_cont_not_term(self):
        namd_control.pause(self.ssh, _Cfg())
        namd_control.resume(self.ssh, _Cfg())
        self.assertTrue(any("pkill -STOP" in c for c in self.ssh.calls))
        self.assertTrue(any("pkill -CONT" in c for c in self.ssh.calls))
        # `stop` is SIGTERM and is a different operation entirely.
        self.assertFalse(any("pkill -TERM" in c for c in self.ssh.calls))
        self.assertFalse(any("pkill -KILL" in c for c in self.ssh.calls))


class TestPauseReportsWhenNothingMatched(unittest.TestCase):
    """A pause that hit no process must not claim success.

    pkill exits 1 when nothing matched, but the caller only checks for a thrown
    error. So without an explicit count, pausing a task whose simulation is not
    running returns ok:True -- the UI says the run is suspended while it was
    never touched.
    """

    class _NoMatchSsh:
        def __init__(self):
            self.calls = []

        def exec(self, cmd, timeout=None):
            self.calls.append(cmd)
            return ("0\n", "", 0)

    def test_pause_is_not_ok_when_no_process_matched(self):
        result = namd_control.pause(self._NoMatchSsh(), _Cfg())
        self.assertFalse(result["ok"])
        self.assertEqual(result["matchedProcesses"], 0)
        self.assertIn("did nothing", result["note"])

    def test_continue_is_not_ok_when_no_process_matched(self):
        result = namd_control.resume(self._NoMatchSsh(), _Cfg())
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()