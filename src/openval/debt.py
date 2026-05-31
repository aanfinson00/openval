"""Mortgage debt: amortization and monthly debt service.

Supports interest-only periods and a term shorter than the amortization
schedule (balloon at term end). The balloon balance is left in the
`balance` column — the reversion module pays it off at sale.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
from pydantic import BaseModel, Field, model_validator


class Loan(BaseModel):
    principal: Decimal = Field(gt=0)
    rate_annual: Decimal = Field(gt=0, le=1)
    amortization_years: int = Field(gt=0)
    term_years: int = Field(gt=0)
    interest_only_years: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _term_consistency(self) -> "Loan":
        if self.interest_only_years > self.term_years:
            raise ValueError("interest_only_years cannot exceed term_years")
        if self.interest_only_years > self.amortization_years:
            raise ValueError("interest_only_years cannot exceed amortization_years")
        return self


class Refinance(BaseModel):
    """Mid-hold refinance: pay off the existing loan (plus any prepayment
    penalty) and originate a new one with potentially different terms.

    Net cashflow to equity at the refi month equals
    ``new_loan.principal − (old_balance × (1 + prepayment_penalty_pct))``.
    Positive = cash distribution to equity; negative = equity contribution
    (rare; happens when the new loan is smaller than the payoff amount).
    """

    effective_date: date
    new_loan: "Loan"
    prepayment_penalty_pct: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("0.10"))


def amortize_loan_with_refinance(
    initial_loan: Loan,
    initial_funding_date: date,
    months: pd.DatetimeIndex,
    refinance: "Refinance | None" = None,
) -> pd.DataFrame:
    """Amortize a loan that may be refinanced mid-stream.

    Returns the standard `interest / principal / payment / balance` columns,
    plus `refi_proceeds` (single non-zero entry on the refi month equal to
    new_principal − (old_balance × (1 + penalty))).
    """
    base = amortize_loan(initial_loan, initial_funding_date, months)
    base["refi_proceeds"] = 0.0
    if refinance is None:
        return base

    refi_ts = pd.Timestamp(year=refinance.effective_date.year,
                           month=refinance.effective_date.month, day=1)
    if refi_ts not in months:
        return base

    # Capture old balance at end of the refi month (post-amort), then payoff
    # before swapping to the new loan.
    old_balance_at_refi = float(base.loc[refi_ts, "balance"])
    payoff = old_balance_at_refi * (1.0 + float(refinance.prepayment_penalty_pct))

    # From the refi month onward, replace the amortization with the new loan.
    new_months = months[months >= refi_ts]
    new_amort = amortize_loan(refinance.new_loan, refinance.effective_date, new_months)

    out = base.copy()
    for col in ("interest", "principal", "payment", "balance"):
        out.loc[new_months, col] = new_amort[col].values
    # Refi proceeds: cash to equity at the refi month.
    proceeds = float(refinance.new_loan.principal) - payoff
    out.loc[refi_ts, "refi_proceeds"] = proceeds
    return out


def amortize_loan(
    loan: Loan,
    funding_date: date,
    months: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Monthly amortization schedule aligned to `months`.

    Columns: interest, principal, payment, balance.
    Rows before funding_date or after loan term are zero (balance carries last).
    """
    monthly_rate = float(loan.rate_annual) / 12.0
    amort_months = loan.amortization_years * 12
    term_months = loan.term_years * 12
    io_months = loan.interest_only_years * 12

    payment = _amortizing_payment(float(loan.principal), monthly_rate, amort_months)

    out = pd.DataFrame(
        0.0,
        index=months,
        columns=["interest", "principal", "payment", "balance"],
    )
    funding_ts = pd.Timestamp(year=funding_date.year, month=funding_date.month, day=1)

    balance = float(loan.principal)
    months_funded = 0
    for ts in months:
        if ts < funding_ts:
            continue
        months_funded += 1
        if months_funded > term_months:
            out.loc[ts, "balance"] = balance
            continue

        interest = balance * monthly_rate
        if months_funded <= io_months:
            principal_paid = 0.0
            pmt = interest
        else:
            principal_paid = min(payment - interest, balance)
            pmt = interest + principal_paid

        balance -= principal_paid
        out.loc[ts, "interest"] = interest
        out.loc[ts, "principal"] = principal_paid
        out.loc[ts, "payment"] = pmt
        out.loc[ts, "balance"] = balance

    return out


def _amortizing_payment(principal: float, monthly_rate: float, n_months: int) -> float:
    if monthly_rate == 0:
        return principal / n_months
    factor = (1 + monthly_rate) ** n_months
    return principal * (monthly_rate * factor) / (factor - 1)
