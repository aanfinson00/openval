"""Property model: building + rent roll + OpEx schedule + hold assumptions + debt."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from openval.debt import Loan
from openval.lease import Lease


ReversionBasis = Literal["trailing", "forward"]


class Property(BaseModel):
    name: str
    rentable_sf: int = Field(gt=0)
    leases: list[Lease] = Field(default_factory=list)
    opex_annual: dict[int, Decimal]
    capex_annual: dict[int, Decimal] = Field(default_factory=dict)

    acquisition_date: date
    acquisition_price: Decimal = Field(gt=0)
    hold_years: int = Field(gt=0)
    exit_cap_rate: Decimal = Field(gt=0, le=1)
    sale_costs_pct: Decimal = Field(default=Decimal("0.02"), ge=0, le=Decimal("0.1"))
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
    # Credit loss: fraction of gross potential rent deducted for bad debt /
    # collection loss. Industry rule of thumb is 0.5–1%. Argus's
    # "Credit Loss" / "Collection Loss" line.
    credit_loss_pct: Decimal = Field(default=Decimal("0"), ge=0, le=1)

    loan: Optional[Loan] = None

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
