"""magnetomech route dispatcher — local computation, no remote host is ever
contacted, so each handler returns a benign no-op result. Uses the shared
build_dispatcher factory.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from _shared.routes import build_dispatcher

dispatch = build_dispatcher(__name__)