"""Shared route dispatcher for tasktype routes."""

from importlib import import_module

ROUTE_NAMES = ("files", "jobs", "sequences", "shell", "status", "trajectory")


def build_dispatcher(package):
    """Import ``package``'s standard route modules and build its dispatch fn.

    ``package`` is the route package's ``__name__`` (e.g. ``"routes"``); the
    six module names live in ``ROUTE_NAMES``. Keeps per-tasktype dispatchers
    as a one-line ``dispatch = build_dispatcher(__package__)`` instead of a
    duplicated ``sys.path`` preamble plus a hand-written ROUTES dict.
    """
    modules = {}
    for name in ROUTE_NAMES:
        modules[name] = import_module(f"{package}.{name}")
    return make_dispatch(modules)


def make_dispatch(route_modules):
    """Create a dispatch function from a dict of route name -> module.

    Each module must expose `handle(ssh, cfg, args, local_task)`.
    """
    def dispatch(ssh, cfg, args, local_task):
        mod = route_modules.get(args.route)
        if mod is None:
            return {"ok": False, "error": f"unknown route {args.route!r}"}
        try:
            return mod.handle(ssh, cfg, args, local_task)
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return dispatch
