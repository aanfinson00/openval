"""Tests for Market Leasing Assumptions (MLA) on lease rollover."""

from datetime import date
from decimal import Decimal

import pytest

from openval import (
    ExpenseStructure,
    Lease,
    MarketLeasingAssumption,
    Property,
    RentStep,
    project_property,
    project_rent_roll,
)
from openval.cashflow import expand_with_mla


def _short_lease_with_mla(
    *,
    renewal_probability=Decimal("0"),
    downtime_months=0,
    market_rent_psf=Decimal("30"),
    market_rent_growth_pct=Decimal("0"),
    free_rent_new=0,
    free_rent_renewal=0,
    ti_new=Decimal("0"),
    ti_renewal=Decimal("0"),
    lc_new=Decimal("0"),
    lc_renewal=Decimal("0"),
    renewal_discount=Decimal("0"),
    new_term_months=24,
    expense_structure=ExpenseStructure.NNN,
) -> Lease:
    mla = MarketLeasingAssumption(
        market_rent_psf=market_rent_psf,
        market_rent_growth_pct=market_rent_growth_pct,
        new_term_months=new_term_months,
        free_rent_months_new=free_rent_new,
        free_rent_months_renewal=free_rent_renewal,
        ti_psf_new=ti_new,
        ti_psf_renewal=ti_renewal,
        lc_pct_new=lc_new,
        lc_pct_renewal=lc_renewal,
        renewal_probability=renewal_probability,
        downtime_months_new=downtime_months,
        renewal_market_discount_pct=renewal_discount,
        expense_structure=expense_structure,
    )
    return Lease(
        suite_id="100",
        tenant_name="Acme",
        area_sf=10_000,
        start_date=date(2026, 1, 1),
        end_date=date(2028, 1, 1),  # 2-year lease, expires mid-hold
        base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("28.00"))],
        expense_structure=ExpenseStructure.NNN,
        market_leasing_assumption=mla,
    )


def test_expand_without_mla_returns_single_segment():
    lease = Lease(
        suite_id="A",
        tenant_name="X",
        area_sf=1_000,
        start_date=date(2026, 1, 1),
        end_date=date(2031, 1, 1),
        base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("20"))],
        expense_structure=ExpenseStructure.NNN,
    )
    segments = expand_with_mla(lease, projection_end=date(2031, 1, 1))
    assert len(segments) == 1
    assert segments[0].weight == 1.0
    assert segments[0].lease is lease


def test_expand_with_mla_pure_new_branch_has_two_segments():
    """renewal_probability=0 → all weight on new branch (single chain)."""
    lease = _short_lease_with_mla(renewal_probability=Decimal("0"))
    segments = expand_with_mla(lease, projection_end=date(2030, 1, 1))
    # Original (weight 1) + new-tenant branch (weight 1) extending to 2030
    weights = [s.weight for s in segments]
    assert pytest.approx(sum(weights), abs=1e-9) == pytest.approx(2.0)  # original + 1 rollover
    assert all(s.lease.suite_id in ("100", "100-new") for s in segments)


def test_expand_with_mla_pure_renewal_branch():
    """renewal_probability=1 → all weight on renewal branch."""
    lease = _short_lease_with_mla(renewal_probability=Decimal("1"))
    segments = expand_with_mla(lease, projection_end=date(2030, 1, 1))
    suite_ids = [s.lease.suite_id for s in segments]
    assert "100-renew" in suite_ids
    assert "100-new" not in suite_ids


def test_expand_with_mla_blended_50_50_weights_sum_to_two_branches():
    """50/50 blend → original (1.0) + two children whose weights sum to 1.0."""
    lease = _short_lease_with_mla(renewal_probability=Decimal("0.5"))
    segments = expand_with_mla(lease, projection_end=date(2029, 1, 1))
    original_segments = [s for s in segments if s.lease.suite_id == "100"]
    child_segments = [s for s in segments if s.lease.suite_id != "100"]
    assert sum(s.weight for s in original_segments) == pytest.approx(1.0)
    assert sum(s.weight for s in child_segments) == pytest.approx(1.0)


