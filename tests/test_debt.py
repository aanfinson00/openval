from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from openval import Loan, amortize_loan


MONTHS = pd.date_range(start="2026-01-01", end="2031-01-01", freq="MS")


def test_payment_matches_pmt_formula():
    """30-year mortgage at 6.5%, $1M principal — payment ~$6,320/mo."""
    loan = Loan(
        principal=Decimal("1000000"),
        rate_annual=Decimal("0.065"),
        amortization_years=30,
        term_years=10,
    )
    df = amortize_loan(loan, date(2026, 1, 1), MONTHS)
    # PMT(0.065/12, 360, -1_000_000) ~= 6,320.68
    assert df.loc["2026-01-01", "payment"] == pytest.approx(6_320.68, abs=1.0)


def test_interest_plus_principal_equals_payment():
    loan = Loan(
        principal=Decimal("1000000"),
        rate_annual=Decimal("0.065"),
        amortization_years=30,
        term_years=10,
    )
    df = amortize_loan(loan, date(2026, 1, 1), MONTHS)
    active = df[df["payment"] > 0]
    diffs = (active["interest"] + active["principal"] - active["payment"]).abs()
    assert (diffs < 0.01).all()


def test_balance_amortizes_down():
    loan = Loan(
        principal=Decimal("1000000"),
        rate_annual=Decimal("0.065"),
        amortization_years=30,
        term_years=10,
    )
    df = amortize_loan(loan, date(2026, 1, 1), MONTHS)
    first = df.loc["2026-01-01", "balance"]
    last = df.loc["2030-12-01", "balance"]
    assert first < 1_000_000  # paid down some
    assert last < first
    assert last > 800_000  # 5 years of 30-yr amort still has most of balance


def test_interest_only_period():
    loan = Loan(
        principal=Decimal("1000000"),
        rate_annual=Decimal("0.06"),
        amortization_years=30,
        term_years=10,
        interest_only_years=2,
    )
    df = amortize_loan(loan, date(2026, 1, 1), MONTHS)
    # IO period: principal == 0, payment == interest
    assert df.loc["2026-06-01", "principal"] == 0.0
    assert df.loc["2026-06-01", "payment"] == pytest.approx(1_000_000 * 0.06 / 12)
    # After IO ends (month 25 onward): principal > 0
    assert df.loc["2028-06-01", "principal"] > 0.0


def test_zero_before_funding_and_after_term():
    loan = Loan(
        principal=Decimal("1000000"),
        rate_annual=Decimal("0.06"),
        amortization_years=30,
        term_years=3,
    )
    df = amortize_loan(loan, date(2027, 1, 1), MONTHS)
    assert df.loc["2026-06-01", "payment"] == 0.0  # before funding
    assert df.loc["2030-06-01", "payment"] == 0.0  # after term


def test_io_longer_than_term_rejected():
    with pytest.raises(ValueError):
        Loan(
            principal=Decimal("1000000"),
            rate_annual=Decimal("0.06"),
            amortization_years=30,
            term_years=2,
            interest_only_years=3,
        )
