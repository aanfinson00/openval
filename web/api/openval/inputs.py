"""Input-construction helpers for OpenVal.

Where ``openval.io.*`` parses external file formats and ``openval.reporting``
analyzes projection outputs, this module is for transforming raw deal
inputs into the dicts / lists that ``Property`` expects — useful when the
source data isn't already in OpenVal shape.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Union

from openval.property import Property


def opex_with_pct_of_revenue_fee(
    base_opex: dict[int, Decimal],
    pct_of_revenue: Union[Decimal, float, str],
    prop_template: Property,
    *,
    max_iter: int = 10,
    tolerance: float = 1.0,
) -> dict[int, Decimal]:
    """Compose an opex schedule that includes a percentage-of-revenue fee.

    Argus's Property Management Fee is typically quoted as a % of Effective
    Gross Revenue, but OpenVal's projector takes a flat annual opex dict.
    EGR depends on recoveries which depend on opex which include the fee →
    circular. This helper runs the projector iteratively, converging on a
    stable schedule (each step shrinks error by ``pct × occupancy``, so
    ~2-3 iterations is normal for a 4% fee).

    Args:
        base_opex: Annual non-percentage opex (taxes, insurance, CAM, ...).
        pct_of_revenue: Fee as a fraction of EGR (e.g. ``Decimal("0.04")``).
        prop_template: A ``Property`` to project on. Its ``opex_annual`` is
            swapped per iteration; everything else comes from this template.
            Pass it with ``base_opex`` already set as a starting point.
        max_iter: Convergence cap (default 10).
        tolerance: Max per-year dollar change before declaring convergence
            (default $1).

    Returns:
        Full opex dict (base + fee per year). Same key set as ``base_opex``.

    Example::

        prop = Property(..., opex_annual=base_opex, ...)
        full_opex = opex_with_pct_of_revenue_fee(
            base_opex, Decimal("0.04"), prop
        )
        prop = prop.model_copy(update={"opex_annual": full_opex})
    """
    # Deferred import to avoid a circular dependency at module load.
    from openval.dcf import project_property

    pct = Decimal(str(pct_of_revenue))
    if pct == 0:
        return {y: Decimal(v) for y, v in base_opex.items()}

    pct_float = float(pct)
    curr: dict[int, Decimal] = {y: Decimal(v) for y, v in base_opex.items()}

    for _ in range(max_iter):
        prop_iter = prop_template.model_copy(update={"opex_annual": curr})
        result = project_property(prop_iter)
        egi_by_year = (
            result.cashflows["egi"].groupby(result.cashflows.index.year).sum()
        )
        max_delta = 0.0
        next_opex: dict[int, Decimal] = {}
        for year, base_v in base_opex.items():
            egi = float(egi_by_year.get(year, 0.0))
            new_v = float(base_v) + pct_float * egi
            next_opex[year] = Decimal(str(round(new_v, 2)))
            max_delta = max(max_delta, abs(new_v - float(curr[year])))
        curr = next_opex
        if max_delta < tolerance:
            break
    return curr
