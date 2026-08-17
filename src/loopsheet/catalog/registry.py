"""Finding and loading catalog entries.

Resources are reached through :mod:`importlib.resources`, never through
``__file__``-relative paths. A ``__file__`` path is wrong the moment the
package is loaded from a zip, a frozen bundle, or an editable install laid out
differently from the source tree — and "the catalog is empty" is a
spectacularly confusing failure to debug.

Layout
======

A vendor pack is an importable package whose directory contains one YAML file
per part number::

    loopsheet/catalog/data/ifm/VVB020.yaml   ->   ifm:VVB020

The *file name* is the part number and the *directory name* is the vendor, so
:func:`list_parts` can enumerate the catalog without opening, parsing, or
validating a single file. That is the guarantee worth having: listing 400 parts
should not cost 400 YAML parses.

Third-party packs
=================

Any distribution can ship parts by advertising the ``loopsheet.catalog``
entry-point group::

    [project.entry-points."loopsheet.catalog"]
    acme = "acme_loopsheet.parts"

**On "no vendor imports".** :func:`list_parts` never calls
``EntryPoint.load()``, so no vendor *code* runs and no YAML is parsed. It does
import the named package itself, because that is what
``importlib.resources.files()` requires to locate its data. Keep vendor pack
``__init__.py`` files empty — they are data packages, and anything executable
in one runs at discovery time.
"""

from __future__ import annotations

from functools import cache, lru_cache
from importlib import resources
from importlib.metadata import entry_points
from importlib.resources.abc import Traversable

import yaml

from loopsheet.catalog.schema import CatalogEntry
from loopsheet.errors import CatalogError

__all__ = ["clear_cache", "get", "list_parts", "vendors"]

#: Package holding the built-in vendor packs.
_BUILTIN_DATA_PACKAGE = "loopsheet.catalog.data"

#: Entry-point group third parties advertise vendor packs under.
_ENTRY_POINT_GROUP = "loopsheet.catalog"

_SUFFIXES = (".yaml", ".yml")


def _is_part_file(item: Traversable) -> bool:
    return item.is_file() and item.name.endswith(_SUFFIXES)


@lru_cache(maxsize=1)
def _vendor_packages() -> dict[str, str]:
    """Map vendor slug → importable package name.

    Built-in packs are found by walking :data:`_BUILTIN_DATA_PACKAGE`;
    third-party packs by entry point. A built-in vendor wins a name collision,
    so an installed package cannot silently shadow the shipped ``ifm`` data
    with its own.
    """
    found: dict[str, str] = {}

    try:
        root = resources.files(_BUILTIN_DATA_PACKAGE)
    except (ModuleNotFoundError, TypeError) as exc:  # pragma: no cover - packaging bug
        raise CatalogError(
            f"built-in catalog data package {_BUILTIN_DATA_PACKAGE!r} is not importable: {exc}"
        ) from exc

    for item in root.iterdir():
        if item.is_dir() and not item.name.startswith(("_", ".")):
            found[item.name] = f"{_BUILTIN_DATA_PACKAGE}.{item.name}"

    for entry_point in entry_points(group=_ENTRY_POINT_GROUP):
        found.setdefault(entry_point.name, entry_point.value)

    return found


def _pack(vendor: str) -> Traversable:
    """Return the resource directory for a vendor pack."""
    packages = _vendor_packages()
    package = packages.get(vendor)
    if package is None:
        known = ", ".join(sorted(packages)) or "none installed"
        raise CatalogError(f"unknown catalog vendor {vendor!r}. Known vendors: {known}")
    try:
        return resources.files(package)
    except ModuleNotFoundError as exc:
        raise CatalogError(
            f"catalog vendor {vendor!r} advertises package {package!r}, which is not "
            f"importable: {exc}"
        ) from exc


def vendors() -> list[str]:
    """Every vendor slug with parts available, sorted."""
    return sorted(_vendor_packages())


def list_parts(vendor: str | None = None) -> list[str]:
    """Every known part reference in ``vendor:PART`` form, sorted.

    Reads file names only — no YAML is opened or parsed, and no vendor code is
    executed. Pass ``vendor`` to list one pack.
    """
    targets = [vendor] if vendor is not None else vendors()
    refs: list[str] = []
    for name in targets:
        refs.extend(
            f"{name}:{item.name.rsplit('.', 1)[0]}"
            for item in _pack(name).iterdir()
            if _is_part_file(item)
        )
    return sorted(refs)


def _split_ref(ref: str) -> tuple[str, str]:
    vendor, _, part = ref.partition(":")
    if not vendor or not part:
        raise CatalogError(
            f"malformed catalog reference {ref!r}. Expected 'vendor:PART', e.g. 'ifm:VVB020'"
        )
    return vendor, part


@cache
def _load(ref: str) -> CatalogEntry:
    """Parse and validate one entry. Cached; callers get a copy."""
    vendor, part = _split_ref(ref)
    pack = _pack(vendor)

    for suffix in _SUFFIXES:
        candidate = pack / f"{part}{suffix}"
        if candidate.is_file():
            break
    else:
        available = ", ".join(sorted(p.split(":", 1)[1] for p in list_parts(vendor)))
        raise CatalogError(f"unknown part {ref!r}. {vendor} ships: {available or 'no parts'}")

    try:
        raw = yaml.safe_load(candidate.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CatalogError(f"catalog file for {ref!r} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise CatalogError(
            f"catalog file for {ref!r} must contain a mapping, got {type(raw).__name__}"
        )

    entry = CatalogEntry.model_validate(raw)

    # The path is the index. An entry whose declared identity disagrees with
    # its filename would be unreachable by the name it claims.
    if entry.vendor != vendor or entry.part_number != part:
        raise CatalogError(
            f"catalog file {vendor}/{part} declares itself as {entry.ref!r}. "
            "The file path is the index, so the two must agree"
        )
    return entry


def get(ref: str) -> CatalogEntry:
    """Load the entry for ``ref``, e.g. ``get("ifm:VVB020")``.

    Returns a deep copy of the cached entry. Entries are mutable models, and a
    caller appending to ``channels`` on a shared instance would quietly corrupt
    every later lookup — a copy costs microseconds and removes the whole class
    of bug.

    Raises:
        CatalogError: If the reference is malformed, the vendor is unknown, the
            part does not exist, or the file is invalid.
    """
    return _load(ref).model_copy(deep=True)


def clear_cache() -> None:
    """Forget every cached entry and the vendor-pack scan.

    For tests and for anything that installs a vendor pack at runtime.
    """
    _load.cache_clear()
    _vendor_packages.cache_clear()
