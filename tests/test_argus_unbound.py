"""CI guardrail for the Argus Unbound Gateway Phase I validation deal.

Runs the canonical stub property through the projector and asserts every
stabilized-year row matches the pinned Argus golden within $25. If anything
breaks the Y2..Y10 top-line parity, this test fires.

Skips when the Argus fixture isn't present so a fresh clone still runs the
full suite cleanly.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

from openval import opex_with_pct_of_revenue_fee

# validation/ isn't on sys.path by default; insert it so the harness module
# can be imported without the user installing it as a package.
VALIDATION_DIR = Path(__file__).parent.parent / "validation"
sys.path.insert(0, str(VALIDATION_DIR))

from argus_unbound import (  # noqa: E402
    ARGUS_OPEX_BY_YEAR,
    FIXTURE_PATH,
    STABILIZED_ROWS,
    STABILIZED_YEAR_INDEXES,
    assert_matches_argus,
    build_stub_property,
    pinned_drift,
)


pytestmark = pytest.mark.skipif(
    not FIXTURE_PATH.exists(),
    reason=f"Argus fixture not present at {FIXTURE_PATH}",
)


def test_unbound_stabilized_years_match_argus_golden():
    """The pin: every Y2-Y10 cell of every numeric top-line row stays
    within $25 of the Argus export."""
    assert_matches_argus(tolerance=25.0)


def test_unbound_stabilized_drift_under_50():
    """A looser ceiling that surfaces gradual erosion before it tips the
    tight $25 pin. If this fails, the tight test is about to fail too."""
    drift = pinned_drift()
    for row in STABILIZED_ROWS:
        for y_idx in STABILIZED_YEAR_INDEXES:
            assert abs(drift.iloc[:, y_idx].loc[row]) < 50.0, (
                f"{row!r} @ {drift.columns[y_idx]} drift = ${drift.iloc[:, y_idx].loc[row]:,.2f}"
            )


def test_opex_helper_reproduces_argus_opex_from_base_plus_4pct_fee():
    """End-to-end demo of ``opex_with_pct_of_revenue_fee``: given Unbound's
    base opex (Real Estate Taxes + Insurance + CAM, read off Argus) and a
    4% management fee, the converged opex matches Argus's actual Total
    Operating Expenses schedule within $20/yr for Y1..Y10.

    This is the proof that OpenVal can reproduce Argus's percentage-of-
    revenue management fee without needing a first-class fee model.
    """
    # Unbound base opex (RE Tax + Insurance + CAM), pulled from the Argus
    # fixture in this session. Source: validation/argus_unbound.py exploration.
    UNBOUND_BASE_OPEX: list[int] = [
        1_445_004, 1_488_360, 1_533_000, 1_578_996, 1_626_348, 1_675_140,
        1_725_408, 1_777_164, 1_830_480, 1_885_392, 1_941_960,
    ]
    base_opex = {2026 + i: Decimal(str(v)) for i, v in enumerate(UNBOUND_BASE_OPEX)}

    prop_template = build_stub_property().model_copy(update={"opex_annual": base_opex})
    derived = opex_with_pct_of_revenue_fee(
        base_opex, pct_of_revenue=Decimal("0.04"), prop_template=prop_template
    )

    for y_idx in range(10):  # Y1..Y10 (skip Y11 — partial year due to rollover)
        year = 2026 + y_idx
        ours = float(derived[year])
        theirs = ARGUS_OPEX_BY_YEAR[y_idx]
        assert abs(ours - theirs) < 20.0, (
            f"Y{y_idx + 1} ({year}): helper produced ${ours:,.2f}, Argus = ${theirs:,.0f} "
            f"(drift ${ours - theirs:+,.2f})"
        )
