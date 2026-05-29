"""Property model: building + rent roll + OpEx schedule + hold assumptions + debt."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from openval.debt import Loan
from openval.lease import Lease


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
        return self
