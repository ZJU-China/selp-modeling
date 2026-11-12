"""flow_tiger2 folds in the DCD -> CG conversion.

The heavyweight conversion is tested in test_transition_generate.py; what is
specific to the wrapper is the thin layer around it: which commands regenerate
the CG inputs, and how the CG temperature is derived from the task's own
parameters. Both are easy to get wrong silently -- a wrong temperature still
writes a plausible .mdp, and a missed trigger still writes plausible files,
just at the wrong times.
"""
import argparse
import importlib.util
import os
import tempfile
import unittest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAIN = os.path.join(BACKEND, "tasktype", "flow_tiger2", "main.py")


def _load():
    spec = importlib.util.spec_from_file_location("flow_tiger2_main_test", MAIN)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestFlowTiger2Conversion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.local = self.tmp.name
        os.makedirs(os.path.join(self.local, "output"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_convert_command_is_accepted(self):
        args = self.mod.build_arg_parser().parse_args(
            ["convert", "--local-dir", self.local]
        )
        self.assertEqual(args.command, "convert")

    def test_temperature_falls_back_to_celsius_default(self):
        # No temperature configured anywhere: synthesize() uses 310 K, so the
        # CG start temperature must be 310 K too, not an arbitrary 37 C.
        result = self.mod.convert(self.local, {})
        self.assertAlmostEqual(result["temperatureK"], 310.0)

    def test_temperature_uses_celsius_field_when_present(self):
        result = self.mod.convert(self.local, {"temperatureC": 25.0})
        self.assertAlmostEqual(result["temperatureK"], 298.15)

    def test_temperature_round_trips_from_the_run_temperature(self):
        # flow_tiger2 stores the run temperature in Kelvin; the generator wants
        # Celsius. 310 K must come back out as 310 K.
        result = self.mod.convert(self.local, {"temperature": 310})
        self.assertAlmostEqual(result["temperatureK"], 310.0)

    def test_temperature_reads_the_nested_defaults(self):
        # synthesize() reads config.defaults.temperature as well as the
        # top-level field; both must feed the conversion.
        result = self.mod.convert(self.local, {"defaults": {"temperature": 330}})
        self.assertAlmostEqual(result["temperatureK"], 330.0)

    def test_trajectory_download_triggers_conversion(self):
        self.assertTrue(self.mod._brings_trajectory_local(
            argparse.Namespace(command="route", route="trajectory")))
        self.assertTrue(self.mod._brings_trajectory_local(
            argparse.Namespace(command="sync", route=None)))
        self.assertTrue(self.mod._brings_trajectory_local(
            argparse.Namespace(command="organize", route=None)))

    def test_other_route_reads_do_not_trigger_conversion(self):
        for route in ("jobs", "status", "sequences", "shell"):
            with self.subTest(route=route):
                self.assertFalse(self.mod._brings_trajectory_local(
                    argparse.Namespace(command="route", route=route)))
        self.assertFalse(self.mod._brings_trajectory_local(
            argparse.Namespace(command="start", route=None)))
        self.assertFalse(self.mod._brings_trajectory_local(
            argparse.Namespace(command="status", route=None)))


if __name__ == "__main__":
    unittest.main()
