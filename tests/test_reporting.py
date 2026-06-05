"""Tests for the reporting helpers (mark-to-market, rent roll summary,
Argus-style top-line income block).
"""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from openval import (
    ARGUS_CASHFLOW_ROWS,
    ARGUS_TOP_LINE_ROWS,
    ExpenseStructure,
    Lease,
    Loan,
    MarketLeasingAssumption,
    Property,
    RentStep,
    argus_cashflow_report,
    argus_top_line_income,
    mark_to_market,
    project_property,
    rent_roll_summary,
)


def _mla(market_psf: float = 30.0, growth: float = 0.0) -> MarketLeasingAssumption:
    return MarketLeasingAssumption(
        market_rent_psf=Decimal(str(market_psf)),
        market_rent_growth_pct=Decimal(str(growth)),
        new_term_months=60,
    )


def _lease(suite="A", psf=Decimal("32"), area=50_000, mla=None) -> Lease:
    return Lease(
        suite_id=suite,
        tenant_name=f"Tenant {suite}",
        area_sf=area,
        start_date=date(2026, 1, 1),
        end_date=date(2031, 1, 1),
        base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=psf)],
        expense_structure=ExpenseStructure.NNN,
        market_leasing_assumption=mla,
    )


def _prop(leases) -> Property:
    return Property(
        name="Test",
        rentable_sf=200_000,
        leases=leases,
        opex_annual={2026: Decimal("500000")},
        acquisition_date=date(2026, 1, 1),
        acquisition_price=Decimal("20000000"),
        hold_years=5,
        exit_cap_rate=Decimal("0.07"),
    )


def test_mark_to_market_over_market():
    """Lease at $32 PSF vs market $30 → over-market by $2."""
    prop = _prop([_lease(psf=Decimal("32"), mla=_mla(30.0))])
    mtm = mark_to_market(prop)
    row = mtm.iloc[0]
    assert row["in_place_psf"] == pytest.approx(32.0)
    assert row["market_psf"] == pytest.approx(30.0)
    assert row["delta_psf"] == pytest.approx(2.0)
    assert row["mtm_tag"] == "over"
    assert row["annual_delta_dollars"] == pytest.approx(100_000)


def test_mark_to_market_under_market():
    """Lease at $25 PSF vs market $30 → under-market."""
    prop = _prop([_lease(psf=Decimal("25"), mla=_mla(30.0))])
    mtm = mark_to_market(prop)
    row = mtm.iloc[0]
    assert row["delta_psf"] == pytest.approx(-5.0)
    assert row["mtm_tag"] == "under"


def test_mark_to_market_growth_applied_at_as_of_date():
    """Market rent grows from origin to as_of: $30 × 1.03^2 ≈ $31.83."""
    prop = _prop([_lease(psf=Decimal("32"), mla=_mla(30.0, growth=0.03))])
    mtm = mark_to_market(prop, as_of=date(2028, 1, 1))
    assert mtm.iloc[0]["market_psf"] == pytest.approx(31.827, abs=1e-2)


def test_mark_to_market_no_mla_flagged():
    """Leases without MLA still appear in MTM but market columns are blank."""
    prop = _prop([_lease(mla=None)])
    mtm = mark_to_market(prop)
    row = mtm.iloc[0]
    assert row["market_psf"] is None
    assert row["mtm_tag"] == "no MLA"


def test_rent_roll_summary_columns_and_values():
    prop = _prop([_lease(suite="A", psf=Decimal("32"), area=60_000)])
    rr = rent_roll_summary(prop)
    row = rr.iloc[0]
    assert row["suite_id"] == "A"
    assert row["area_sf"] == 60_000
    assert row["term_months"] == 60
    assert row["annual_rent"] == pytest.approx(60_000 * 32)
    assert row["expense_structure"] == "NNN"


# ----------------------------------------------------------------------
# argus_top_line_income
# ----------------------------------------------------------------------


def test_argus_top_line_income_row_order_matches_argus():
    """The reporter's row index mirrors openval.io.argus_cashflow's exact
    label order so it can be diff'd against a real Argus export.
    """
    from openval.io import TOP_LINE_INCOME_ROWS as IO_ROWS

    assert ARGUS_TOP_LINE_ROWS == IO_ROWS


