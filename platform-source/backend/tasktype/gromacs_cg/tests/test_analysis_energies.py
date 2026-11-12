"""Energies module tests against a real GROMACS EDR (skipped when absent).

Set CG_TEST_EDR (or rely on the default /tmp/opencode/gmxtest/run.edr) and a
gmx binary (GMX_BIN or GROMACS_BIN; defaults to `gmx` on PATH) to exercise the
extraction. Pure xvg parsing is always tested.
"""
import os
import sys
import unittest

_GC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _GC_DIR)
# _shared lives beside tasktype/, i.e. two levels up from this tasktype.
sys.path.insert(0, os.path.abspath(os.path.join(_GC_DIR, "..", "..")))

from lib.analysis import energies  # noqa: E402

TEST_EDR = os.environ.get(
    "CG_TEST_EDR",
    "/tmp/opencode/gmxtest/run.edr" if os.path.exists("/tmp/opencode/gmxtest/run.edr") else "",
)
GMX_BIN = os.environ.get("GMX_BIN") or os.environ.get("GROMACS_BIN") or "gmx"


class TestParsing(unittest.TestCase):
    def test_parse_xvg_numeric(self):
        raw = """# comment
   @ fake 1 2
   0.0  1.0  2.5
   0.5  3.0  4.5
"""
        rows = energies.parse_xvg_numeric(raw)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], [0.0, 1.0, 2.5])


@unittest.skipUnless(TEST_EDR and os.access(GMX_BIN, os.X_OK),
                     "gmx binary or test EDR not available")
class TestGmxExtraction(unittest.TestCase):
    def test_extract_series(self):
        import tempfile
        import numpy as np
        with tempfile.TemporaryDirectory() as d:
            xvg = os.path.join(d, "out.xvg")
            rows = energies.extract_series(TEST_EDR, "Total-Energy", xvg)
            self.assertTrue(len(rows) > 0)
            for t, v in rows:
                self.assertGreaterEqual(t, 0)
                self.assertTrue(np.isfinite(v), v)

    def test_analyze_smoke(self):
        # Build a minimal task dir with just the EDR under output/sample.
        import json
        import shutil
        import tempfile
        from lib.analysis import paths
        tmp = tempfile.mkdtemp(prefix="cg_edr_")
        try:
            task = os.path.join(tmp, "task")
            sample = os.path.join(task, "output", "sample0")
            os.makedirs(sample, exist_ok=True)
            shutil.copy(TEST_EDR, os.path.join(sample, "relax.edr"))
            cfg = paths.load_task_config(task)
            res = energies.analyze(task, cfg)
            self.assertTrue(res["ok"])
            with open(os.path.join(paths.analysis_dir(task), "energy.dat")) as f:
                lines = [l for l in f.read().splitlines() if l and not l.startswith("#")]
            self.assertTrue(len(lines) > 0)
            # total_energy column present (not empty).
            self.assertNotEqual(lines[0].split("\t")[2], "")
            sys.stderr.write(f"  energy.dat rows={len(lines)}\n")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()