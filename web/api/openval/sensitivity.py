"""Sensitivity matrices over OpenVal underwriting metrics.

Standard CRE practice: pick two assumption axes (e.g. rent growth × exit cap),
sweep a grid of values, and report the headline metric (unlevered IRR is the
canonical one). OpenVal's matrix is a pandas DataFrame indexed by one axis
with columns from the other.

Supported axes (anything settable on Property or on its loan):
- exit_cap_rate          (Property.exit_cap_rate)
- sale_costs_pct         (Property.sale_costs_pct)
- general_vacancy_pct    (Property.general_vacancy_pct)
- credit_loss_pct        (Property.credit_loss_pct)
- acquisition_price      (Property.acquisition_price)
- loan_principal         (Property.loan.principal)
- loan_rate              (Property.loan.rate_annual)

Supported metrics:
- unlevered_irr          (UnderwritingResult.unlevered_irr)
- levered_irr            (UnderwritingResult.levered_irr)
- unlevered_em           (UnderwritingResult.unlevered_equity_multiple)
- levered_em             (UnderwritingResult.levered_equity_multiple)
- terminal_noi           (Reversion.terminal_noi)
- gross_sale_price       (Reversion.gross_sale_price)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

import pandas as pd

from openval.dcf import IrrConvention, project_property
from openval.property import Property


_PROPERTY_AXES = {
    "exit_cap_rate",
    "sale_costs_pct",
    "general_vacancy_pct",
    "credit_loss_pct",
    "acquisition_price",
}
_LOAN_AXES = {"loan_principal", "loan_rate"}
_VALID_AXES = _PROPERTY_AXES | _LOAN_AXES

_METRIC_GETTERS = {
    "unlevered_irr": lambda r: r.unlevered_irr,
    "levered_irr": lambda r: r.levered_irr,
    "unlevered_em": lambda r: r.unlevered_equity_multiple,
    "levered_em": lambda r: r.levered_equity_multiple,
    "terminal_noi": lambda r: r.reversion.terminal_noi,
    "gross_sale_price": lambda r: r.reversion.gross_sale_price,
}


def sensitivity(
    prop: Property,
    row_axis: str,
    row_values: Iterable,
    col_axis: str,
    col_values: Iterable,
    metric: str = "unlevered_irr",
    irr_convention: IrrConvention = IrrConvention.MONTHLY_ANNUALIZED,
) -> pd.DataFrame:
    """Run a 2-axis sensitivity sweep over ``prop`` and return a DataFrame.

    Each cell is the value of ``metric`` for the property with ``row_axis``
    overridden to the row value and ``col_axis`` overridden to the column
    value. The original ``prop`` is unchanged.

    ``irr_convention`` only matters when ``metric`` is ``"unlevered_irr"`` or
    ``"levered_irr"`` — for those we recompute IRR under the requested
    convention rather than using the cached monthly-annualized value.

    Example::

        sensitivity(
            prop,
            row_axis="exit_cap_rate", row_values=[Decimal("0.06"), Decimal("0.07"), Decimal("0.08")],
            col_axis="acquisition_price", col_values=[Decimal("4000000"), Decimal("4500000"), Decimal("5000000")],
            metric="unlevered_irr",
        )
    """
    if row_axis not in _VALID_AXES:
        raise ValueError(f"row_axis {row_axis!r} not supported; valid: {sorted(_VALID_AXES)}")
    if col_axis not in _VALID_AXES:
        raise ValueError(f"col_axis {col_axis!r} not supported; valid: {sorted(_VALID_AXES)}")
    if metric not in _METRIC_GETTERS:
        raise ValueError(f"metric {metric!r} not supported; valid: {sorted(_METRIC_GETTERS)}")
    if row_axis == col_axis:
        raise ValueError("row_axis and col_axis must differ")

    row_values = list(row_values)
    col_values = list(col_values)
    getter = _METRIC_GETTERS[metric]

    rows: list[list[Optional[float]]] = []
    for rv in row_values:
        cells: list[Optional[float]] = []
        for cv in col_values:
            tweaked = _apply_overrides(prop, {row_axis: rv, col_axis: cv})
            result = project_property(tweaked)
            if metric in ("unlevered_irr", "levered_irr"):
                levered = metric == "levered_irr"
                cells.append(result.irr(convention=irr_convention, levered=levered))
            else:
                cells.append(getter(result))
        rows.append(cells)

    return pd.DataFrame(rows, index=row_values, columns=col_values)


def _apply_overrides(prop: Property, overrides: dict[str, object]) -> Property:
    """Return a copy of ``prop`` with each ``axis: value`` applied."""
    prop_kwargs = {k: v for k, v in overrides.items() if k in _PROPERTY_AXES}
    loan_overrides = {k: v for k, v in overrides.items() if k in _LOAN_AXES}

    new_prop = prop.model_copy(update={
        k: (v if isinstance(v, Decimal) else Decimal(str(v))) for k, v in prop_kwargs.items()
    })

    if loan_overrides:
        if prop.loan is None:
            raise ValueError(
                f"Cannot override {sorted(loan_overrides)} — property has no loan"
            )
        loan_kwargs: dict[str, Decimal] = {}
        if "loan_principal" in loan_overrides:
            v = loan_overrides["loan_principal"]
            loan_kwargs["principal"] = v if isinstance(v, Decimal) else Decimal(str(v))
        if "loan_rate" in loan_overrides:
            v = loan_overrides["loan_rate"]
            loan_kwargs["rate_annual"] = v if isinstance(v, Decimal) else Decimal(str(v))
        new_loan = prop.loan.model_copy(update=loan_kwargs)
        new_prop = new_prop.model_copy(update={"loan": new_loan})

    return new_prop
