"""Shared route: residue-level sequence annotations.

Two sub-commands:
  (default)   the annotation table for the viewer
  derive      reverse the structure back to its one-letter input sequence
"""
from _shared import sequence_annotation


def handle(ssh, cfg, args, local_task):
    if getattr(args, "sub", None) == "derive":
        return sequence_annotation.derive_sequence(local_task)
    return sequence_annotation.compute(local_task, cfg)
