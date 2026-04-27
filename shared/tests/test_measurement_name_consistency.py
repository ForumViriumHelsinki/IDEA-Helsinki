"""Regression guard for InfluxDB measurement-name drift across the system.

History (issue #397): four independent PRs (#29, #30, #42, #117) introduced
health checks that hardcoded measurement names that did not match what the
producer code was actually writing. The bug was masked for ~6 months because
the wrong-named checks either reported `degraded` (non-blocking) or
unconditionally `healthy` regardless of whether the query found anything.

These tests pin both invariants:
1. The constants resolve to the on-the-wire values that the producers
   `Point("segment_data")` / `measurement_name="idea_validation"` have used
   since the initial containerize commit. Renaming the constant would break
   wire compatibility with all historical data; assert the literal value.
2. None of the obsolete wrong names appears anywhere in production code.
   Three different wrong names were independently invented during the
   six-month window — guard against any of them creeping back in.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from idea_shared.lib.Constants.Constants import (
    INFLUX_FCD_MEASUREMENT,
    INFLUX_VALIDATION_MEASUREMENT,
)

# Repository root — three parents up from this file: shared/tests -> shared -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]

# Production source roots: shared library + every service. Tests are
# excluded so test fixtures can use whatever literals they need.
PRODUCTION_DIRS = (
    REPO_ROOT / "shared" / "src",
    REPO_ROOT / "services" / "orchestrator" / "src",
    REPO_ROOT / "services" / "fcd-manager" / "src",
    REPO_ROOT / "services" / "traffic-monitor" / "src",
)

# Names that have appeared in past health checks but never as actual
# measurement names in InfluxDB. If any of these turns up in production code,
# someone has introduced a fresh variant of the issue #397 bug.
OBSOLETE_NAMES = ("fcd_segment", "fcd_data", "validation_result")


def test_fcd_measurement_constant_pins_wire_value() -> None:
    """Renaming this constant would orphan all historical FCD data."""
    assert INFLUX_FCD_MEASUREMENT == "segment_data"


def test_validation_measurement_constant_pins_wire_value() -> None:
    """Renaming this constant would orphan all historical validation data."""
    assert INFLUX_VALIDATION_MEASUREMENT == "idea_validation"


def _iter_production_python_files():
    for root in PRODUCTION_DIRS:
        if not root.exists():
            continue
        yield from root.rglob("*.py")


@pytest.mark.parametrize("obsolete", OBSOLETE_NAMES)
def test_no_obsolete_measurement_names_in_production_code(obsolete: str) -> None:
    """No production source file should contain the historical wrong names.

    These three literals were introduced by past PRs as plausible-sounding
    measurement names that did not match the producer's `Point(...)` call.
    Failures here mean a new health check or query has reintroduced a
    non-matching name; use INFLUX_FCD_MEASUREMENT or
    INFLUX_VALIDATION_MEASUREMENT instead.
    """
    quoted_variants = (f'"{obsolete}"', f"'{obsolete}'")
    offenders: list[str] = []

    for path in _iter_production_python_files():
        # Skip this regression test's own copy of the names.
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        if any(variant in text for variant in quoted_variants):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert not offenders, (
        f"Obsolete measurement name {obsolete!r} found in production source files: "
        f"{offenders}. Use INFLUX_FCD_MEASUREMENT or INFLUX_VALIDATION_MEASUREMENT "
        f"from idea_shared.lib.Constants.Constants instead — see issue #397."
    )
