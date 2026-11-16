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

import lift as _lift

_PREFIX = __name__ + "."


class _Alias(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Finds saxscribe.<x> by importing lift.<x> and handing back that module."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(_PREFIX) and fullname != _PREFIX + "__main__":  # -m saxscribe uses ours
            return importlib.util.spec_from_loader(fullname, self)
        return None

    def create_module(self, spec):
        real = importlib.import_module("lift." + spec.name[len(_PREFIX):])
        self._real_spec = real.__spec__
        return real

    def exec_module(self, module):
        # importlib stamps the alias spec on the module; give lift's own back.
        module.__spec__ = self._real_spec


if not any(isinstance(f, _Alias) for f in sys.meta_path):
    sys.meta_path.insert(0, _Alias())

# Names at the top of the package (LAYERS, LAYOUT_VERSION, ...) read through too.
globals().update({k: v for k, v in vars(_lift).items() if not k.startswith("__")})
