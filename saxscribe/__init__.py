"""The old name of Lift, kept so old commands and saved scripts keep working.

Saxscribe was renamed Lift on 2026-11-16 (ADR-0047). The code lives in lift/.
`import saxscribe.score.card` hands back the very same module as
`import lift.score.card` (not a second copy), and `python -m saxscribe ...`
runs `python -m lift ...`. New code should import lift.
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys

_PREFIX = __name__ + "."


class _Alias(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Finds saxscribe.<x> by importing lift.<x> and handing back that module."""

    @staticmethod
    def _real_name(alias: str) -> str:
        return "lift." + alias[len(_PREFIX):]

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(_PREFIX) or fullname == _PREFIX + "__main__":
            return None  # python -m saxscribe runs our own __main__.py
        try:
            real = importlib.util.find_spec(self._real_name(fullname))
        except ModuleNotFoundError:
            real = None
        if real is None:
            return None  # a normal "No module named saxscribe.x"
        return importlib.util.spec_from_loader(fullname, self, origin=real.origin,
                                              is_package=real.submodule_search_locations is not None)

    def __init__(self):
        self._specs = {}  # lift module name -> its own spec, by name so threads can't mix them up

    def create_module(self, spec):
        real = importlib.import_module(self._real_name(spec.name))
        self._specs.setdefault(real.__name__, real.__spec__)
        return real

    def exec_module(self, module):
        # importlib stamps the alias spec on the module; give lift's own back.
        module.__spec__ = self._specs[module.__name__]

    def get_code(self, fullname):
        """python -m saxscribe.<x> runs lift.<x>."""
        real = importlib.util.find_spec(self._real_name(fullname))
        return real.loader.get_code(real.name)


# Installed before anything else here, so a thread importing saxscribe.<x> while
# this package is still loading already finds the alias.
if not any(type(f).__name__ == "_Alias" and getattr(f, "_saxscribe_alias", False) for f in sys.meta_path):
    _finder = _Alias()
    _finder._saxscribe_alias = True
    sys.meta_path.insert(0, _finder)

import lift as _lift  # noqa: E402

# Names at the top of the package (LAYERS, LAYOUT_VERSION, ...) read through too.
globals().update({k: v for k, v in vars(_lift).items() if not k.startswith("__")})
