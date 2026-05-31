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
    # >=0 to support vacant-suite modeling (a Lease that's already expired at
    # acquisition with $0 placeholder rent; the MLA handles the lease-up).
    annual_psf: Decimal = Field(ge=0)


class CpiEscalator(BaseModel):
    """Annual CPI-indexed escalation, applied to the lease's preceding
    base-rent step (or the first step if none precedes the escalator's
    ``effective_date``). Common in long-term industrial / ground-lease deals.

    Mechanics: for each escalator year, take the latest base PSF, multiply
    by min(ceiling, max(floor, cpi_rate_for_year)).

    ``floor_pct`` and ``ceiling_pct`` are fractions, e.g. 0.02 / 0.05 = 2%/5%.
    Set ``ceiling_pct=None`` for an uncapped escalator.
    """

    effective_date: date
    floor_pct: Decimal = Field(default=Decimal("0"), ge=0)
    ceiling_pct: Optional[Decimal] = Field(default=None, ge=0)


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
    # CPI-indexed escalators applied annually. Each escalator looks up the
    # CPI rate for its effective_date.year in the property's cpi_series,
    # clamps to [floor_pct, ceiling_pct], and bumps the prevailing PSF.
    cpi_escalators: list[CpiEscalator] = Field(default_factory=list)
    free_rent_months: int = Field(default=0, ge=0)

    ti_psf: Decimal = Field(default=Decimal("0"), ge=0)
    lc_pct_first_year_rent: Decimal = Field(default=Decimal("0"), ge=0, le=1)

    expense_structure: ExpenseStructure
    base_year: Optional[int] = None
    expense_stop_psf: Optional[Decimal] = None
    recovery_cap_pct: Optional[Decimal] = Field(default=None, ge=0)

    percentage_rent: Optional[PercentageRent] = None
    # Year → projected gross sales (only relevant when percentage_rent is set).
    # Keys are calendar years; values are annual sales for that year.
    annual_sales: dict[int, Decimal] = Field(default_factory=dict)

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

    @classmethod
    def vacant_at_acquisition(
        cls,
        suite_id: str,
        area_sf: int,
        acquisition_date: date,
        market_leasing_assumption: "MarketLeasingAssumption",
        expense_structure: ExpenseStructure = ExpenseStructure.NNN,
    ) -> "Lease":
        """Build a placeholder Lease for a suite that's dark at acquisition.

        The lease is constructed so its term has already ended at the
        acquisition month, which triggers immediate MLA rollover from day 1.
        The renewal branch starts at the acquisition month; the new-tenant
        branch starts after ``downtime_months_new``. Combined with a
        ``renewal_probability=0`` MLA this models "vacant suite leasing up
        from market" — the standard Argus pattern.
        """
        # End date = the acquisition month; start one month earlier so the
        # validator accepts it. The "real" lease covers the preceding month,
        # which is outside the projection window and has $0 rent.
        end = acquisition_date
        if end.month == 1:
            start = date(end.year - 1, 12, end.day)
        else:
            start = date(end.year, end.month - 1, end.day)
        return cls(
            suite_id=suite_id,
            tenant_name="VACANT",
            area_sf=area_sf,
            start_date=start,
            end_date=end,
            base_rent_steps=[RentStep(start_date=start, annual_psf=Decimal("0"))],
            expense_structure=expense_structure,
            market_leasing_assumption=market_leasing_assumption,
        )
