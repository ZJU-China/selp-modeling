"""A parameter set in the UI has to be the value the run uses.

Each tasktype's ``task_config.template.json`` nests run settings under
``defaults``, but ``persistTaskConfig`` (what ``PUT /api/tasks/:id/params``
calls) merges the panel's values as *flat* top-level keys. When the readers only
looked in ``defaults``, the panel accepted the value, returned ``ok: true``, and
the simulation ran on the template default instead -- silently, with plausible
numbers, which is the worst way for this to fail.

These tests pin both halves of the contract: flat values win, and a config with
only ``defaults`` still works.
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..")
sys.path.insert(0, BACKEND)

from _shared.config_lookup import value_lookup  # noqa: E402


def _load_by_path(name, relative):
    """Load a tasktype's module by path.

    Every tasktype ships its own ``lib/task_config.py``, so they cannot both be
    imported as ``lib.task_config`` -- the second would shadow the first.
    """
    spec = importlib.util.spec_from_file_location(name, os.path.join(BACKEND, relative))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cg_load = _load_by_path("cg_task_config", "tasktype/gromacs_cg/lib/task_config.py").load
_tiger2_mod = _load_by_path("t2_task_config", "tasktype/tiger2/lib/task_config.py")
_t2_load = _tiger2_mod.load
_paths_mod = _load_by_path("cg_analysis_paths",
                           "tasktype/gromacs_cg/lib/analysis/paths.py")


def _template(tasktype):
    with open(os.path.join(BACKEND, "tasktype", tasktype,
                           "task_config.template.json")) as fh:
        raw = json.load(fh)
    raw.pop("_comment", None)
    return raw


class TestValueLookup(unittest.TestCase):
    def test_flat_wins_over_defaults(self):
        d = value_lookup({"defaults": {"numReplicas": 4}, "numReplicas": 7})
        self.assertEqual(d.int_("numReplicas", 1), 7)

    def test_defaults_used_when_flat_absent(self):
        d = value_lookup({"defaults": {"numReplicas": 4}})
        self.assertEqual(d.int_("numReplicas", 1), 4)

    def test_fallback_when_absent_everywhere(self):
        d = value_lookup({})
        self.assertEqual(d.int_("numReplicas", 9), 9)

    def test_empty_string_is_treated_as_unset(self):
        # An empty form field must not blank out a configured default.
        d = value_lookup({"defaults": {"numReplicas": 4}, "numReplicas": ""})
        self.assertEqual(d.int_("numReplicas", 1), 4)

    def test_non_numeric_falls_back(self):
        d = value_lookup({"numReplicas": "not-a-number"})
        self.assertEqual(d.int_("numReplicas", 3), 3)

    def test_float_key_reads_int_value(self):
        self.assertEqual(value_lookup({"totalCycles": "5"}).float_("totalCycles", 10), 5.0)


class TestGromacsCg(unittest.TestCase):
    def test_panel_values_are_used(self):
        cfg = _template("gromacs_cg")
        cfg.update(numReplicas=2, stepsPerCycle=100000, totalCycles=5,
                   protein="2KY10 SELP CG crosslinked")
        c = cg_load(cfg)
        self.assertEqual(c.num_replicas, 2)
        self.assertEqual(int(c.steps_per_cycle), 100000)
        self.assertEqual(c.total_cycles, 5)
        self.assertEqual(c.protein, "2KY10 SELP CG crosslinked")

    def test_defaults_still_honoured(self):
        c = cg_load(_template("gromacs_cg"))
        self.assertEqual(c.num_replicas, 1)
        self.assertEqual(int(c.steps_per_cycle), 500000)


class TestTiger2(unittest.TestCase):
    def _cfg(self, **over):
        raw = _template("tiger2")
        raw["defaults"].setdefault("numReplicas", 4)
        raw["defaults"].setdefault("stepsPerCycle", 15000)
        raw["defaults"].setdefault("totalCycles", 1667)
        raw.update(over)
        return raw

    def _write(self, tmp, raw):
        p = os.path.join(tmp, "task_config.json")
        with open(p, "w") as fh:
            json.dump(raw, fh)
        return p

    def test_panel_values_are_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, self._cfg(numReplicas=7, stepsPerCycle=5000,
                                             totalCycles=10))
            c = _t2_load(path)
        self.assertEqual(c.num_replicas, 7)
        self.assertEqual(c.steps_per_cycle, 5000)
        self.assertEqual(c.total_cycles, 10)

    def test_defaults_still_honoured(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, self._cfg())
            c = _t2_load(path)
        self.assertEqual(c.num_replicas, 4)
        self.assertEqual(c.steps_per_cycle, 15000)


class TestAnalysisPaths(unittest.TestCase):
    def test_analysis_uses_the_configured_cycle_count(self):
        """The CG analysis must convert the length the run actually used.

        This module reads the config directly rather than through the loader, so
        it was the one place still reporting the template value after the panel
        was fixed -- yielding a trajectory length in ns that did not match the
        run that produced the trajectory.
        """
        fn = _paths_mod.load_task_config
        with tempfile.TemporaryDirectory() as tmp:
            scripts = os.path.join(tmp, "scripts")
            os.makedirs(scripts)
            with open(os.path.join(scripts, "task_config.json"), "w") as fh:
                json.dump({"defaults": {"totalCycles": 10, "stepsPerCycle": 500000},
                           "totalCycles": 4, "stepsPerCycle": 250000}, fh)
            resolved = fn(tmp)
        self.assertEqual(resolved["totalCycles"], 4)
        self.assertEqual(resolved["stepsPerCycle"], 250000)


if __name__ == "__main__":
    unittest.main()