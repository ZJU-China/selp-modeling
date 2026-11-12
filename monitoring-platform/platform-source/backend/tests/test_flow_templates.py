"""Flow templates: shape and internal consistency.

The templates live in routes/flow-templates.js, so they are read by importing
that module under node and inspecting its exports. Duplicating the template
list here would let the two drift, which is the bug this guards against: a
handoff key naming a task type no template produces would silently create no
`next` wiring, and the step would never receive its upstream files, with no
error anywhere.
"""
import json
import os
import subprocess
import unittest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Task types that run in-process and must never be given a serverId.
LOCAL_TYPES = {"magnetomech", "flow_magnetomech"}

# Generator steps: run in-process via runTransition, not over SSH. The
# templates no longer use these (the conversion is folded into flow_tiger2), but
# the standalone types still exist and can be added by hand.
TRANSITION_TYPES = {"tiger2_dcd_to_gromacs_cg_pdb", "seq_to_pdb"}

# Task types whose generated outputs are produced by another type's generator,
# because they import it rather than fork it. flow_tiger2 folds in the DCD -> CG
# conversion, so its handoff outputs come from
# tiger2_dcd_to_gromacs_cg_pdb/generate.py.
REUSED_GENERATORS = {"flow_tiger2": "tiger2_dcd_to_gromacs_cg_pdb"}

# Task types whose Parameters panel is editable. Keyed on the `flow_*` wrappers,
# because services/editable-params.js keys its specs on those.
EDITABLE_TYPES = {"flow_tiger2", "flow_magnetomech", "flow_gromacs_cg"}


