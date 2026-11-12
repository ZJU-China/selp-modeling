"""CG pause/continue must prefer SLURM over signalling the process.

CG jobs run under SLURM on the ZJU cluster, so `pkill -STOP` would either miss
the job (it is on a compute node) or freeze the simulation while SLURM still
reports RUNNING. These tests pin the scontrol path and the signal fallback.
"""
import os
import signal
import subprocess
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from lib import gmx  # noqa: E402


def _state(pid):
    try:
        with open(f"/proc/{pid}/stat") as fh:
            fields = fh.read().rsplit(")", 1)[1].split()
        return fields[0]
    except (OSError, IndexError):
        return None


class _Cfg:
    pgrep_pattern = staticmethod(lambda: "am3_test_marker")
    slurm_user = staticmethod(lambda: "tester")
    slurm_job_prefix = staticmethod(lambda: "marker")


class _Ssh:
    """Records commands; applies the signal ones to local PIDs.

    Stands in for SSHClient so the control path is exercised without a cluster.
    """

    def __init__(self, pids=(), squeue_output=""):
        self.pids = list(pids)
        self.squeue_output = squeue_output
        self.calls = []

    def exec(self, cmd, timeout=None):
        self.calls.append(cmd)
        if cmd.startswith("squeue"):
            return (self.squeue_output, "", 0)
        if cmd.startswith("pgrep -fc"):
            return ("1\n" if self.pids else "0\n", "", 0)
        if "-STOP" in cmd:
            for pid in self.pids:
                os.kill(pid, signal.SIGSTOP)
            return ("DONE", "", 0)
        if "-CONT" in cmd:
            for pid in self.pids:
                os.kill(pid, signal.SIGCONT)
            return ("DONE", "", 0)
        return ("", "", 0)


def _running_child():
    return subprocess.Popen(
        [sys.executable, "-c", "x=0\nwhile True: x+=1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _wait_for_state(pid, wanted, tries=100):
    for _ in range(tries):
        if _state(pid) in wanted:
            return True
        time.sleep(0.02)
    return False


class TestGromacsPausePrefersSlurm(unittest.TestCase):
    def test_uses_scontrol_when_jobs_exist(self):
        ssh = _Ssh(squeue_output="4242\tmarker_job\tRUNNING\n")
        result = gmx.pause(ssh, _Cfg())
        self.assertEqual(result["method"], "slurm")
        self.assertEqual(result["jobIds"], ["4242"])
        self.assertTrue(
            any(c.startswith("scontrol suspend 4242") for c in ssh.calls),
            f"expected scontrol suspend, got {ssh.calls}",
        )
        self.assertFalse(any("-STOP" in c for c in ssh.calls),
                         "must not pkill when a SLURM job exists")

    def test_continue_uses_scontrol_resume(self):
        ssh = _Ssh(squeue_output="4242\tmarker_job\tSUSPENDED\n")
        result = gmx.resume(ssh, _Cfg())
        self.assertTrue(any(c.startswith("scontrol resume 4242") for c in ssh.calls))
        self.assertEqual(result["action"], "resumed")

    def test_pending_job_is_not_an_error(self):
        # scontrol refuses to suspend a PENDING job. Report not-ok rather than
        # pretending, but do not treat it as a failure of the command itself.
        ssh = _Ssh(squeue_output="4243\tmarker_job\tPENDING\n")
        result = gmx.pause(ssh, _Cfg())
        self.assertEqual(result["jobIds"], [])
        self.assertFalse(result["ok"])
        self.assertFalse(any("scontrol" in c for c in ssh.calls),
                         "should not suspend a job that has not started")

    def test_falls_back_to_signal_when_no_slurm_job(self):
        proc = _running_child()
        try:
            ssh = _Ssh([proc.pid])
            result = gmx.pause(ssh, _Cfg())
            self.assertEqual(result["method"], "signal")
            self.assertTrue(_wait_for_state(proc.pid, {"T"}), "process must be stopped")
            self.assertEqual(proc.poll(), None, "pause must not kill the process")
        finally:
            os.kill(proc.pid, signal.SIGCONT)
            proc.kill()
            proc.wait()

    def test_is_paused_only_when_all_jobs_suspended(self):
        cfg = _Cfg()
        # slurm_jobs() filters by the configured job prefix, so the names here
        # must contain "marker" to be considered at all.
        self.assertTrue(gmx.is_paused(_Ssh(squeue_output="1\tmarker_a\tSUSPENDED\n"), cfg))
        self.assertFalse(gmx.is_paused(_Ssh(squeue_output="1\tmarker_a\tRUNNING\n"), cfg))
        self.assertFalse(gmx.is_paused(_Ssh(squeue_output=""), cfg))
        # An unrelated job must not be counted as this task's.
        self.assertFalse(gmx.is_paused(_Ssh(squeue_output="1\tother\tSUSPENDED\n"), cfg))


if __name__ == "__main__":
    unittest.main()