def test_rent_during_original_term_unchanged_by_mla():
    """MLA must not bleed back into the parent lease's own term."""
    lease_no_mla = _short_lease_with_mla(renewal_probability=Decimal("0"))
    lease_no_mla = Lease(
        **{**lease_no_mla.model_dump(), "market_leasing_assumption": None}
    )
    with_mla = _short_lease_with_mla(renewal_probability=Decimal("0.5"))

    rr_a = project_rent_roll([lease_no_mla], date(2026, 1, 1), date(2028, 1, 1))
    rr_b = project_rent_roll([with_mla], date(2026, 1, 1), date(2028, 1, 1))
    # Within the original term, rent and TI/LC should match exactly.
    pd_assert_equal = lambda a, b: a.equals(b)
    assert pd_assert_equal(rr_a["base_rent"], rr_b["base_rent"])


def test_blended_rent_equals_probability_weighted_average():
    """50/50 blend's rent = 0.5*new + 0.5*renewal during the rollover slot."""
    lease_50_50 = _short_lease_with_mla(
        renewal_probability=Decimal("0.5"),
        renewal_discount=Decimal("0.1"),  # renewal pays 90% of market
        market_rent_psf=Decimal("30"),
    )
    rr = project_rent_roll([lease_50_50], date(2026, 1, 1), date(2029, 1, 1))

    # First month after original lease ends: Jan 2028.
    # New tenant (weight 0.5) pays 30 psf
    # Renewal tenant (weight 0.5) pays 30 * 0.9 = 27 psf
    # Blended: 0.5*30 + 0.5*27 = 28.5 psf
    # Monthly base: 28.5 * 10000 / 12 = 23,750
    feb_2028 = rr.loc["2028-01-01"]
    assert feb_2028["base_rent"] == pytest.approx(23_750.0, rel=1e-6)


def test_downtime_reduces_new_tenant_rent_in_first_months():
    """Downtime applies only to new branch; renewal continues immediately."""
    # 50/50 blend, 6-month downtime on new. Renewal continues immediately.
    lease = _short_lease_with_mla(
        renewal_probability=Decimal("0.5"),
        downtime_months=6,
        market_rent_psf=Decimal("30"),
    )
    rr = project_rent_roll([lease], date(2026, 1, 1), date(2029, 1, 1))

    # Jan 2028 (immediately after lease ends): renewal contributes (weight 0.5 × 30 psf),
    # new branch is in downtime → contributes 0. So blended rent = 0.5 * 30 * 10000 / 12 = 12,500.
    assert rr.loc["2028-01-01", "base_rent"] == pytest.approx(12_500.0, rel=1e-6)
    # July 2028 (after downtime): both branches paying → blended rent = 0.5*30 + 0.5*30 = 30 psf full.
    assert rr.loc["2028-07-01", "base_rent"] == pytest.approx(25_000.0, rel=1e-6)


def test_free_rent_applied_on_new_tenant_branch():
    """Free rent on new tenant reduces collected rent during free-rent window."""
    lease = _short_lease_with_mla(
        renewal_probability=Decimal("0"),  # 100% new tenant
        free_rent_new=3,
        market_rent_psf=Decimal("30"),
    )
    rr = project_rent_roll([lease], date(2026, 1, 1), date(2029, 1, 1))
    # New tenant starts Jan 2028 with 3 months free.
    # base_rent shows gross rent; free_rent_abatement is the offset.
    jan = rr.loc["2028-01-01"]
    assert jan["base_rent"] == pytest.approx(25_000.0, rel=1e-6)  # 30 * 10000/12
    assert jan["free_rent_abatement"] == pytest.approx(-25_000.0, rel=1e-6)
    # net_rent for the abated month should be 0.
    assert (jan["base_rent"] + jan["free_rent_abatement"]) == pytest.approx(0.0, abs=1e-6)