def _templates():
    script = (
        'import("./routes/flow-templates.js")'
        '.then(m => { console.log(JSON.stringify({'
        'templates: m.FLOW_TEMPLATES, handoff: m.HANDOFF })); process.exit(0); })'
        '.catch(e => { console.error(e.message); process.exit(1); });'
    )
    out = subprocess.run(["node", "-e", script], cwd=BACKEND,
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise AssertionError(f"could not import flow-templates.js: {out.stderr}")
    d = json.loads(out.stdout.strip().splitlines()[-1])
    return d["templates"], d["handoff"]


class TestFlowTemplates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.templates, cls.handoff = _templates()

    def test_empty_template_exists_and_has_no_steps(self):
        self.assertIn("empty", self.templates)
        self.assertEqual(self.templates["empty"]["steps"], [])

    def test_template_ids_are_unique(self):
        self.assertEqual(len(self.templates), len(set(self.templates)))

    def test_every_step_is_named_typed_and_labelled(self):
        for tid, spec in self.templates.items():
            self.assertTrue(spec.get("label"), f"{tid} has no label")
            for step in spec["steps"]:
                with self.subTest(template=tid):
                    self.assertTrue(step.get("name"), f"{tid} has an unnamed step")
                    self.assertTrue(step.get("taskType"), f"{tid} has an untyped step")

    def test_needs_server_agrees_with_which_types_are_local(self):
        """A step asking for a server must not be a local type.

        Local types are run in-process; handing one a serverId would make
        buildMainArgs build an SSH hop for a task that never needed one.
        """
        for tid, spec in self.templates.items():
            for step in spec["steps"]:
                with self.subTest(template=tid, step=step["name"]):
                    if step.get("needsServer"):
                        self.assertNotIn(step["taskType"], LOCAL_TYPES | TRANSITION_TYPES)
                    else:
                        self.assertIn(step["taskType"], LOCAL_TYPES | TRANSITION_TYPES)

    def test_compute_steps_are_types_with_an_editable_panel(self):
        """A step must be a type the Parameters panel can actually edit.

        The panel is driven by editable-params.js SPECS, which only covers the
        `flow_*` wrappers. A template built from the bare types therefore created
        steps that rendered a field list but rejected every save with "has no
        editable parameters" -- a flow that looked configurable and was not.
        """
        for tid, spec in self.templates.items():
            for step in spec["steps"]:
                if step["taskType"] in TRANSITION_TYPES:
                    continue  # pure conversion, nothing to configure
                with self.subTest(template=tid, step=step["name"]):
                    self.assertIn(
                        step["taskType"], EDITABLE_TYPES,
                        f"{step['taskType']} has no editable Parameters panel",
                    )

    def test_full_chain_folds_the_conversion_into_the_tiger2_step(self):
        """TIGER2 -> CG needs the DCD conversion, but not as its own step.

        NAMD writes DCD/coor/vel, which GROMACS cannot read; the conversion is
        what produces the CG start structure and .mdp. It used to be a separate
        step, which had no main.py, so flow start skipped it and it had to be
        triggered by hand. It is now folded into flow_tiger2 (its own output is
        the DCD source), so no template should list it as a step.
        """
        for tid in ("tiger2-to-cg", "full-chain"):
            with self.subTest(template=tid):
                types = [s["taskType"] for s in self.templates[tid]["steps"]]
                self.assertNotIn(
                    "tiger2_dcd_to_gromacs_cg_pdb", types,
                    f"{tid} still has a separate conversion step",
                )
                self.assertLess(
                    types.index("flow_tiger2"), types.index("flow_gromacs_cg"),
                    "TIGER2 must run before the CG step",
                )

    def test_handoff_files_are_produced_by_the_generating_step(self):
        """A handoff may only name files that step actually writes.

        This is the check that would have caught the original mapping, which
        named `extended.pdb`/`extended.cif` from TIGER2 -- files NAMD never
        writes, so every copy silently reported "source missing".
        """
        produced = self._known_outputs()
        for key, files in self.handoff.items():
            source = key.partition(">")[0]
            known = produced.get(source)
            if known is None:
                continue  # generator output not knowable from here
            for f in files:
                with self.subTest(key=key, output=f["output"]):
                    self.assertIn(
                        f["output"], known,
                        f"{source} does not produce {f['output']}; it writes {sorted(known)}",
                    )

    @classmethod
    def _known_outputs(cls):
        """Output names each tasktype's own code writes, read from its source.

        A type that imports another type's generator (REUSED_GENERATORS) is read
        from that generator, since its own main.py names no output files.
        """
        import re
        sources = {
            tt: os.path.join(BACKEND, "tasktype", tt, "generate.py")
            for tt in sorted(TRANSITION_TYPES)
        }
        for wrapper, gen_type in REUSED_GENERATORS.items():
            sources[wrapper] = os.path.join(BACKEND, "tasktype", gen_type, "generate.py")

        out = {}
        for tt, src in sources.items():
            if not os.path.exists(src):
                continue
            with open(src) as fh:
                text = fh.read()
            names = set(re.findall(r'["\']([\w.-]+\.(?:pdb|mdp|cif|gro|csv|top))["\']', text))
            # Snapshot directories are handed off too (e.g. "from-tiger2"), and
            # they are written as os.path.join(output_dir, "<name>") rather than
            # as a literal filename, so they need their own pattern.
            names |= set(re.findall(r'os\.path\.join\(output_dir,\s*["\']([\w.-]+)["\']\)', text))
            if names:
                out[tt] = names
        return out

    def test_handoff_names_types_some_template_actually_produces(self):
        used = {s["taskType"] for t in self.templates.values() for s in t["steps"]}
        for key in self.handoff:
            with self.subTest(key=key):
                source, _, target = key.partition(">")
                self.assertIn(source, used, f"{key}: no template produces {source}")
                self.assertIn(target, used, f"{key}: no template produces {target}")

    def test_handoff_entries_are_complete(self):
        for key, files in self.handoff.items():
            for f in files:
                with self.subTest(key=key):
                    self.assertTrue(f.get("output"), "handoff needs an output filename")
                    self.assertTrue(f.get("into"), "handoff needs a destination")

    def test_only_the_full_chain_needs_the_handoff_key(self):
        """At least one consecutive step pair must match a HANDOFF key.

        Otherwise the wiring exists but no template triggers it, which reads as
        working while handing nothing downstream.
        """
        pairs = set()
        for spec in self.templates.values():
            types = [s["taskType"] for s in spec["steps"]]
            pairs.update(zip(types, types[1:]))
        self.assertTrue(
            pairs, "no template has more than one step, so nothing can be chained"
        )
        matched = [f"{a}>{b}" for a, b in pairs if f"{a}>{b}" in self.handoff]
        self.assertTrue(
            matched,
            f"no consecutive template pair matches any HANDOFF key: {sorted(pairs)} vs {list(self.handoff)}",
        )

    def test_cg_step_receives_the_conversion_output(self):
        """The CG step must be wired to what the TIGER2 step now writes.

        Without this the CG step starts with an empty input and cannot run, even
        though every individual step looks correctly ordered. The producing step
        is flow_tiger2, which folds in the conversion.
        """
        files = self.handoff.get("flow_tiger2>flow_gromacs_cg", [])
        self.assertTrue(files, "the TIGER2 -> CG handoff is missing entirely")
        outs = {f["output"] for f in files}
        self.assertIn("cg_start.pdb", outs)
        self.assertIn("cg_input.mdp", outs)


if __name__ == "__main__":
    unittest.main()
