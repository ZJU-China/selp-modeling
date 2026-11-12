"""Wrapper tasktypes must accept every command their base implements.

flow_tiger2 / flow_gromacs_cg / flow_magnetomech mirror the base tasktype's CLI
and then delegate with `subprocess.call([python, BASE_MAIN] + sys.argv[1:])`.
The base can grow a command that the wrapper's own `choices=[...]` does not list,
and the result is an argparse rejection -- "invalid choice: 'pause'" -- even though
the delegated implementation exists and works.

That drift is invisible in the base tasktype's own tests, so it is pinned here.

The three tasktypes express their command set three different ways (an argparse
choices list, an if/elif chain, and a dispatch dict), so each is read from its own
source form. The assertion is one-directional and intentional: a wrapper may accept
more than its base, but never less.
"""
import ast
import os
import unittest

TASKTYPE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "tasktype")
)

WRAPPERS = {
    "flow_tiger2": "tiger2",
    "flow_gromacs_cg": "gromacs_cg",
    "flow_magnetomech": "magnetomech",
}


def _command_choices(tree):
    """Commands rejected by argparse's `choices=[...]` on the 'command' arg.

    None when the parser does not restrict commands, which is the case for
    tiger2/magnetomech: they accept any string and dispatch themselves.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_argument"):
            continue
        if not node.args or getattr(node.args[0], "value", None) != "command":
            continue
        for kw in node.keywords:
            if kw.arg != "choices":
                continue
            if not isinstance(kw.value, ast.List):
                raise AssertionError("command choices is not a literal list")
            return {ast.literal_eval(e) for e in kw.value.elts}
    return None


def _handled_commands(tree):
    """Commands the implementation actually acts on.

    Covers both dispatch styles in use:
      * `elif cmd == "start":` chains (tiger2)
      * a dict named `commands` mapping command -> handler (gromacs_cg)

    Only that one dict is read. Matching every dict literal in the file would
    sweep up JSON response keys ("ok", "error", "remoteDir", ...) and produce a
    nonsense "missing commands" list.
    """
    found = set()
    for node in ast.walk(tree):
        # if/elif chains
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name):
            if node.left.id == "cmd" and len(node.ops) == 1:
                op = node.ops[0]
                if isinstance(op, ast.Eq) and isinstance(node.comparators[0], ast.Constant):
                    if isinstance(node.comparators[0].value, str):
                        found.add(node.comparators[0].value)
        # the named dispatch dict only
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "commands":
                    for key in node.value.keys:
                        if isinstance(key, ast.Constant) and isinstance(key.value, str):
                            found.add(key.value)
    return found


def _read(path):
    with open(path) as fh:
        return ast.parse(fh.read())


class TestWrapperChoicesCoverBase(unittest.TestCase):
    def test_wrappers_are_not_narrower_than_their_base(self):
        for wrapper, base in WRAPPERS.items():
            with self.subTest(wrapper=wrapper):
                wrapper_choices = _command_choices(
                    _read(os.path.join(TASKTYPE_DIR, wrapper, "main.py"))
                )
                base_handled = _handled_commands(
                    _read(os.path.join(TASKTYPE_DIR, base, "main.py"))
                )
                if wrapper_choices is None:
                    # No argparse restriction, so it cannot reject anything.
                    continue
                missing = base_handled - wrapper_choices
                self.assertEqual(
                    missing, set(),
                    f"{wrapper}/main.py would reject {sorted(missing)} with "
                    f"'invalid choice', even though {base}/main.py implements it. "
                    f"Add them to its choices list.",
                )

    def test_choices_cover_handled_commands(self):
        """A tasktype's own choices list must list everything it handles.

        This is the same failure one level down, and it is the one that actually
        shipped: tiger2/main.py gained `elif cmd == "pause"` while its
        argparse choices list did not gain "pause", so the command was
        implemented and reachable in the source but rejected at the parser.
        Comparing a base's handled commands only against *wrapper* choices
        missed it entirely.
        """
        for tasktype in sorted(set(WRAPPERS.values())):
            with self.subTest(tasktype=tasktype):
                tree = _read(os.path.join(TASKTYPE_DIR, tasktype, "main.py"))
                choices = _command_choices(tree)
                if choices is None:
                    continue  # no restriction, nothing can be rejected
                missing = _handled_commands(tree) - choices
                self.assertEqual(
                    missing, set(),
                    f"{tasktype}/main.py handles {sorted(missing)} but its argparse "
                    f"choices list omits them, so they fail with 'invalid choice'.",
                )

    def test_wrappers_still_delegate_verbatim(self):
        # The coverage above is only sound because argv is passed through
        # untouched. Assert that, so a future refactor that filters commands
        # fails here instead of silently reintroducing the mismatch.
        for wrapper, base in WRAPPERS.items():
            with self.subTest(wrapper=wrapper):
                with open(os.path.join(TASKTYPE_DIR, wrapper, "main.py")) as fh:
                    src = fh.read()
                self.assertIn(f'"{base}"', src, f"{wrapper} no longer names its base")
                self.assertIn(
                    "sys.argv[1:]", src,
                    f"{wrapper} must still delegate verbatim via sys.argv[1:]; "
                    f"the choices test assumes no command is filtered out.",
                )

    def test_pause_and_continue_reachable_for_pausable_wrappers(self):
        # magnetomech is a one-shot local compute with no long-running process
        # to suspend, so it deliberately opts out.
        for wrapper, base in WRAPPERS.items():
            if wrapper == "flow_magnetomech":
                continue
            with self.subTest(wrapper=wrapper):
                with open(os.path.join(TASKTYPE_DIR, wrapper, "main.py")) as fh:
                    wrapper_choices = _command_choices(ast.parse(fh.read()))
                self.assertIsNotNone(
                    wrapper_choices,
                    f"{wrapper} has no command choices, so it cannot reject anything",
                )
                assert wrapper_choices is not None
                self.assertIn("pause", wrapper_choices)
                self.assertIn("continue", wrapper_choices)

if __name__ == "__main__":
    unittest.main()