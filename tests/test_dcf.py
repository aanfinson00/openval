from datetime import date
from decimal import Decimal

import pytest

from openval import (
    ExpenseStructure,
    IrrConvention,
    Lease,
    Loan,
    Property,
    RentStep,
    project_property,
)


def _full_building_nnn() -> Property:
    """One tenant fills 50,000 sf at $30/sf NNN, 5-yr lease, no debt."""
    lease = Lease(
        suite_id="100",
        tenant_name="Solo Tenant",
        area_sf=50_000,
        start_date=date(2026, 1, 1),
        end_date=date(2031, 1, 1),
        base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("30"))],
        expense_structure=ExpenseStructure.NNN,
    )
    return Property(
        name="Test Building",
        rentable_sf=50_000,
        leases=[lease],
        opex_annual={
            2026: Decimal("500000"),
            2027: Decimal("500000"),
            2028: Decimal("500000"),
            2029: Decimal("500000"),
            2030: Decimal("500000"),
        },
        acquisition_date=date(2026, 1, 1),
        acquisition_price=Decimal("15000000"),
        hold_years=5,
        exit_cap_rate=Decimal("0.07"),
    )


def test_noi_full_building_nnn():
    """Gross rent 1.5M + recoveries 500k - opex 500k = NOI 1.5M/yr."""
    result = project_property(_full_building_nnn())
    cf = result.cashflows
    # Year 1 NOI (sum of 12 months)
    year_1 = cf.loc["2026-01-01":"2026-12-31"]
    assert year_1["gross_rent"].sum() == pytest.approx(1_500_000.0)
    assert year_1["recoveries"].sum() == pytest.approx(500_000.0)
    assert year_1["opex"].sum() == pytest.approx(-500_000.0)
    assert year_1["noi"].sum() == pytest.approx(1_500_000.0)


def test_reversion_matches_trailing_noi_over_cap():
    """$1.5M trailing NOI / 7% cap = $21.43M gross sale, less 2% costs."""
    result = project_property(_full_building_nnn())
    assert result.reversion.terminal_noi == pytest.approx(1_500_000.0)
    expected_gross = 1_500_000.0 / 0.07
    assert result.reversion.gross_sale_price == pytest.approx(expected_gross)
    assert result.reversion.sale_costs == pytest.approx(expected_gross * 0.02)
    assert result.reversion.net_sale == pytest.approx(expected_gross * 0.98)


def test_unlevered_irr_positive_and_reasonable():
    """$15M in, $1.5M/yr NOI (10% cap on cost), exit at 7% cap. IRR > entry cap."""
    result = project_property(_full_building_nnn())
    # 10% on cost + cap rate compression = strong IRR
    assert result.unlevered_irr is not None
    assert 0.12 < result.unlevered_irr < 0.25
    # Equity multiple: 5 years of yield (~50%) + reversion (~140% of equity) = ~1.9-2.0x
    assert 1.7 < result.unlevered_equity_multiple < 2.2


def test_no_loan_means_levered_equals_unlevered_metrics_none():
    result = project_property(_full_building_nnn())
    assert result.levered_irr is None
    assert result.levered_equity_multiple is None


def test_with_loan_levered_irr_exceeds_unlevered():
    """Positive leverage: when entry yield > debt cost, levered IRR > unlevered."""
    prop = _full_building_nnn()
    levered = Property(
        **{**prop.model_dump(), "loan": Loan(
            principal=Decimal("9000000"),  # 60% LTV
            rate_annual=Decimal("0.055"),
            amortization_years=30,
            term_years=10,
        )}
    )
    result = project_property(levered)
    assert result.levered_irr is not None
    assert result.unlevered_irr is not None
    # Entry yield (~10%) > debt cost (5.5%) -> positive leverage
    assert result.levered_irr > result.unlevered_irr


def test_loan_payoff_in_reversion():
    """Loan balance at sale shows up as loan_payoff, reduces net to equity."""
    prop = _full_building_nnn()
    levered = Property(
        **{**prop.model_dump(), "loan": Loan(
            principal=Decimal("9000000"),
            rate_annual=Decimal("0.055"),
            amortization_years=30,
            term_years=10,
        )}
    )
    result = project_property(levered)
    assert result.reversion.loan_payoff > 8_000_000  # most of principal still outstanding after 5 yrs
    assert result.reversion.loan_payoff < 9_000_000  # but some paid down
    assert result.reversion.net_sale_to_equity == pytest.approx(
        result.reversion.net_sale - result.reversion.loan_payoff
    )


def test_loan_principal_exceeds_price_rejected():
    prop = _full_building_nnn()
    with pytest.raises(ValueError):
        Property(
            **{**prop.model_dump(), "loan": Loan(
                principal=Decimal("20000000"),
                rate_annual=Decimal("0.055"),
                amortization_years=30,
                term_years=10,
            )}
        )


