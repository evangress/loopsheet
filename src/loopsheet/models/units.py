"""Engineering units as validated strings.

Core carries units as **strings**, not quantity objects: ``unit="mm/s"``.
``pint`` drags in flexcache / flexparser / platformdirs and would raise the
Python floor, so it lives behind the ``[units]`` extra (PLAN.md §3.4).

What core *does* provide is a closed vocabulary, so that a typo like ``"mm/S"``
or ``"degC"`` fails at load time rather than silently producing a channel whose
unit nothing downstream recognises.

The set is deliberately small and grows by pull request. Adding a unit is a
one-line change; inventing one at authoring time is not possible.
"""

from __future__ import annotations

from typing import Annotated, Final

from pydantic import AfterValidator, Field

#: Units accepted anywhere loopsheet takes a `unit` field.
#:
#: Spellings are the SI/UCUM-flavoured ones that appear on the datasheets this
#: package transcribes — note ``m/s²`` with a superscript, as ifm prints it.
#: ASCII aliases are normalised to these by :func:`normalize_unit`.
KNOWN_UNITS: Final[frozenset[str]] = frozenset(
    {
        # dimensionless
        "",  # explicitly unitless (crest factor, ratios) — distinct from None
        "%",
        "ppm",
        # vibration / motion
        "m/s",
        "mm/s",
        "inch/s",
        "m/s²",
        "g",
        "mg",
        "µm",
        "mm",
        "m",
        # rotation
        "rpm",
        "Hz",
        "kHz",
        "rad/s",
        # temperature
        "°C",
        "°F",
        "K",
        # electrical
        "V",
        "mV",
        "A",
        "mA",
        "W",
        "kW",
        "Ohm",
        # pressure / flow / level
        "Pa",
        "kPa",
        "bar",
        "mbar",
        "psi",
        "l/min",
        "m³/h",
        "l",
        # time
        "s",
        "ms",
        "µs",
        "h",
        # other
        "dB",
        "count",
    }
)

#: ASCII / vendor spellings mapped onto the canonical entry in KNOWN_UNITS.
#: Keyboards and CSV exports lose the superscripts and degree signs; accepting
#: the lossy spelling and normalising it is friendlier than rejecting it, and
#: still leaves exactly one canonical form in the model.
_UNIT_ALIASES: Final[dict[str, str]] = {
    "m/s2": "m/s²",
    "m/s^2": "m/s²",
    "mps2": "m/s²",
    "degC": "°C",
    "C": "°C",
    "degF": "°F",
    "F": "°F",
    "um": "µm",
    "us": "µs",
    "ohm": "Ohm",
    "m3/h": "m³/h",
    "lpm": "l/min",
    "none": "",
    "-": "",
}


def normalize_unit(unit: str) -> str:
    """Return the canonical spelling of ``unit``.

    Raises :class:`ValueError` if the unit is not in :data:`KNOWN_UNITS` after
    alias resolution.
    """
    candidate = _UNIT_ALIASES.get(unit.strip(), unit.strip())
    if candidate not in KNOWN_UNITS:
        raise ValueError(
            f"unknown unit {unit!r}. Known units: {', '.join(sorted(u for u in KNOWN_UNITS if u))}"
        )
    return candidate


#: A validated engineering unit, normalised to its canonical spelling.
#:
#: ``None`` (on an optional field) means "no unit declared"; the empty string
#: means "explicitly dimensionless". The crest factor is dimensionless, an
#: unconfigured channel is unknown, and conflating the two loses information.
Unit = Annotated[
    str,
    AfterValidator(normalize_unit),
    Field(description="Engineering unit, e.g. 'mm/s'. Validated against KNOWN_UNITS."),
]
