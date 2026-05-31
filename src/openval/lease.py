from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class ExpenseStructure(str, Enum):
    NNN = "NNN"
    MG = "MG"
    FSG = "FSG"


class RentStep(BaseModel):
    start_date: date
    annual_psf: Decimal = Field(gt=0)


class PercentageRent(BaseModel):
    natural_breakpoint: bool = True
    breakpoint_annual: Optional[Decimal] = None
    rate: Decimal = Field(gt=0, le=1)

    @model_validator(mode="after")
    def _breakpoint_required_if_unnatural(self) -> PercentageRent:
        if not self.natural_breakpoint and self.breakpoint_annual is None:
            raise ValueError("breakpoint_annual is required when natural_breakpoint=False")
        return self


class RenewalOption(BaseModel):
    notice_months: int = Field(ge=0)
    term_months: int = Field(gt=0)
    rent_basis: str = "market"
    market_discount_pct: Decimal = Field(default=Decimal("0"), ge=0, le=1)


class MarketLeasingAssumption(BaseModel):
    """Rules applied when a lease expires inside the projection window.

    Generates two probability-weighted speculative segments at every rollover:
    a renewal variant (weight = renewal_probability) and a new-tenant variant
    (weight = 1 - renewal_probability). Each segment inherits this same MLA,
    so rollover chains extend through the projection automatically.
    """

    market_rent_psf: Decimal = Field(gt=0)
    market_rent_growth_pct: Decimal = Field(default=Decimal("0"), ge=0)

    new_term_months: int = Field(gt=0)
    rent_escalation_pct: Decimal = Field(default=Decimal("0"), ge=0)

    free_rent_months_new: int = Field(default=0, ge=0)
    free_rent_months_renewal: int = Field(default=0, ge=0)

    ti_psf_new: Decimal = Field(default=Decimal("0"), ge=0)
    ti_psf_renewal: Decimal = Field(default=Decimal("0"), ge=0)

    lc_pct_new: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    lc_pct_renewal: Decimal = Field(default=Decimal("0"), ge=0, le=1)

    renewal_probability: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    downtime_months_new: int = Field(default=0, ge=0)
    renewal_market_discount_pct: Decimal = Field(default=Decimal("0"), ge=0, le=1)

    expense_structure: ExpenseStructure = ExpenseStructure.NNN


class Lease(BaseModel):
    suite_id: str
    tenant_name: str
    area_sf: int = Field(gt=0)

    start_date: date
    end_date: date

    base_rent_steps: list[RentStep]
    free_rent_months: int = Field(default=0, ge=0)

    ti_psf: Decimal = Field(default=Decimal("0"), ge=0)
    lc_pct_first_year_rent: Decimal = Field(default=Decimal("0"), ge=0, le=1)

    expense_structure: ExpenseStructure
    base_year: Optional[int] = None
    expense_stop_psf: Optional[Decimal] = None
    recovery_cap_pct: Optional[Decimal] = Field(default=None, ge=0)

    percentage_rent: Optional[PercentageRent] = None

    renewal_options: list[RenewalOption] = Field(default_factory=list)

    # When set, the projector synthesizes probability-weighted rollover segments
    # after end_date for the remainder of the projection window. Each speculative
    # segment inherits this same MLA so rollover chains automatically.
    market_leasing_assumption: Optional["MarketLeasingAssumption"] = None

    @field_validator("base_rent_steps")
    @classmethod
    def _steps_sorted_and_nonempty(cls, v: list[RentStep]) -> list[RentStep]:
        if not v:
            raise ValueError("base_rent_steps must contain at least one step")
        for prev, nxt in zip(v, v[1:]):
            if nxt.start_date <= prev.start_date:
                raise ValueError("base_rent_steps must be strictly increasing by start_date")
        return v

    @model_validator(mode="after")
    def _structural_checks(self) -> Lease:
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        if self.base_rent_steps[0].start_date < self.start_date:
            raise ValueError("first rent step cannot precede lease start_date")
        if self.expense_structure is ExpenseStructure.MG:
            if self.base_year is None and self.expense_stop_psf is None:
                raise ValueError("MG lease requires base_year or expense_stop_psf")
        return self

    def term_months(self) -> int:
        years = self.end_date.year - self.start_date.year
        months = self.end_date.month - self.start_date.month
        return years * 12 + months
