"""Property model: building + rent roll + OpEx schedule + hold assumptions + debt."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from openval.debt import Loan, Refinance
from openval.lease import Lease


ReversionBasis = Literal["trailing", "forward"]


class Property(BaseModel):
    name: str
    rentable_sf: int = Field(gt=0)
    leases: list[Lease] = Field(default_factory=list)
    opex_annual: dict[int, Decimal]
    # Optional per-category opex breakdown. When set, ``opex_annual`` is
    # derived as the per-year sum of all categories (or validated against the
    # provided value). Categories named after Argus's standard rows
    # ("Real Estate Taxes", "Insurance", "Property Management Fee", "CAM")
    # surface as sub-rows in ``argus_cashflow_report``; non-standard names
    # still feed into the opex total but don't have a dedicated row in the
    # Argus layout.
    opex_categories: Optional[dict[str, dict[int, Decimal]]] = Field(default=None)
    capex_annual: dict[int, Decimal] = Field(default_factory=dict)
    # Optional per-category capex breakdown. Mirrors opex_categories. When
    # set, ``capex_annual`` is derived as the per-year sum (or validated).
    # Categories named "Capital Reserves" and "Non-Leasing Capital Expense"
    # surface as sub-rows in ``argus_cashflow_report``; other names still
    # feed the total but don't get a dedicated Argus row.
    capex_categories: Optional[dict[str, dict[int, Decimal]]] = Field(default=None)

    acquisition_date: date
    acquisition_price: Decimal = Field(gt=0)
    hold_years: int = Field(gt=0)
    exit_cap_rate: Decimal = Field(gt=0, le=1)
    sale_costs_pct: Decimal = Field(default=Decimal("0.02"), ge=0, le=Decimal("0.1"))
    # Closing costs (legal, due diligence, lender fees, etc.) — fraction of
    # acquisition_price added to the initial equity outlay. Not financed by
    # the loan (loan principal is sized on acquisition_price only).
    acquisition_costs_pct: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("0.1"))
    # "trailing": terminal value = trailing-12 NOI / cap (default; OpenVal Phase 1).
    # "forward": terminal value = NOI for the 12 months *following* the hold period
    # divided by cap (Argus convention). Requires opex_annual to cover the year
    # after the hold ends.
    reversion_basis: ReversionBasis = Field(default="trailing")

    # General vacancy: fraction of gross potential rent deducted each month as
    # background vacancy (e.g. 0.05 = 5% vacancy assumption). Argus's
    # "General Vacancy" — applied on top of (not instead of) absorption /
    # turnover vacancy captured by MLA downtime. Set to 0 to disable.
    general_vacancy_pct: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    # Per-year override of general_vacancy_pct. When a calendar year appears
    # in this dict, all months in that year use this fraction instead of the
    # flat `general_vacancy_pct`. Years not in the dict fall back to the flat
    # value. Argus drift-fit knob: real deals usually show vacancy spiking
    # during rollover years and settling lower during stabilized years; this
    # field lets a stub mirror that without modeling tenant turnover.
    general_vacancy_by_year: dict[int, Decimal] = Field(default_factory=dict)
    # Credit loss: fraction of gross potential rent deducted for bad debt /
    # collection loss. Industry rule of thumb is 0.5–1%. Argus's
    # "Credit Loss" / "Collection Loss" line.
    credit_loss_pct: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    # Per-year override of credit_loss_pct. Same semantics as
    # `general_vacancy_by_year`.
    credit_loss_by_year: dict[int, Decimal] = Field(default_factory=dict)
    # CPI rate series for CPI-indexed lease escalators. Year → CPI rate
    # (fraction). Lease.cpi_escalators read from this series; if a year
    # is missing, the escalator skips that year.
    cpi_series: dict[int, Decimal] = Field(default_factory=dict)
    # Reimbursement gross-up: when occupancy falls below this threshold for a
    # year, opex passed into the recovery calc is scaled up to threshold-
    # occupancy equivalent. Each tenant ends up paying their pro-rata share of
    # the *grossed-up* opex, leaving the landlord on the hook only for the
    # threshold-equivalent vacancy share. None = disabled. Argus's
    # "Gross Up Reimbursements" toggle; common threshold is 0.95 or 1.00.
    opex_gross_up_at_occupancy_pct: Optional[Decimal] = Field(default=None, ge=0, le=1)
    # Non-recoverable share of opex: management fees, marketing, etc., that
    # don't pass through to NNN/MG tenants even though they sit on the
    # property's books. Default 0 = everything is recoverable (current Argus
    # default). Set to e.g. 0.08 to mark 8% of opex as landlord-eat.
    opex_non_recoverable_pct: Decimal = Field(default=Decimal("0"), ge=0, le=1)

    loan: Optional[Loan] = None
    # Optional mid-hold refinance: pay off the original loan and originate a
    # new one with different terms (rate, principal, amort, IO). Common in
    # value-add deals where a stabilized refi pulls equity out at year 3-5.
    refinance: Optional[Refinance] = None

    @model_validator(mode="before")
    @classmethod
    def _derive_totals_from_categories(cls, data: Any) -> Any:
        """If ``opex_categories`` / ``capex_categories`` are supplied, derive
        (or validate) the corresponding ``opex_annual`` / ``capex_annual``
        totals from the per-year sum across categories.

        - Categories alone → the matching total is auto-populated.
        - Both supplied → validate they agree per year (within 1 cent).
        - Categories absent → no change (existing single-line behavior).
        """
        if not isinstance(data, dict):
            return data
        for cat_key, total_key in (
            ("opex_categories", "opex_annual"),
            ("capex_categories", "capex_annual"),
        ):
            categories = data.get(cat_key)
            if not categories:
                continue
            derived: dict[int, Decimal] = {}
            for cat_schedule in categories.values():
                if not isinstance(cat_schedule, dict):
                    continue
                for year, amount in cat_schedule.items():
                    # JSON dict keys are always strings; coerce.
                    y_int = int(year)
                    if not isinstance(amount, Decimal):
                        amount = Decimal(str(amount))
                    derived[y_int] = derived.get(y_int, Decimal("0")) + amount
            provided = data.get(total_key)
            if not provided:
                data[total_key] = derived
                continue
            # JSON roundtrips turn int dict keys into strings; normalize so
            # both sides compare on the same key type.
            provided_norm = {int(y): v for y, v in provided.items()}
            all_years = set(derived) | set(provided_norm)
            for y in all_years:
                d_v = derived.get(y, Decimal("0"))
                p_raw = provided_norm.get(y, Decimal("0"))
                p_v = p_raw if isinstance(p_raw, Decimal) else Decimal(str(p_raw))
                if abs(d_v - p_v) > Decimal("0.01"):
                    raise ValueError(
                        f"{total_key}[{y}]={p_v} disagrees with sum of "
                        f"{cat_key}[*][{y}]={d_v}"
                    )
        return data

    @model_validator(mode="after")
    def _structural_checks(self) -> "Property":
        if not self.opex_annual:
            raise ValueError("opex_annual cannot be empty")
        for lease in self.leases:
            if lease.area_sf > self.rentable_sf:
                raise ValueError(
                    f"lease {lease.suite_id} area_sf {lease.area_sf} exceeds property rentable_sf {self.rentable_sf}"
                )
        if self.loan is not None and self.loan.principal >= self.acquisition_price:
            raise ValueError("loan principal must be less than acquisition price")
        if self.reversion_basis == "forward":
            self._check_forward_opex_coverage()
        return self

    def _check_forward_opex_coverage(self) -> None:
        """Forward NOI projects one extra year past the hold; opex must cover it."""
        hold_end_year = self.acquisition_date.year + self.hold_years - 1
        forward_year_start = hold_end_year + 1
        # Hold can straddle calendar years; forward year can do the same.
        forward_year_end = hold_end_year + 2 if self.acquisition_date.month > 1 else hold_end_year + 1
        missing = [
            y for y in range(forward_year_start, forward_year_end + 1)
            if y not in self.opex_annual
        ]
        if missing:
            raise ValueError(
                f"reversion_basis='forward' requires opex_annual to cover the year "
                f"following the hold period; missing year(s): {missing}"
            )
