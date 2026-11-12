"""Starting a CG run must actually launch gmx, or explain why it cannot.

CG start/restart previously returned a fixed "launch with sbatch on the cluster"
message for both commands, so the step could never be started from the app. These
tests pin the replacement: the real mdrun is launched and verified, a placeholder
remoteDir is refused before any command runs, and a configured-but-missing gmx is
an error rather than a silent fallback to a different binary.

A recording fake SSH stands in for the server, so nothing here needs a cluster.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# Three levels up: `lib.launch` imports `_shared.tools` (the shared resolver),
# which lives at backend/_shared rather than tasktype/_shared.
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from lib import launch, task_config  # noqa: E402

# The launch path waits for a process to survive two checks. The wait is real,
# and covered separately; here it is removed so the suite does not spend a
# minute sleeping.
launch.SETTLE_DELAYS = (0, 0)


class FakeSsh:
    """Records commands and answers existence probes from a scripted table."""

    def __init__(self, files=(), dirs=(), gmx_present=True, sbatch=None, mdrun_alive=True,
                 mdrun_completed=False):
        self.files = set(files)
        self.dirs = set(dirs)
        self.gmx_present = gmx_present
        self.sbatch = sbatch
        self.mdrun_alive = mdrun_alive
        self.mdrun_completed = mdrun_completed
        self.calls = []

    def exec(self, cmd, timeout=None):
        self.calls.append(cmd)
        if "command -v sbatch" in cmd:
            return ((self.sbatch + "\n") if self.sbatch else "", "", 0 if self.sbatch else 1)
        if self.sbatch and "/usr/bin/sbatch" in cmd and "command -v" not in cmd:
            return ("Submitted batch job 4242\n", "", 0)
        if "command -v gmx" in cmd or "-x" in cmd and "gmx" in cmd:
            return ("YES\n" if self.gmx_present else "NO\n", "", 0)
        if cmd.startswith("ls -d"):
            import shlex
            pat = shlex.split(cmd[len("ls -d "):].split(" 2>")[0].strip())[0]
            hits = [d for d in self.dirs if d == pat]
            return ("\n".join(hits) + "\n" if hits else "", "", 0)
        if cmd.startswith("test -d"):
            import shlex
            p = shlex.split(cmd[len("test -d "):].split(" ")[0])[0]
            return ("YES\n" if p in self.dirs else "NO\n", "", 0)
        if "test -f" in cmd and "Finished mdrun" in cmd:
            return (("1\n" if self.mdrun_completed else "0\n"), "", 0)
        if cmd.startswith("test -f"):
            import shlex
            p = shlex.split(cmd[len("test -f "):].split(" ")[0])[0]
            return ("YES\n" if p in self.files else "NO\n", "", 0)
        if "ps aux | grep" in cmd:
            # A real `ps aux` line: gmx_processes needs >= 11 fields and reads
            # the PID from the second one.
            line = ("igem 4242 0.5 12.0 51200 90000 ? Ssl 10:22 0:01 "
                    "/usr/bin/gmx mdrun -s run/relax.tpr")
            return ((line + "\n") if self.mdrun_alive else "", "", 0)
        if "pgrep -fc" in cmd:
            return (("1\n" if self.mdrun_alive else "0\n"), "", 0)
        if cmd.startswith("squeue"):
            return ("", "", 0)
        if "test -f" in cmd and "Finished mdrun" in cmd:
            return (("1\n" if self.mdrun_completed else "0\n"), "", 0)
        if "tail -n" in cmd:
            return ("", "", 0)
        if "Finished mdrun" in cmd:
            return (("1\n" if self.mdrun_completed else "0\n"), "", 0)
        return ("", "", 0)


def make_cfg(**over):
    raw = {
        "remoteDir": "/home/selp/igem-2026/MD/CG_test",
        "logPrefix": "relax",
        "defaults": {"numReplicas": 1, "stepsPerCycle": 100, "totalCycles": 1},
        "gromacs": {
            "mdpName": "relax_out.mdp",
            "sampleGlobs": ["run"],
            "runSubdir": "run",
            "initGro": "init.gro",
            "gmxBin": "/usr/bin/gmx",
        },
    }
    raw.update(over)
    return task_config.load(raw)


SAMPLE = "/home/selp/igem-2026/MD/CG_test/run"


class TestShellQuoting(unittest.TestCase):
    def test_plain_paths_are_not_quoted(self):
        # Keeps the generated command readable in logs for the common case.
        self.assertEqual(launch.shell_quote("/home/selp/run"), "/home/selp/run")

    def test_metacharacters_are_quoted(self):
        # remoteDir comes from a user-editable field and is interpolated into a
        # remote shell command.
        self.assertEqual(launch.shell_quote("/tmp; rm -rf /"), "'/tmp; rm -rf /'")
        self.assertEqual(launch.shell_quote("a b"), "'a b'")

    def test_single_quote_is_escaped(self):
        self.assertEqual(launch.shell_quote("it's"), "'it'\\''s'")


class TestPreflight(unittest.TestCase):
    def test_placeholder_remote_dir_is_refused_before_launching(self):
        # A task scaffolded from a template has a FILL-IN remoteDir. Starting it
        # would cd into a literal "FILL-IN: ..." directory.
        cfg = make_cfg(remoteDir="FILL-IN: remote working directory")
        ssh = FakeSsh()
        r = launch.start(ssh, cfg)
        self.assertFalse(r["ok"])
        self.assertIn("placeholder", r["error"].lower())
        self.assertEqual(ssh.calls, [], "nothing should be run remotely")

    def test_missing_remote_dir_is_refused(self):
        cfg = make_cfg(remoteDir="")
        r = launch.start(FakeSsh(), cfg)
        self.assertFalse(r["ok"])
        self.assertIn("remoteDir", r["error"])

    def test_configured_gmx_that_is_absent_is_an_error_not_a_fallback(self):
        # Falling back to a different binary than the task configured would make
        # the run irreproducible while appearing to succeed.
        cfg = make_cfg()
        cfg.extra["gromacs"]["gmxBin"] = "/opt/nope/gmx"
        ssh = FakeSsh(gmx_present=False)
        r = launch.start(ssh, cfg)
        self.assertFalse(r["ok"])
        self.assertIn("/opt/nope/gmx", r["error"])

    def test_missing_sample_dir_reports_where_it_looked(self):
        cfg = make_cfg()
        r = launch.start(FakeSsh(dirs=[]), cfg)
        self.assertFalse(r["ok"])
        self.assertIn("CG_test", r["error"])


class TestLaunch(unittest.TestCase):
    def _staged_ssh(self, **kw):
        return FakeSsh(
            files=[f"{SAMPLE}/relax.tpr", f"{SAMPLE}/relax.cpt"],
            dirs=[SAMPLE],
            **kw,
        )

    def test_start_runs_mdrun_with_the_configured_tpr(self):
        cfg = make_cfg()
        ssh = self._staged_ssh()
        r = launch.start(ssh, cfg)
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["running"])
        joined = " ".join(ssh.calls)
        self.assertIn("mdrun", joined)
        self.assertIn(f"{SAMPLE}/relax.tpr", joined)

    def test_start_uses_setsid_so_the_run_outlives_the_ssh_session(self):
        # Without detachment mdrun is killed when exec() returns.
        cfg = make_cfg()
        ssh = self._staged_ssh()
        launch.start(ssh, cfg)
        self.assertTrue(any("setsid" in c for c in ssh.calls))

    def test_hwloc_gl_probe_is_disabled(self):
        # hwloc's GL plugin calls XOpenDisplay() during topology detection. On
        # the iGEM server the X socket exists but no longer accepts an
        # authorized client, so that call blocks forever and mdrun never starts
        # (it prints "Authorization required..." and produces no log). Verified
        # end-to-end against that host: with HWLOC_COMPONENTS=-gl a 2000-step
        # run finished at 894 ns/day; without it the launch timed out.
        cfg = make_cfg()
        ssh = self._staged_ssh()
        launch.start(ssh, cfg)
        joined = " ".join(ssh.calls)
        self.assertIn("HWLOC_COMPONENTS=-gl", joined)
        # grompp is invoked through the same wrapper, so staging a tpr is safe.
        ssh2 = FakeSsh(files=[f"{SAMPLE}/cg_input.mdp", f"{SAMPLE}/init.gro"],
                       dirs=[SAMPLE])
        launch.start(ssh2, cfg)
        self.assertIn("HWLOC_COMPONENTS=-gl", " ".join(ssh2.calls))

    def test_restart_continues_from_the_checkpoint(self):
        # Starting from the tpr again would discard the trajectory already done.
        cfg = make_cfg()
        ssh = self._staged_ssh()
        r = launch.start(ssh, cfg, resume=True)
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["resumed"])
        joined = " ".join(ssh.calls)
        self.assertIn("-cpi", joined)
        self.assertIn("-append", joined)

    def test_smoke_steps_override_the_run_length(self):
        cfg = make_cfg()
        cfg.extra["gromacs"]["smokeSteps"] = 2000
        ssh = self._staged_ssh()
        launch.start(ssh, cfg)
        self.assertTrue(any("-nsteps 2000" in c for c in ssh.calls))

    def test_no_sbatch_on_the_host_is_reported_not_assumed(self):
        # The old message told users to run sbatch even on a host without it.
        cfg = make_cfg()
        r = launch.start(self._staged_ssh(), cfg)
        self.assertIn("no SLURM", r["scheduler"])

    def test_sbatch_available_is_reported(self):
        cfg = make_cfg()
        r = launch.start(self._staged_ssh(sbatch="/usr/bin/sbatch"), cfg)
        self.assertIn("sbatch", r["scheduler"])
        self.assertEqual(r["jobId"], "4242")

    def test_sbatch_submission_writes_a_batch_script_with_hwloc_and_mdrun(self):
        # The batch script is the only trace an sbatch job leaves before its
        # first step, so what it runs must be written down and readable.
        cfg = make_cfg()
        ssh = self._staged_ssh(sbatch="/usr/bin/sbatch")
        launch.start(ssh, cfg)
        writes = [c for c in ssh.calls if "cat >" in c]
        self.assertEqual(len(writes), 1, "exactly one batch script is written")
        body = writes[0]
        self.assertIn("SBATCH_SCRIPT_EOF_", body)
        self.assertIn("HWLOC_COMPONENTS=-gl", body)
        self.assertIn("/usr/bin/gmx mdrun", body)
        self.assertIn("#SBATCH --job-name=relax", body)
        # The script is chmod +x before submission so it survives reuse.
        self.assertIn("chmod +x", body)
        submitted = [c for c in ssh.calls if "/usr/bin/sbatch" in c and "command -v" not in c]
        self.assertEqual(len(submitted), 1)

    def test_a_run_that_dies_immediately_is_a_failure_with_the_log(self):
        # GROMACS exits straight away on a bad tpr; reporting success here hides
        # the reason behind an empty log.
        cfg = make_cfg()
        ssh = self._staged_ssh(mdrun_alive=False)
        r = launch.start(ssh, cfg)
        self.assertFalse(r["ok"])
        self.assertFalse(r["running"])
        self.assertIn("stdoutLog", r)

    def test_grompp_runs_when_no_tpr_is_staged(self):
        # A start must not depend on an unrecorded manual staging step.
        cfg = make_cfg()
        ssh = FakeSsh(
            files=[f"{SAMPLE}/cg_input.mdp", f"{SAMPLE}/init.gro"],
            dirs=[SAMPLE],
        )
        r = launch.start(ssh, cfg)
        joined = " ".join(ssh.calls)
        self.assertIn("grompp", joined)
        self.assertIsNotNone(r.get("command"))

    def test_missing_mdp_is_reported_by_name(self):
        cfg = make_cfg()
        ssh = FakeSsh(files=[f"{SAMPLE}/init.gro"], dirs=[SAMPLE])
        r = launch.start(ssh, cfg)
        self.assertFalse(r["ok"])
        self.assertIn("mdp", r["error"])

    def test_a_smoke_run_can_complete_inside_the_settle_window(self):
        # A short smoke run finishes in under a second of wall time on a fast
        # host, so by the first survival check mdrun has already exited. That is
        # success, not the "exited during startup" failure of a bad tpr.
        cfg = make_cfg()
        ssh = self._staged_ssh(mdrun_alive=False, mdrun_completed=True)
        r = launch.start(ssh, cfg)
        self.assertTrue(r["ok"], r)
        self.assertTrue(r.get("completed"))
        self.assertFalse(r["running"])

    def test_exit_without_a_completion_record_is_still_presented_as_a_failure(self):
        # The completed log is the only thing distinguishing a finished smoke
        # run from a bad tpr. Without it, an immediate exit stays an error.
        cfg = make_cfg()
        ssh = self._staged_ssh(mdrun_alive=False, mdrun_completed=False)
        r = launch.start(ssh, cfg)
        self.assertFalse(r["ok"])
        self.assertIn("stdoutLog", r)


class TestMdrunCommand(unittest.TestCase):
    def test_command_is_argv_not_a_shell_string(self):
        cfg = make_cfg()
        argv = launch.build_mdrun_command(["gmx"], cfg, SAMPLE, f"{SAMPLE}/relax.tpr")
        self.assertEqual(argv[:3], ["gmx", "mdrun", "-s"])

    def test_deffnm_follows_the_configured_prefix(self):
        cfg = make_cfg(logPrefix="job7")
        argv = launch.build_mdrun_command(["gmx"], cfg, SAMPLE, f"{SAMPLE}/relax.tpr")
        self.assertIn(os.path.join(SAMPLE, "job7"), argv)


class TestConfigAccessors(unittest.TestCase):
    def test_launch_settings_default_when_absent(self):
        cfg = task_config.load({"remoteDir": "/tmp/x", "logPrefix": "relax"})
        self.assertEqual(cfg.ntomp(), 0)
        self.assertIsNone(cfg.smoke_steps())
        self.assertEqual(cfg.gmx_bin(), None)
        self.assertEqual(cfg.init_gro(), "init.gro")

    def test_deffnm_falls_back_to_the_log_prefix(self):
        cfg = task_config.load({"remoteDir": "/tmp/x", "logPrefix": "runA"})
        self.assertEqual(cfg.defffnm(), "runA")


if __name__ == "__main__":
    unittest.main()