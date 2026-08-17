"""The core-purity hard rule, enforced.

`models`, `codec`, and `errors` must import with every optional dependency
sabotaged out of `sys.modules`. Two reasons this is load-bearing (CLAUDE.md §2):

1. `asyncua` is LGPL-3.0. Never importing it from core keeps loopsheet's
   Apache-2.0 grant clean.
2. The whole value proposition is modelling a machine on a laptop with no
   drivers installed.

Sabotage rather than "check it isn't installed": the test has to fail when
someone adds the import, on a machine where the extra *is* present.
"""

from __future__ import annotations

import builtins
import importlib
import subprocess
import sys
from collections.abc import Iterator, Sequence
from types import ModuleType
from typing import Any

import pytest

#: Every optional dependency, plus the transitive names that would give one
#: away. `bindings`, `io`, `export`, and `adapters` join the guarded list as
#: they land in later phases.
FORBIDDEN_IN_CORE = (
    "paho",
    "aiomqtt",
    "asyncua",
    "pycomm3",
    "httpx",
    "pymodbus",
    "pint",
    "basyx",
    "numpy",
    "requests",
    "aiohttp",
)

#: The modules that must stay pure.
CORE_MODULES = (
    "loopsheet",
    "loopsheet.errors",
    "loopsheet.models",
    "loopsheet.models.base",
    "loopsheet.models.units",
    "loopsheet.models.datatype",
    "loopsheet.models.reading",
    "loopsheet.models.channel",
    "loopsheet.models.processdata",
    "loopsheet.models.asset",
    "loopsheet.models.component_base",
    "loopsheet.models.sensor",
    "loopsheet.models.iolink",
    "loopsheet.models.controller",
    "loopsheet.models.daq",
    "loopsheet.models.component",
    "loopsheet.models.site",
    "loopsheet.codec",
    "loopsheet.codec.datatypes",
    "loopsheet.codec.processdata",
    "loopsheet.codec.decode",
    "loopsheet.codec.scaling",
)


@pytest.fixture
def sabotaged_imports() -> Iterator[None]:
    """Make every optional dependency unimportable for the duration of a test."""
    real_import = builtins.__import__
    saved = {name: sys.modules.pop(name, None) for name in FORBIDDEN_IN_CORE}
    for name in list(sys.modules):
        if name.split(".", 1)[0] in FORBIDDEN_IN_CORE:
            saved.setdefault(name, sys.modules.pop(name))

    def guarded(
        name: str,
        globals_: dict[str, Any] | None = None,
        locals_: dict[str, Any] | None = None,
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> ModuleType:
        if name.split(".", 1)[0] in FORBIDDEN_IN_CORE:
            raise ImportError(
                f"{name!r} is not importable from loopsheet core — see the "
                "core-purity rule in CLAUDE.md §2"
            )
        return real_import(name, globals_, locals_, fromlist, level)

    builtins.__import__ = guarded
    try:
        yield
    finally:
        builtins.__import__ = real_import
        for name, module in saved.items():
            if module is not None:
                sys.modules[name] = module


@pytest.mark.parametrize("module", CORE_MODULES)
def test_core_imports_with_every_optional_dependency_sabotaged(
    module: str, sabotaged_imports: None
) -> None:
    for name in list(sys.modules):
        if name == "loopsheet" or name.startswith("loopsheet."):
            del sys.modules[name]
    importlib.import_module(module)


@pytest.mark.parametrize(
    "first",
    ["loopsheet.models", "loopsheet.codec"],
)
def test_either_subpackage_can_be_imported_first(first: str) -> None:
    """`models` and `codec` reference each other's modules; neither may deadlock.

    Run in a subprocess so the import really is cold. A cycle that only shows
    up on one import order is exactly the kind of bug a warm `sys.modules`
    hides.
    """
    result = subprocess.run(
        [sys.executable, "-c", f"import {first}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_the_sabotage_actually_bites() -> None:
    """A test that cannot fail proves nothing. Confirm the fixture blocks imports."""
    real_import = builtins.__import__

    def guarded(name: str, *args: Any, **kwargs: Any) -> ModuleType:
        if name.split(".", 1)[0] in FORBIDDEN_IN_CORE:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    builtins.__import__ = guarded
    try:
        with pytest.raises(ImportError):
            importlib.import_module("httpx")
    finally:
        builtins.__import__ = real_import
