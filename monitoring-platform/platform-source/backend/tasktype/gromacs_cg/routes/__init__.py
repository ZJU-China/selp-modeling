"""GROMACS CG route dispatcher — uses the shared build_dispatcher factory."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from _shared.routes import build_dispatcher

dispatch = build_dispatcher(__name__)