def test_ti_and_lc_at_rollover_commencement():
    """TI and LC outlays land at the new lease's commencement month."""
    lease = _short_lease_with_mla(
        renewal_probability=Decimal("0"),
        ti_new=Decimal("25"),  # $25/sf TI
        lc_new=Decimal("0.06"),  # 6% LC on first-year rent
        market_rent_psf=Decimal("30"),
    )
    rr = project_rent_roll([lease], date(2026, 1, 1), date(2029, 1, 1))
    jan_2028 = rr.loc["2028-01-01"]
    assert jan_2028["ti"] == pytest.approx(-25 * 10_000, rel=1e-6)
    # First-year rent for new tenant: 30 * 10000 = 300,000. LC = 6% = 18,000.
    assert jan_2028["lc"] == pytest.approx(-18_000.0, rel=1e-6)


def test_market_rent_growth_compounded_to_rollover_start():
    """5% annual growth × 2 years from origin = market rent at rollover."""
    lease = _short_lease_with_mla(
        renewal_probability=Decimal("0"),
        market_rent_psf=Decimal("30"),
        market_rent_growth_pct=Decimal("0.05"),
    )
    rr = project_rent_roll([lease], date(2026, 1, 1), date(2029, 1, 1))
    # Rollover at Jan 2028 = 2 years from origin → 30 * 1.05^2 = 33.075 psf.
    expected_monthly = 33.075 * 10_000 / 12
    assert rr.loc["2028-01-01", "base_rent"] == pytest.approx(expected_monthly, rel=1e-3)


def test_chained_rollovers_inside_long_hold():
    """5-year hold + 2-yr original + 2-yr new term should produce TWO rollovers."""
    lease = _short_lease_with_mla(
        renewal_probability=Decimal("0"),
        new_term_months=24,
        market_rent_psf=Decimal("30"),
    )
    # Project through 2032 (6 years from origin) — original (26-28), rollover 1 (28-30), rollover 2 (30-32).
    segments = expand_with_mla(lease, projection_end=date(2032, 1, 1))
    suite_ids = [s.lease.suite_id for s in segments]
    # Original + child + grandchild (all "new" branch on 100% new tenant case).
    assert "100" in suite_ids
    assert "100-new" in suite_ids
    assert "100-new-new" in suite_ids


def test_property_projection_with_mla_runs():
    """End-to-end: project_property accepts a lease with MLA and produces numbers."""
    lease = _short_lease_with_mla(
        renewal_probability=Decimal("0.6"),
        market_rent_psf=Decimal("32"),
        market_rent_growth_pct=Decimal("0.03"),
        free_rent_new=2,
        ti_new=Decimal("20"),
        lc_new=Decimal("0.05"),
        downtime_months=3,
    )
    prop = Property(
        name="Rollover Building",
        rentable_sf=10_000,
        leases=[lease],
        opex_annual={
            2026: Decimal("100000"),
            2027: Decimal("103000"),
            2028: Decimal("106090"),
            2029: Decimal("109273"),
            2030: Decimal("112551"),
        },
        acquisition_date=date(2026, 1, 1),
        acquisition_price=Decimal("4000000"),
        hold_years=5,
        exit_cap_rate=Decimal("0.07"),
    )
    result = project_property(prop)
    cf = result.cashflows

    # Year 1 (original lease in place): gross rent = 28 * 10000 = 280,000.
    assert cf.loc["2026-01-01":"2026-12-31", "gross_rent"].sum() == pytest.approx(
        280_000.0, rel=1e-6
    )

    # Year 3 (rollover year): blended gross rent reflects the 60/40 weighting.
    year_3_rent = cf.loc["2028-01-01":"2028-12-31", "gross_rent"].sum()
    assert year_3_rent > 0
    # NOI is non-zero across the hold period (no unexpected gaps).
    assert (cf["noi"] != 0).all()

    # IRR computes.
    assert result.unlevered_irr is not None
    assert result.unlevered_irr > 0