def test_argus_top_line_income_returns_16_rows_and_fiscal_year_cols():
    prop = _prop([_lease()])
    result = project_property(prop)
    tli = argus_top_line_income(result, prop)
    assert tuple(tli.index) == ARGUS_TOP_LINE_ROWS
    assert list(tli.columns) == [f"Year {i}" for i in range(1, 6)]


def test_argus_top_line_income_section_headers_are_nan():
    prop = _prop([_lease()])
    result = project_property(prop)
    tli = argus_top_line_income(result, prop)
    for header in ("Rental Revenue", "Other Tenant Revenue", "Vacancy & Credit Loss"):
        assert tli.loc[header].isna().all(), f"{header} should be a label-only row"


def test_argus_identities_hold_on_top_line_block():
    """Reproduce Argus's accounting identities on an OpenVal projection:

      Scheduled Base Rent      = Potential Base Rent + A&T Vacancy + Free Rent
      Total Rental Revenue     = Scheduled Base Rent
      Total Tenant Revenue     = Total Rental Revenue + Total Other Tenant Rev
      Potential Gross Revenue  = Total Tenant Revenue
      Effective Gross Revenue  = Potential Gross Revenue + Total V&C Loss
    """
    prop = _prop([_lease()])
    result = project_property(prop)
    tli = argus_top_line_income(result, prop)

    sbr_derived = (
        tli.loc["  Potential Base Rent"]
        + tli.loc["  Absorption & Turnover Vacancy"]
        + tli.loc["  Free Rent"]
    )
    pd.testing.assert_series_equal(
        tli.loc["  Scheduled Base Rent"].rename(None),
        sbr_derived.rename(None),
        atol=1.0,
    )
    pd.testing.assert_series_equal(
        tli.loc["Total Rental Revenue"].rename(None),
        tli.loc["  Scheduled Base Rent"].rename(None),
        atol=1.0,
    )
    pd.testing.assert_series_equal(
        tli.loc["Total Tenant Revenue"].rename(None),
        (tli.loc["Total Rental Revenue"] + tli.loc["Total Other Tenant Revenue"]).rename(None),
        atol=1.0,
    )
    pd.testing.assert_series_equal(
        tli.loc["Potential Gross Revenue"].rename(None),
        tli.loc["Total Tenant Revenue"].rename(None),
        atol=1.0,
    )
    pd.testing.assert_series_equal(
        tli.loc["Effective Gross Revenue"].rename(None),
        (tli.loc["Potential Gross Revenue"] + tli.loc["Total Vacancy & Credit Loss"]).rename(None),
        atol=1.0,
    )


def test_at_market_lease_with_no_free_rent_has_zero_vacancy_and_free_rent():
    """Lease starts at acquisition, no free rent, MLA renews → A&T Vacancy
    and Free Rent are both $0 for the whole hold."""
    prop = _prop([_lease(mla=_mla(market_psf=32.0))])
    result = project_property(prop)
    tli = argus_top_line_income(result, prop)
    assert (tli.loc["  Absorption & Turnover Vacancy"].abs() < 1.0).all()
    assert (tli.loc["  Free Rent"].abs() < 1.0).all()


def test_free_rent_shows_up_as_negative_line():
    """3-month free rent on a $32 PSF × 50k SF lease ⇒ Y1 Free Rent = −$400k."""
    lease = Lease(
        suite_id="A",
        tenant_name="Tenant",
        area_sf=50_000,
        start_date=date(2026, 1, 1),
        end_date=date(2031, 1, 1),
        base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("32"))],
        free_rent_months=3,
        expense_structure=ExpenseStructure.NNN,
        market_leasing_assumption=_mla(market_psf=32.0),
    )
    prop = _prop([lease])
    result = project_property(prop)
    tli = argus_top_line_income(result, prop)
    # 3 months × $32 × 50,000 / 12 = $400,000
    assert tli.loc["  Free Rent", "Year 1"] == pytest.approx(-400_000, abs=1.0)


def test_monthly_frequency_returns_monthly_grid():
    prop = _prop([_lease()])
    result = project_property(prop)
    tli_m = argus_top_line_income(result, prop, frequency="monthly")
    # 5-yr hold = 60 months
    assert tli_m.shape == (16, 60)
    assert isinstance(tli_m.columns, pd.DatetimeIndex)


def test_invalid_frequency_raises():
    prop = _prop([_lease()])
    result = project_property(prop)
    with pytest.raises(ValueError):
        argus_top_line_income(result, prop, frequency="quarterly")


