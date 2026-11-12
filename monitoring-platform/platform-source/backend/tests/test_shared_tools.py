"""Tool resolution: PATH names, absolute paths, and container commands."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from _shared.tools import describe, resolve_argv  # noqa: E402


class TestResolve(unittest.TestCase):
    def setUp(self):
        # Isolate from whatever the developer has exported.
        for var in ("GMX_BIN", "GROMACS_BIN", "MATLAB_BIN"):
            os.environ.pop(var, None)

    def test_defaults_to_a_bare_name_on_path(self):
        # gmx is on PATH on the iGEM server, so the fallback must be the name
        # rather than a hardcoded path that does not exist there.
        self.assertEqual(resolve_argv("gmx"), ["gmx"])
        self.assertEqual(resolve_argv("matlab"), ["matlab"])

    def test_absolute_path_is_used_verbatim(self):
        argv = resolve_argv("gmx", {"tools": {"gmx": "/opt/app/gromacs/bin/gmx_mpi"}})
        self.assertEqual(argv, ["/opt/app/gromacs/bin/gmx_mpi"])

    def test_container_command_is_split_into_argv(self):
        # MATLAB runs from the mathworks/matlab image on the iGEM server, so the
        # real invocation is a docker exec, not a path.
        argv = resolve_argv("matlab", {"tools": {"matlab": "docker exec matlab-gui matlab"}})
        self.assertEqual(argv, ["docker", "exec", "matlab-gui", "matlab"])
        self.assertTrue(describe("matlab", {"tools": {"matlab": "docker exec matlab-gui matlab"}})["viaContainer"])

    def test_task_config_beats_environment(self):
        os.environ["GMX_BIN"] = "/from/env/gmx"
        self.assertEqual(resolve_argv("gmx"), ["/from/env/gmx"])
        self.assertEqual(resolve_argv("gmx", {"tools": {"gmx": "/from/task/gmx"}}), ["/from/task/gmx"])

    def test_both_gromacs_env_spellings_work(self):
        os.environ["GROMACS_BIN"] = "/opt/gmx"
        self.assertEqual(resolve_argv("gmx"), ["/opt/gmx"])

    def test_missing_path_is_reported_not_silently_replaced(self):
        info = describe("gmx", {"tools": {"gmx": "/definitely/not/here/gmx"}})
        self.assertFalse(info["ok"])
        self.assertIn("does not exist", info["error"])

    def test_empty_command_is_an_error(self):
        self.assertFalse(describe("gmx", {"tools": {"gmx": "   "}})["ok"])


if __name__ == "__main__":
    unittest.main()