def _escalating_nnn(reversion_basis: str = "trailing") -> Property:
    """Same shape as _full_building_nnn but 5% annual rent step-ups so trailing
    vs forward NOI diverge measurably."""
    steps = [
        RentStep(
            start_date=date(2026 + i, 1, 1),
            annual_psf=(Decimal("30") * (Decimal("1.05") ** i)).quantize(Decimal("0.01")),
        )
        for i in range(6)  # cover year 6 too so forward mode can read it
    ]
    lease = Lease(
        suite_id="100",
        tenant_name="Solo Tenant",
        area_sf=50_000,
        start_date=date(2026, 1, 1),
        end_date=date(2032, 1, 1),
        base_rent_steps=steps,
        expense_structure=ExpenseStructure.NNN,
    )
    opex = {2026 + i: Decimal("500000") for i in range(6)}  # flat opex through year 6
    return Property(
        name="Test Building (escalating)",
        rentable_sf=50_000,
        leases=[lease],
        opex_annual=opex,
        acquisition_date=date(2026, 1, 1),
        acquisition_price=Decimal("15000000"),
        hold_years=5,
        exit_cap_rate=Decimal("0.07"),
        reversion_basis=reversion_basis,
    )


def test_reversion_basis_defaults_to_trailing():
    prop = _full_building_nnn()
    assert prop.reversion_basis == "trailing"
    result = project_property(prop)
    assert result.reversion.basis == "trailing"


def test_forward_basis_changes_terminal_noi_under_escalation():
    """With 5% annual rent steps, forward NOI > trailing-12 NOI."""
    trailing_result = project_property(_escalating_nnn("trailing"))
    forward_result = project_property(_escalating_nnn("forward"))

    assert trailing_result.reversion.basis == "trailing"
    assert forward_result.reversion.basis == "forward"
    # 5% escalation between hold-year-5 rent and hold-year-6 rent.
    # NOI is gross_rent + flat recoveries netting opex; the rent step drives the delta.
    assert forward_result.reversion.terminal_noi > trailing_result.reversion.terminal_noi
    # Expect roughly the year-6 / year-5 rent ratio on the rent component.
    # Year 5 rent psf = 30 * 1.05^4; year 6 = 30 * 1.05^5. Ratio ≈ 1.05.
    # NOI grows by rent_delta only (recoveries == opex on NNN here), so
    # terminal_noi ratio should sit between 1.0 and 1.05.
    ratio = forward_result.reversion.terminal_noi / trailing_result.reversion.terminal_noi
    assert 1.02 < ratio < 1.06


def test_forward_basis_matches_trailing_when_rent_is_flat():
    """Flat rent + flat opex → forward and trailing reversion NOI must match."""
    trailing_result = project_property(_full_building_nnn())
    # Extend opex to cover year 6 so we can run forward mode on this same deal.
    prop = _full_building_nnn()
    forward_prop = Property(
        **{
            **prop.model_dump(),
            "opex_annual": {**prop.opex_annual, 2031: Decimal("500000")},
            "reversion_basis": "forward",
        }
    )
    # Extend the lease into year 6 too — otherwise forward NOI sees zero rent
    # and falls off a cliff (true to model: lease expires).
    forward_prop.leases[0] = Lease(
        **{
            **forward_prop.leases[0].model_dump(),
            "end_date": date(2032, 1, 1),
        }
    )
    forward_result = project_property(forward_prop)
    assert forward_result.reversion.terminal_noi == pytest.approx(
        trailing_result.reversion.terminal_noi, rel=1e-9
    )


def test_forward_basis_requires_year_n_plus_1_opex():
    """Property rejects forward basis if opex_annual lacks year N+1."""
    prop_dict = _full_building_nnn().model_dump()
    prop_dict["reversion_basis"] = "forward"
    # opex_annual only covers 2026-2030; hold ends 2030, forward year is 2031.
    with pytest.raises(ValueError, match="reversion_basis='forward'"):
        Property(**prop_dict)


def test_forward_basis_irr_exceeds_trailing_under_escalation():
    """Higher terminal NOI → higher gross sale → higher IRR."""
    trailing_result = project_property(_escalating_nnn("trailing"))
    forward_result = project_property(_escalating_nnn("forward"))
    assert forward_result.unlevered_irr > trailing_result.unlevered_irr


def test_general_vacancy_reduces_egi():
    """5% general vacancy on a 1.5M gross-rent year → 75k vacancy deduction."""
    prop = _full_building_nnn()
    with_vac = Property(**{**prop.model_dump(), "general_vacancy_pct": Decimal("0.05")})
    result = project_property(with_vac)
    year_1 = result.cashflows.loc["2026-01-01":"2026-12-31"]
    assert year_1["gross_rent"].sum() == pytest.approx(1_500_000.0, rel=1e-6)
    assert year_1["general_vacancy"].sum() == pytest.approx(-75_000.0, rel=1e-6)
    # EGI = gross + abatement + vacancy + recoveries; NOI = EGI - opex.
    assert year_1["noi"].sum() == pytest.approx(1_425_000.0, rel=1e-6)