# ----------------------------------------------------------------------
# argus_cashflow_report — full block (top-line + opex + leasing + capex + NCF)
# ----------------------------------------------------------------------


def test_full_report_returns_34_rows():
    prop = _prop([_lease()])
    result = project_property(prop)
    report = argus_cashflow_report(result, prop)
    assert tuple(report.index) == ARGUS_CASHFLOW_ROWS
    assert report.shape[0] == 34


def test_full_report_top_16_rows_match_top_line_income():
    """The full report's first 16 rows are the top-line income block,
    unchanged from ``argus_top_line_income``. Lets us evolve the lower
    block without disturbing the income contract."""
    prop = _prop([_lease()])
    result = project_property(prop)
    top = argus_top_line_income(result, prop)
    full = argus_cashflow_report(result, prop)
    pd.testing.assert_frame_equal(full.loc[list(top.index)], top, atol=1.0)


def test_opex_shows_positive_in_argus_convention():
    """Engine stores opex as negative; the report flips it to positive
    so the layout matches Argus (costs presented positive in cost section)."""
    prop_template = _prop([_lease()])
    # Override the single-year opex from _prop with a full 5-yr schedule
    # so every year of the report has opex to flip.
    prop = prop_template.model_copy(
        update={"opex_annual": {y: Decimal("500000") for y in range(2026, 2031)}}
    )
    result = project_property(prop)
    report = argus_cashflow_report(result, prop)
    assert (report.loc["Total Operating Expenses"] > 0).all()


def test_noi_equals_egr_minus_total_opex():
    prop = _prop([_lease()])
    result = project_property(prop)
    report = argus_cashflow_report(result, prop)
    derived = (
        report.loc["Effective Gross Revenue"]
        - report.loc["Total Operating Expenses"]
    )
    pd.testing.assert_series_equal(
        report.loc["Net Operating Income"].rename(None),
        derived.rename(None),
        atol=1.0,
    )


def test_cash_flow_before_debt_service_equals_noi_minus_leasing_and_capital():
    prop = _prop([_lease()])
    result = project_property(prop)
    report = argus_cashflow_report(result, prop)
    derived = (
        report.loc["Net Operating Income"]
        - report.loc["Total Leasing & Capital Costs"]
    )
    pd.testing.assert_series_equal(
        report.loc["Cash Flow Before Debt Service"].rename(None),
        derived.rename(None),
        atol=1.0,
    )


def test_total_leasing_costs_equals_ti_plus_lc():
    # Lease with TI / LC so the rows are nonzero.
    lease = Lease(
        suite_id="A",
        tenant_name="T",
        area_sf=50_000,
        start_date=date(2026, 1, 1),
        end_date=date(2031, 1, 1),
        base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("32"))],
        ti_psf=Decimal("15"),
        lc_pct_first_year_rent=Decimal("0.05"),
        expense_structure=ExpenseStructure.NNN,
    )
    prop = _prop([lease])
    result = project_property(prop)
    report = argus_cashflow_report(result, prop)
    derived = report.loc["  Tenant Improvements"] + report.loc["  Leasing Commissions"]
    pd.testing.assert_series_equal(
        report.loc["  Total Leasing Costs"].rename(None),
        derived.rename(None),
        atol=1.0,
    )


def test_cash_flow_available_for_distribution_matches_cfb_when_no_loan():
    """Without debt, CFAD == Cash Flow Before Debt Service."""
    prop = _prop([_lease()])
    result = project_property(prop)
    report = argus_cashflow_report(result, prop)
    pd.testing.assert_series_equal(
        report.loc["Cash Flow Available for Distribution"].rename(None),
        report.loc["Cash Flow Before Debt Service"].rename(None),
        atol=1.0,
    )


def test_cash_flow_available_for_distribution_is_cfb_minus_debt_service_with_loan():
    loan = Loan(
        principal=Decimal("5_000_000"),
        rate_annual=Decimal("0.05"),
        amortization_years=30,
        term_years=10,
    )
    prop_template = _prop([_lease()])
    prop = prop_template.model_copy(update={"loan": loan})
    result = project_property(prop)
    report = argus_cashflow_report(result, prop)
    # With a loan, CFAD strictly less than CFB by the debt service amount.
    cfb = report.loc["Cash Flow Before Debt Service"]
    cfad = report.loc["Cash Flow Available for Distribution"]
    assert (cfb > cfad).all()


