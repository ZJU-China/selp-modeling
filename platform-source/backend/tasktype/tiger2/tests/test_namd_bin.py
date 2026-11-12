"""NAMD build resolution: which build a launch would actually use.

The task config, the shell convention and the deployed layouts disagree about
how a NAMD build is named, and the previously hardcoded default
(``~/software/NAMD_3.0.2_Linux-x86_64-netlrts-smp``) does not exist on the iGEM
server -- the builds live under ``~/igem-2026/MD/``. A launch against a
directory that is not there dies inside charmrun, so resolution is what keeps
the "configured" and "used" paths from drifting apart.
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TT = os.path.dirname(HERE)
sys.path.insert(0, TT)
sys.path.insert(0, os.path.join(TT, "..", ".."))

from lib.namd_control import (  # noqa: E402
    DEFAULT_NAMD_BIN_GLOBS,
    probe_namd_bin,
    resolve_namd_bin,
    start,
    _expand_home,
)
from _shared.tools import describe_namd, namd_build_dir  # noqa: E402


class FakeSsh:
    """Records commands and answers with canned stdout.

    ``present`` decides whether a probed build directory is treated as a real
    install, so resolution can be tested without a server.
    """

    def __init__(self, present=(), conf="", launcher=""):
        # The probe expands "~" to $HOME before it ever reaches the shell, so a
        # candidate is "present" when its expanded form appears in the command.
        self.present = {p if p.startswith(("/", "$")) else _expand_home(p) for p in present}
        self.conf = conf
        self.launcher = launcher
        self.commands = []
        self._launched = False

    def exec(self, cmd, timeout=30):
        self.commands.append(cmd)
        # The build probe is the only command that tests for `[ -x `; the launch
        # itself also mentions charmrun, so that marker is what tells them apart.
        # A real probe echoes the resolved path, so the fake does too.
        if "[ -x " in cmd:
            if not any(p in cmd for p in self.present):
                return "__NAMD_MISSING__", "", 0
            import re
            echo = re.findall(r'then echo "([^"]+)"', cmd)
            return (echo[0] if echo else ""), "", 0
        if "pgrep" in cmd:
            return ("YES\n" if self._launched else "NO\n"), "", 0
        if "find -L" in cmd:
            return ("FRESH\n" if self._launched else "STALE\n"), "", 0
        if ".conf" in cmd and "ls" in cmd:
            return self.conf, "", 0
        if "tail -n" in cmd:
            return self.launcher, "", 0
        return "", "", 0


class FakeCfg:
    def __init__(self, process=None, num_replicas=4):
        self.extra = {"process": process or {}}
        self.log_prefix = "job0"
        self.num_replicas = num_replicas

    def temp_dir(self):
        return "/remote/temp"

    def namd_bin(self):
        return (self.extra.get("process") or {}).get("namdBin")

    def prepare_dirs(self, ssh):
        return None

    def env_setup(self):
        return ""

    def pgrep_pattern(self):
        return "namd3 .*job0"

    def freshness_minutes(self):
        return 5

    def log_paths(self, replica):
        return [f"/remote/temp/logs/{replica}/job0.{replica}.log"]


class TestExpandHome(unittest.TestCase):
    def test_tilde_becomes_remote_home(self):
        # "~" must expand remotely: the launch runs on the compute server, so
        # expanding it against the backend host's HOME would point somewhere
        # that does not have NAMD.
        self.assertEqual(_expand_home("~/software/NAMD"), "$HOME/software/NAMD")

    def test_absolute_path_untouched(self):
        self.assertEqual(_expand_home("/opt/NAMD"), "/opt/NAMD")


class TestProbe(unittest.TestCase):
    def test_missing_build_reported(self):
        ssh = FakeSsh(present=())
        path, ok, detail = probe_namd_bin(ssh, "/nope/NAMD")
        self.assertFalse(ok)
        self.assertIn("no executable charmrun+namd3", detail)

    def test_present_build_reported(self):
        ssh = FakeSsh(present=("/srv/NAMD",))
        path, ok, _ = probe_namd_bin(ssh, "/srv/NAMD")
        self.assertTrue(ok)
        self.assertEqual(path, "/srv/NAMD")


class TestResolve(unittest.TestCase):
    def test_configured_path_wins(self):
        cfg = FakeCfg({"namdBin": "/srv/NAMD"})
        ssh = FakeSsh(present=("/srv/NAMD",))
        path, info = resolve_namd_bin(ssh, cfg)
        self.assertEqual(path, "/srv/NAMD")
        self.assertEqual(info["source"], "configured")

    def test_explicit_cli_wins_over_task_config(self):
        cfg = FakeCfg({"namdBin": "/srv/NAMD"})
        ssh = FakeSsh(present=("/cli/NAMD", "/srv/NAMD"))
        path, info = resolve_namd_bin(ssh, cfg, namd_bin="/cli/NAMD")
        self.assertEqual(path, "/cli/NAMD")

    def test_discovers_when_nothing_configured(self):
        # The point of the fallback list: a task that never set namdBin still
        # finds the build that is actually installed.
        installed = DEFAULT_NAMD_BIN_GLOBS[2]
        ssh = FakeSsh(present=(installed,))
        path, info = resolve_namd_bin(ssh, FakeCfg())
        self.assertEqual(path, _expand_home(installed))
        self.assertEqual(info["source"], "discovered")

    def test_no_build_available_is_an_error(self):
        ssh = FakeSsh(present=())
        path, info = resolve_namd_bin(ssh, FakeCfg())
        self.assertIsNone(path)
        self.assertIn("error", info)
        self.assertTrue(info["tried"])


class TestStartUsesResolvedPath(unittest.TestCase):
    def test_launch_command_uses_resolved_build(self):
        ssh = FakeSsh(present=("/srv/NAMD",), conf="/remote/temp/job0.conf")
        cfg = FakeCfg({"namdBin": "/srv/NAMD"})
        ssh._launched = True
        result = start(ssh, cfg)
        self.assertTrue(result["ok"])
        self.assertTrue(result["running"])
        launch = [c for c in ssh.commands if "charmrun" in c][0]
        self.assertIn("/srv/NAMD/charmrun", launch)
        self.assertIn("/srv/NAMD/namd3", launch)
        self.assertEqual(result["namd"]["resolved"], "/srv/NAMD")

    def test_start_refuses_when_build_missing(self):
        # Previously this launched anyway and died inside charmrun, so the
        # failure surfaced as an empty log rather than a launch error.
        ssh = FakeSsh(present=(), conf="/remote/temp/job0.conf")
        result = start(ssh, FakeCfg({"namdBin": "/gone/NAMD"}))
        self.assertFalse(result["ok"])
        self.assertIn("NAMD", result["error"])

    def test_start_reports_failure_when_namd_exits(self):
        ssh = FakeSsh(
            present=("/srv/NAMD",),
            conf="/remote/temp/job0.conf",
            launcher="FATAL ERROR: restart with wrong number of replicas",
        )
        ssh._launched = False
        result = start(ssh, FakeCfg({"namdBin": "/srv/NAMD"}))
        self.assertFalse(result["ok"], "a job that never survived must not report ok")
        self.assertFalse(result["running"])
        self.assertIn("wrong number of replicas", result["detail"])


class TestSharedToolsNamd(unittest.TestCase):
    def test_directory_form_accepted(self):
        path, source = namd_build_dir({"process": {"namdBin": "/srv/NAMD"}})
        self.assertEqual(path, "/srv/NAMD")
        self.assertIn("namdBin", source)

    def test_binary_form_normalised_to_directory(self):
        # The shell convention names the binary; the task config names the
        # directory. Both must land on the same build.
        path, _ = namd_build_dir({"tools": {"namd3": "/srv/NAMD/namd3"}})
        self.assertEqual(path, "/srv/NAMD")

    def test_env_var_used(self):
        path, source = namd_build_dir({}, {"NAMD_BIN": "/opt/namd/namd3"})
        self.assertEqual(path, "/opt/namd")
        self.assertEqual(source, "$NAMD_BIN")

    def test_default_is_the_deployed_layout(self):
        path, source = namd_build_dir({})
        self.assertEqual(source, "default")
        self.assertTrue(path.startswith("~/"))

    def test_describe_names_both_binaries(self):
        d = describe_namd({"process": {"namdBin": "/srv/NAMD"}})
        self.assertIn("/srv/NAMD/charmrun", d["command"])
        self.assertIn("/srv/NAMD/namd3", d["command"])

    def test_describe_flags_a_missing_build(self):
        d = describe_namd({"process": {"namdBin": "/nope/NAMD"}})
        self.assertFalse(d["ok"])
        self.assertIn("error", d)


if __name__ == "__main__":
    unittest.main()