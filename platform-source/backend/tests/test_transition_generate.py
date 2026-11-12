"""The DCD -> CG generator, shared by the transition task and flow_tiger2.

`convert()` is imported by flow_tiger2 (which folds the conversion into the
TIGER2 step) and by the standalone transition task's CLI. Two properties matter
and are easy to break:

  * when the source *is* the output dir (the flow_tiger2 case) the snapshot step
    must not copy its own output back into itself recursively;
  * the DCD last frame is rebuilt onto the topology, and when there is no DCD
    the topology is used directly.
"""
import importlib.util
import os
import struct
import tempfile
import unittest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GENERATE = os.path.join(BACKEND, "tasktype", "tiger2_dcd_to_gromacs_cg_pdb", "generate.py")


def _load():
    spec = importlib.util.spec_from_file_location("tiger2_dcd_to_cg_generate_test", GENERATE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pdb_line(serial, name, resname, resseq, x, y, z, element="C"):
    return (
        "ATOM  %5d %-4s%1s%-4s%1s%4d    %8.3f%8.3f%8.3f%6.2f%6.2f          %2s  \n"
        % (serial, name, " ", resname, "A", resseq, x, y, z, 1.00, 0.00, element)
    )


def _write_dcd(path, coords):
    """Minimal CHARMM DCD with one frame of `coords` [(x, y), ...].

    Matches the layout generate.dcd_last_frame reads: CORD at byte 0, an 80-byte
    header, then [4][natoms][4], then three separately wrapped X/Y/Z blocks.
    """
    natoms = len(coords)
    body = b"CORD" + b"\x00" * 80
    body += struct.pack("<i", 4) + struct.pack("<i", natoms) + struct.pack("<i", 4)
    for axis in range(3):
        vals = [c[axis] for c in coords]
        body += struct.pack("<i", natoms * 4)
        body += struct.pack("<%df" % natoms, *vals)
        body += struct.pack("<i", natoms * 4)
    with open(path, "wb") as f:
        f.write(body)


class TestConvert(unittest.TestCase):
    def setUp(self):
        self.gen = _load()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_self_source_snapshot_does_not_recurse(self):
        """flow_tiger2 converts its own output dir; the snapshot must not copy
        from-tiger2 into itself, nor sweep up the CG inputs it writes."""
        output = os.path.join(self.root, "output")
        os.makedirs(os.path.join(output, "from-tiger2"))
        with open(os.path.join(output, "run.txt"), "w") as f:
            f.write("raw tiger2 output\n")
        with open(os.path.join(output, "from-tiger2", "old.txt"), "w") as f:
            f.write("stale snapshot\n")

        result = self.gen.convert(output, output, temperature_c=37.0, generator="test")

        self.assertTrue(result["ok"])
        # The raw output is snapshotted ...
        self.assertTrue(os.path.exists(os.path.join(output, "from-tiger2", "run.txt")))
        # ... but the snapshot is not nested inside itself, and the conversion's
        # own outputs are not copied into the snapshot.
        self.assertFalse(os.path.exists(os.path.join(output, "from-tiger2", "from-tiger2")))
        self.assertFalse(os.path.exists(os.path.join(output, "from-tiger2", "cg_input.mdp")))
        self.assertFalse(os.path.exists(os.path.join(output, "from-tiger2", "README.txt")))
        # The conversion still wrote the mdp + README at the top level.
        self.assertTrue(os.path.exists(os.path.join(output, "cg_input.mdp")))
        self.assertTrue(os.path.exists(os.path.join(output, "README.txt")))
        # No trajectory and no topology: no cg_start.pdb.
        self.assertNotIn("cg_start.pdb", result["files"])

    def test_dcd_last_frame_is_rebuilt_onto_the_topology(self):
        src = os.path.join(self.root, "src", "output")
        out = os.path.join(self.root, "out")
        os.makedirs(src)
        n = 20  # frames must push the file past dcd_last_frame's 300-byte floor
        coords = [(float(i), float(i) + 0.5, float(i) + 1.0) for i in range(n)]
        with open(os.path.join(src, "topology.pdb"), "w") as f:
            for i in range(n):
                f.write(_pdb_line(i + 1, "CA", "ALA", 1, 0.0, 0.0, 0.0))
        _write_dcd(os.path.join(src, "run.dcd"), coords)

        result = self.gen.convert(src, out, temperature_c=37.0, src_id="task_up")

        self.assertTrue(result["ok"])
        self.assertIn("cg_start.pdb", result["files"])
        with open(os.path.join(out, "cg_start.pdb")) as f:
            text = f.read()
        # Coordinates came from the DCD frame, not the topology.
        self.assertIn("19.000", text)
        self.assertIn("20.000", text)
        # The upstream snapshot carries the source files.
        self.assertTrue(os.path.exists(os.path.join(out, "from-tiger2", "topology.pdb")))
        self.assertTrue(os.path.exists(os.path.join(out, "from-tiger2", "run.dcd")))

    def test_no_trajectory_falls_back_to_the_topology(self):
        src = os.path.join(self.root, "src", "output")
        out = os.path.join(self.root, "out")
        os.makedirs(src)
        with open(os.path.join(src, "topology.pdb"), "w") as f:
            f.write(_pdb_line(1, "CA", "ALA", 1, 1.0, 1.0, 1.0))

        result = self.gen.convert(src, out, temperature_c=37.0)

        self.assertIn("cg_start.pdb", result["files"])
        self.assertTrue(os.path.exists(os.path.join(out, "cg_start.pdb")))
        self.assertTrue(any("topology" in n.lower() for n in result["notes"]))

    def test_temperature_is_celsius_to_kelvin(self):
        src = os.path.join(self.root, "src", "output")
        out = os.path.join(self.root, "out")
        os.makedirs(src)
        result = self.gen.convert(src, out, temperature_c=25.0)
        self.assertAlmostEqual(result["temperatureK"], 298.15)
        with open(os.path.join(out, "cg_input.mdp")) as f:
            self.assertIn("298.15", f.read())


if __name__ == "__main__":
    unittest.main()