def test_opex_categories_populate_argus_sub_rows():
    """When ``Property.opex_categories`` is set, the 4 Argus opex sub-rows
    pick up the values; the totals still match Total Operating Expenses."""
    categories = {
        "Real Estate Taxes":         {2026: Decimal("300000"), 2027: Decimal("309000"),
                                      2028: Decimal("318270"), 2029: Decimal("327818"),
                                      2030: Decimal("337653")},
        "Insurance":                 {y: Decimal("50000") for y in range(2026, 2031)},
        "Property Management Fee":   {y: Decimal("75000") for y in range(2026, 2031)},
        "CAM":                       {y: Decimal("75000") for y in range(2026, 2031)},
    }
    prop_template = _prop([_lease()])
    prop = prop_template.model_copy(
        update={"opex_categories": categories, "opex_annual": {}}
    )
    # Re-construct so the derive-from-categories validator runs.
    prop = Property(**prop.model_dump())
    result = project_property(prop)
    report = argus_cashflow_report(result, prop)
    for argus_label, cat_name in (
        ("  Real Estate Taxes", "Real Estate Taxes"),
        ("  Insurance", "Insurance"),
        ("  Property Management Fee", "Property Management Fee"),
        ("  CAM", "CAM"),
    ):
        assert not report.loc[argus_label].isna().any(), f"{argus_label} should be populated"
        assert report.loc[argus_label, "Year 1"] == pytest.approx(
            float(categories[cat_name][2026]), abs=1.0
        )
    derived = sum(report.loc[r] for r in (
        "  Real Estate Taxes", "  Insurance", "  Property Management Fee", "  CAM"
    ))
    pd.testing.assert_series_equal(
        report.loc["Total Operating Expenses"].rename(None),
        derived.rename(None),
        atol=1.0,
    )


def test_opex_categories_derives_opex_annual_when_not_provided():
    categories = {
        "Real Estate Taxes": {2026: Decimal("100000")},
        "Insurance":         {2026: Decimal("25000")},
    }
    prop_template = _prop([_lease()])
    # Build via model_dump roundtrip so the before-validator fires.
    data = prop_template.model_dump()
    data["opex_categories"] = categories
    data["opex_annual"] = {}  # let the validator populate
    prop = Property(**data)
    assert prop.opex_annual[2026] == Decimal("125000")


def test_opex_categories_consistency_check_raises_on_mismatch():
    categories = {"Real Estate Taxes": {2026: Decimal("100000")}}
    prop_template = _prop([_lease()])
    data = prop_template.model_dump()
    data["opex_categories"] = categories
    data["opex_annual"] = {2026: Decimal("999999")}  # disagrees with categories
    with pytest.raises(Exception, match="disagrees with sum"):
        Property(**data)


def test_opex_categories_absent_keeps_existing_behavior():
    """Without categories, the 4 Argus opex sub-rows stay NaN."""
    prop = _prop([_lease()])
    result = project_property(prop)
    report = argus_cashflow_report(result, prop)
    for sub in ("  Real Estate Taxes", "  Insurance",
                "  Property Management Fee", "  CAM"):
        assert report.loc[sub].isna().all()


def test_capex_categories_populate_argus_sub_rows():
    capex_cats = {
        "Capital Reserves": {y: Decimal("25000") for y in range(2026, 2031)},
        "Non-Leasing Capital Expense": {2026: Decimal("500000")},
    }
    prop_template = _prop([_lease()])
    data = prop_template.model_dump()
    data["capex_categories"] = capex_cats
    data["capex_annual"] = {}  # let validator populate
    prop = Property(**data)
    result = project_property(prop)
    report = argus_cashflow_report(result, prop)
    assert report.loc["  Capital Reserves", "Year 1"] == pytest.approx(25_000, abs=1.0)
    assert report.loc["  Non-Leasing Capital Expense", "Year 1"] == pytest.approx(500_000, abs=1.0)
    # Reserves continue Y2..Y5, NLCapex drops to 0 after Y1
    assert report.loc["  Capital Reserves", "Year 5"] == pytest.approx(25_000, abs=1.0)
    assert report.loc["  Non-Leasing Capital Expense", "Year 5"] == pytest.approx(0, abs=1.0)