def test_credit_loss_reduces_egi():
    """1% credit loss on 1.5M gross rent → 15k deduction."""
    prop = _full_building_nnn()
    with_cl = Property(**{**prop.model_dump(), "credit_loss_pct": Decimal("0.01")})
    result = project_property(with_cl)
    year_1 = result.cashflows.loc["2026-01-01":"2026-12-31"]
    assert year_1["credit_loss"].sum() == pytest.approx(-15_000.0, rel=1e-6)
    assert year_1["noi"].sum() == pytest.approx(1_485_000.0, rel=1e-6)


def test_vacancy_and_credit_loss_compound():
    """Both apply independently — 5% vacancy + 1% credit loss → 6% total deduction."""
    prop = _full_building_nnn()
    both = Property(
        **{
            **prop.model_dump(),
            "general_vacancy_pct": Decimal("0.05"),
            "credit_loss_pct": Decimal("0.01"),
        }
    )
    result = project_property(both)
    year_1 = result.cashflows.loc["2026-01-01":"2026-12-31"]
    assert year_1["general_vacancy"].sum() == pytest.approx(-75_000.0, rel=1e-6)
    assert year_1["credit_loss"].sum() == pytest.approx(-15_000.0, rel=1e-6)
    assert year_1["noi"].sum() == pytest.approx(1_410_000.0, rel=1e-6)


def test_zero_vacancy_default_preserves_legacy_noi():
    """Default 0% vacancy/credit loss → NOI matches the baseline test exactly."""
    baseline = project_property(_full_building_nnn())
    explicit_zero = project_property(
        Property(
            **{
                **_full_building_nnn().model_dump(),
                "general_vacancy_pct": Decimal("0"),
                "credit_loss_pct": Decimal("0"),
            }
        )
    )
    pd_series_equal = lambda a, b: a.equals(b) or (a - b).abs().max() < 1e-9
    assert pd_series_equal(baseline.cashflows["noi"], explicit_zero.cashflows["noi"])


def test_irr_default_matches_monthly_annualized():
    """result.unlevered_irr equals result.irr() with default convention."""
    result = project_property(_full_building_nnn())
    assert result.unlevered_irr == pytest.approx(result.irr(), rel=1e-9)
    assert result.irr(convention="monthly_annualized") == pytest.approx(result.unlevered_irr)


def test_irr_levered_kwarg_returns_levered_irr():
    prop = _full_building_nnn()
    levered = Property(
        **{**prop.model_dump(), "loan": Loan(
            principal=Decimal("9000000"),
            rate_annual=Decimal("0.055"),
            amortization_years=30,
            term_years=10,
        )}
    )
    result = project_property(levered)
    assert result.irr(levered=True) == pytest.approx(result.levered_irr, rel=1e-9)


def test_irr_levered_none_when_no_loan():
    result = project_property(_full_building_nnn())
    assert result.irr(levered=True) is None


def test_irr_annual_end_of_year_lower_than_monthly():
    """Year-end annual bucketing pushes cashflows later → lower IRR."""
    result = project_property(_full_building_nnn())
    monthly = result.irr()
    annual_eoy = result.irr(convention=IrrConvention.ANNUAL_END_OF_YEAR)
    assert annual_eoy is not None
    assert annual_eoy < monthly


def test_irr_annual_mid_year_above_end_of_year():
    """Mid-year IRR > end-of-year IRR (cashflows arrive 6 months earlier)."""
    result = project_property(_full_building_nnn())
    eoy = result.irr(convention="annual_end_of_year")
    mid = result.irr(convention="annual_mid_year")
    assert eoy is not None and mid is not None
    assert mid > eoy
    # The two annual conventions should differ by a meaningful but bounded amount.
    # For ~5yr CRE holds with terminal cashflow, the gap is typically 150–400 bps.
    assert 0.005 < (mid - eoy) < 0.05


def test_irr_string_convention_accepted():
    """Strings work in place of the enum."""
    result = project_property(_full_building_nnn())
    assert result.irr(convention="annual_end_of_year") == pytest.approx(
        result.irr(convention=IrrConvention.ANNUAL_END_OF_YEAR), rel=1e-12
    )


def test_lease_too_big_for_building_rejected():
    with pytest.raises(ValueError):
        Property(
            name="Bad",
            rentable_sf=10_000,
            leases=[Lease(
                suite_id="100",
                tenant_name="Too Big",
                area_sf=20_000,
                start_date=date(2026, 1, 1),
                end_date=date(2031, 1, 1),
                base_rent_steps=[RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("30"))],
                expense_structure=ExpenseStructure.NNN,
            )],
            opex_annual={2026: Decimal("100000")},
            acquisition_date=date(2026, 1, 1),
            acquisition_price=Decimal("5000000"),
            hold_years=5,
            exit_cap_rate=Decimal("0.07"),
        )
