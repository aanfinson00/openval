"""CI guardrail for the Argus Telephone Road validation deal.

Pins the rows that don't depend on mid-hold rollover modeling (PBR, opex
sub-categories, Total Operating Expenses) for Y1..Y10. Rollover-driven
rows (A&T Vacancy, Free Rent, SBR, Recoveries during partial-occupancy
years, TI / LC / Capital Reserves, NOI, CFB DS, CFAD) are not pinned —
they require multi-tenant lease modeling that isn't in the schema yet.

Skips when the Argus fixture isn't present.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

VALIDATION_DIR = Path(__file__).parent.parent / "validation"
sys.path.insert(0, str(VALIDATION_DIR))

from argus_telephone_road import (  # noqa: E402
    FIXTURE_PATH,
    STABILIZED_ROWS,
    STABILIZED_YEAR_INDEXES,
    assert_matches_argus,
    pinned_drift,
)


pytestmark = pytest.mark.skipif(
    not FIXTURE_PATH.exists(),
    reason=f"Argus fixture not present at {FIXTURE_PATH}",
)


def test_telephone_road_stabilized_rows_match_argus_golden():
    """Tight pin: every Y1-Y10 cell of every STABILIZED_ROWS row stays
    within $25 of the Argus golden."""
    assert_matches_argus(tolerance=25.0)


def test_telephone_road_drift_under_50():
    """Looser ceiling that surfaces gradual erosion before tipping the
    tight $25 pin."""
    drift = pinned_drift()
    for row in STABILIZED_ROWS:
        for y_idx in STABILIZED_YEAR_INDEXES:
            v = drift.iloc[:, y_idx].loc[row]
            assert abs(v) < 50.0, (
                f"{row!r} @ {drift.columns[y_idx]} drift = ${v:,.2f}"
            )