def test_capex_categories_derives_capex_annual_when_not_provided():
    capex_cats = {
        "Capital Reserves":            {2026: Decimal("10000")},
        "Non-Leasing Capital Expense": {2026: Decimal("90000")},
    }
    prop_template = _prop([_lease()])
    data = prop_template.model_dump()
    data["capex_categories"] = capex_cats
    data["capex_annual"] = {}
    prop = Property(**data)
    assert prop.capex_annual[2026] == Decimal("100000")


def test_capex_categories_consistency_check_raises_on_mismatch():
    capex_cats = {"Capital Reserves": {2026: Decimal("10000")}}
    prop_template = _prop([_lease()])
    data = prop_template.model_dump()
    data["capex_categories"] = capex_cats
    data["capex_annual"] = {2026: Decimal("999999")}
    with pytest.raises(Exception, match="disagrees with sum"):
        Property(**data)


def test_capex_categories_absent_defaults_to_non_leasing_lump():
    """Without capex_categories, full capex falls into 'Non-Leasing Capital
    Expense' (so single-bucket users still see their capex displayed)."""
    prop_template = _prop([_lease()])
    prop = prop_template.model_copy(
        update={"capex_annual": {2027: Decimal("150000")}}
    )
    result = project_property(prop)
    report = argus_cashflow_report(result, prop)
    assert report.loc["  Non-Leasing Capital Expense", "Year 2"] == pytest.approx(
        150_000, abs=1.0
    )
    assert report.loc["  Capital Reserves"].isna().all()


def test_full_report_section_headers_and_unsupported_subrows_are_nan():
    prop = _prop([_lease()])
    result = project_property(prop)
    report = argus_cashflow_report(result, prop)
    nan_rows = (
        # section headers
        "Rental Revenue", "Other Tenant Revenue", "Vacancy & Credit Loss",
        "Operating Expenses", "Leasing Costs", "Capital Expenditures",
        # opex sub-categories (Phase B)
        "  Real Estate Taxes", "  Insurance", "  Property Management Fee", "  CAM",
        # capex sub-category (Phase B)
        "  Capital Reserves",
    )
    for r in nan_rows:
        assert report.loc[r].isna().all(), f"{r} should be NaN"


def test_full_report_monthly_frequency_returns_correct_shape():
    prop = _prop([_lease()])
    result = project_property(prop)
    monthly = argus_cashflow_report(result, prop, frequency="monthly")
    assert monthly.shape == (34, 60)  # 5-yr hold = 60 months


def test_full_report_invalid_frequency_raises():
    prop = _prop([_lease()])
    result = project_property(prop)
    with pytest.raises(ValueError):
        argus_cashflow_report(result, prop, frequency="quarterly")


# ----------------------------------------------------------------------


def test_pbr_uses_full_market_rate_ignoring_renewal_discount():
    """Argus's PBR is the gross potential at the new-tenant rate (no
    renewal haircut). Earlier versions used the discounted renewal rate
    and produced positive A&T Vacancy in stabilized post-rollover years
    — which is definitionally wrong. This test pins the correct behavior.

    Setup: 2-yr lease expiring inside the hold + MLA with renewal at 50%
    of market. The post-expiration PBR should reflect the full market
    rate, not 50%.
    """
    mla = MarketLeasingAssumption(
        market_rent_psf=Decimal("30"),
        market_rent_growth_pct=Decimal("0"),
        new_term_months=60,
        rent_escalation_pct=Decimal("0"),
        renewal_probability=Decimal("0.50"),
        renewal_market_discount_pct=Decimal("0.50"),  # 50% off — extreme to surface drift
        downtime_months_new=0,
    )
    lease = Lease(
        suite_id="A",
        tenant_name="Tenant",
        area_sf=10_000,
        start_date=date(2026, 1, 1),
        end_date=date(2028, 1, 1),  # rolls in Y3
        base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("30"))],
        expense_structure=ExpenseStructure.NNN,
        market_leasing_assumption=mla,
    )
    prop = _prop([lease])
    result = project_property(prop)
    tli = argus_top_line_income(result, prop)
    # Post-rollover years (Y3-Y5): PBR should equal at-market gross
    # (10,000 SF × $30/SF = $300,000/yr), not the 50%-discounted renewal.
    for year in ("Year 3", "Year 4", "Year 5"):
        assert tli.loc["  Potential Base Rent", year] == pytest.approx(300_000, abs=1.0), (
            f"PBR for {year} should be at full market rate, not renewal-discounted"
        )
