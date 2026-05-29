from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from openval import ExpenseStructure, Lease, PercentageRent, RentStep


def _nnn_lease(**overrides) -> Lease:
    defaults = dict(
        suite_id="100",
        tenant_name="Acme Co",
        area_sf=5_000,
        start_date=date(2026, 1, 1),
        end_date=date(2031, 1, 1),
        base_rent_steps=[
            RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("32.00")),
            RentStep(start_date=date(2029, 1, 1), annual_psf=Decimal("36.00")),
        ],
        free_rent_months=3,
        ti_psf=Decimal("50"),
        lc_pct_first_year_rent=Decimal("0.06"),
        expense_structure=ExpenseStructure.NNN,
    )
    defaults.update(overrides)
    return Lease(**defaults)


def test_nnn_lease_constructs():
    lease = _nnn_lease()
    assert lease.term_months() == 60
    assert lease.expense_structure is ExpenseStructure.NNN


def test_mg_requires_base_year_or_stop():
    with pytest.raises(ValidationError):
        _nnn_lease(expense_structure=ExpenseStructure.MG)


def test_mg_with_base_year_ok():
    lease = _nnn_lease(expense_structure=ExpenseStructure.MG, base_year=2026)
    assert lease.base_year == 2026


def test_end_must_follow_start():
    with pytest.raises(ValidationError):
        _nnn_lease(end_date=date(2025, 1, 1))


def test_rent_steps_must_be_increasing():
    with pytest.raises(ValidationError):
        _nnn_lease(
            base_rent_steps=[
                RentStep(start_date=date(2026, 6, 1), annual_psf=Decimal("32")),
                RentStep(start_date=date(2026, 1, 1), annual_psf=Decimal("30")),
            ]
        )


def test_first_step_cannot_predate_lease_start():
    with pytest.raises(ValidationError):
        _nnn_lease(
            base_rent_steps=[
                RentStep(start_date=date(2025, 12, 1), annual_psf=Decimal("32"))
            ]
        )


def test_percentage_rent_unnatural_requires_breakpoint():
    with pytest.raises(ValidationError):
        PercentageRent(natural_breakpoint=False, rate=Decimal("0.06"))


def test_percentage_rent_natural_ok():
    pr = PercentageRent(natural_breakpoint=True, rate=Decimal("0.06"))
    assert pr.breakpoint_annual is None
