from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from openval import (
    ExpenseStructure,
    Lease,
    RentStep,
    project_recoveries,
)


def _lease(**overrides) -> Lease:
    defaults = dict(
        suite_id="100",
        tenant_name="Acme Co",
        area_sf=5_000,
        start_date=date(2026, 1, 1),
        end_date=date(2031, 1, 1),
        base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("36"))],
        expense_structure=ExpenseStructure.NNN,
    )
    defaults.update(overrides)
    return Lease(**defaults)


# OpEx: 5 years, $10/sf on a 50,000 sf building = $500k year 1, growing 3%/yr
PROPERTY_SF = 50_000
OPEX = pd.Series(
    {
        2026: 500_000.0,
        2027: 515_000.0,
        2028: 530_450.0,
        2029: 546_363.5,
        2030: 562_754.4,
    }
)


def test_fsg_returns_zero_recoveries():
    lease = _lease(expense_structure=ExpenseStructure.FSG)
    df = project_recoveries(
        lease,
        start=date(2026, 1, 1),
        end=date(2031, 1, 1),
        property_rentable_sf=PROPERTY_SF,
        opex_annual=OPEX,
    )
    assert (df["recovery"] == 0.0).all()


def test_nnn_pro_rata_of_opex():
    lease = _lease()  # 5,000 / 50,000 = 10% pro-rata
    df = project_recoveries(
        lease,
        start=date(2026, 1, 1),
        end=date(2031, 1, 1),
        property_rentable_sf=PROPERTY_SF,
        opex_annual=OPEX,
    )
    # Year 1: 10% * 500,000 = 50,000 / 12 = ~4,166.67
    assert df.loc["2026-06-01", "recovery"] == pytest.approx(50_000.0 / 12)
    # Year 5: 10% * 562,754.4 / 12
    assert df.loc["2030-06-01", "recovery"] == pytest.approx(562_754.4 * 0.1 / 12)


def test_mg_base_year_zero_in_base_year():
    lease = _lease(expense_structure=ExpenseStructure.MG, base_year=2026)
    df = project_recoveries(
        lease,
        start=date(2026, 1, 1),
        end=date(2031, 1, 1),
        property_rentable_sf=PROPERTY_SF,
        opex_annual=OPEX,
    )
    # Year 1 (base year): recovery == 0
    assert df.loc["2026-06-01", "recovery"] == pytest.approx(0.0)
    # Year 2: 10% * (515,000 - 500,000) = 1,500 / 12 = 125
    assert df.loc["2027-06-01", "recovery"] == pytest.approx(125.0)
    # Year 5: 10% * (562,754.4 - 500,000) = 6,275.44 / 12
    assert df.loc["2030-06-01", "recovery"] == pytest.approx((562_754.4 - 500_000.0) * 0.1 / 12)


def test_mg_base_year_floors_at_zero():
    """If OpEx drops below base year, recovery is zero, not negative."""
    declining = pd.Series({2026: 500_000.0, 2027: 480_000.0, 2028: 490_000.0, 2029: 510_000.0, 2030: 530_000.0})
    lease = _lease(expense_structure=ExpenseStructure.MG, base_year=2026)
    df = project_recoveries(
        lease,
        start=date(2026, 1, 1),
        end=date(2031, 1, 1),
        property_rentable_sf=PROPERTY_SF,
        opex_annual=declining,
    )
    assert df.loc["2027-06-01", "recovery"] == pytest.approx(0.0)
    assert df.loc["2029-06-01", "recovery"] == pytest.approx((510_000 - 500_000) * 0.1 / 12)


def test_mg_expense_stop():
    # Stop at $9/sf on 50,000 sf building -> $450k threshold
    # Year 1 OpEx: $500k. Excess: $50k. Recovery: 10% * $50k = $5k -> $416.67/mo
    lease = _lease(expense_structure=ExpenseStructure.MG, expense_stop_psf=Decimal("9"))
    df = project_recoveries(
        lease,
        start=date(2026, 1, 1),
        end=date(2031, 1, 1),
        property_rentable_sf=PROPERTY_SF,
        opex_annual=OPEX,
    )
    assert df.loc["2026-06-01", "recovery"] == pytest.approx(5_000.0 / 12)
    # Year 2: 10% * (515,000 - 450,000) = 6,500 / 12
    assert df.loc["2027-06-01", "recovery"] == pytest.approx(6_500.0 / 12)


def test_recovery_cap_limits_year_over_year_growth():
    # Cap at 3%. Year 1 NNN: $50k. Year 2 uncapped = $51,500 (3% growth, exactly at cap).
    # Make OpEx grow 10% so cap binds.
    spiky = pd.Series({2026: 500_000.0, 2027: 550_000.0, 2028: 605_000.0, 2029: 665_500.0, 2030: 732_050.0})
    lease = _lease(recovery_cap_pct=Decimal("0.03"))
    df = project_recoveries(
        lease,
        start=date(2026, 1, 1),
        end=date(2031, 1, 1),
        property_rentable_sf=PROPERTY_SF,
        opex_annual=spiky,
    )
    # Year 1: 50,000 (uncapped, no prior)
    assert df.loc["2026-06-01", "recovery"] * 12 == pytest.approx(50_000.0)
    # Year 2: capped at 50,000 * 1.03 = 51,500 (uncapped would be 55,000)
    assert df.loc["2027-06-01", "recovery"] * 12 == pytest.approx(51_500.0)
    # Year 3: capped at 51,500 * 1.03 = 53,045 (uncapped: 60,500)
    assert df.loc["2028-06-01", "recovery"] * 12 == pytest.approx(53_045.0)


def test_recovery_zero_outside_lease_term():
    lease = _lease(start_date=date(2027, 1, 1), end_date=date(2030, 1, 1),
                   base_rent_steps=[RentStep(start_date=date(2027, 1, 1), annual_psf=Decimal("36"))])
    df = project_recoveries(
        lease,
        start=date(2026, 1, 1),
        end=date(2031, 1, 1),
        property_rentable_sf=PROPERTY_SF,
        opex_annual=OPEX,
    )
    assert df.loc["2026-06-01", "recovery"] == 0.0
    assert df.loc["2030-06-01", "recovery"] == 0.0
    assert df.loc["2028-06-01", "recovery"] > 0.0


def test_lease_larger_than_building_rejected():
    lease = _lease(area_sf=60_000)  # bigger than building
    with pytest.raises(ValueError, match="exceeds property"):
        project_recoveries(
            lease,
            start=date(2026, 1, 1),
            end=date(2031, 1, 1),
            property_rentable_sf=PROPERTY_SF,
            opex_annual=OPEX,
        )


def test_mg_base_year_missing_from_schedule_rejected():
    lease = _lease(expense_structure=ExpenseStructure.MG, base_year=2025)  # not in opex
    with pytest.raises(ValueError, match="base_year"):
        project_recoveries(
            lease,
            start=date(2026, 1, 1),
            end=date(2031, 1, 1),
            property_rentable_sf=PROPERTY_SF,
            opex_annual=OPEX,
        )
