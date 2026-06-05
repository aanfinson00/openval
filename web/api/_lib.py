"""Core API logic — pure-function layer that the Vercel serverless handler
wraps. Lives outside ``cashflow.py`` so it can be unit-tested without an
HTTP layer.

The function ``build_cashflow_report`` takes a JSON-shaped Property dict,
runs the engine, and returns a JSON-shaped cashflow report dict ready to
be sent back over the wire.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

# Make the openval package importable from:
#   1. the Vercel function bundle, where `npm run build`'s prebuild step
#      copied `src/openval` to `web/api/openval`. `Path(__file__).parent`
#      is on sys.path automatically inside the function, but we add it
#      defensively so this works under any wrapper.
#   2. local pytest runs against a fresh checkout where the copy hasn't
#      been made — fall back to the repo root's `src/`.
_HERE = Path(__file__).resolve().parent
_REPO_SRC = _HERE.parent.parent / "src"
if (_HERE / "openval" / "__init__.py").exists():
    _IMPORT_ROOT = _HERE
else:
    _IMPORT_ROOT = _REPO_SRC
if str(_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMPORT_ROOT))

from openval import (  # noqa: E402
    Property,
    argus_cashflow_report,
    project_property,
)
from openval.reporting import ARGUS_CASHFLOW_ROWS  # noqa: E402


# Row labels with no leading indent are presentation-level totals or
# section headers; rows with leading whitespace are sub-rows under their
# parent. The frontend uses this to indent visually.
def _indent_level(label: str) -> int:
    stripped = label.lstrip()
    return len(label) - len(stripped)


def _is_section_header(label: str, values: list) -> bool:
    """Argus section headers have no values — every cell is NaN."""
    return all(v is None for v in values)


def _jsonable_value(x: Any) -> Any:
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    if math.isinf(f):
        return None
    return f


def build_cashflow_report(property_payload: dict) -> dict:
    """Run the engine on a JSON Property payload, return a JSON cashflow
    report. Frontend-friendly shape — rows + years + sign-indented labels.

    Raises:
        pydantic.ValidationError if the payload doesn't satisfy the
        ``Property`` schema. The handler should catch and return 400.
    """
    prop = Property.model_validate(property_payload)
    result = project_property(prop)
    df = argus_cashflow_report(result, prop)

    years = list(df.columns)
    rows: list[dict] = []
    for label in ARGUS_CASHFLOW_ROWS:
        if label not in df.index:
            continue
        values = [_jsonable_value(df.loc[label, y]) for y in years]
        rows.append(
            {
                "label": label.strip(),
                "indent": _indent_level(label) // 2,  # 2-space indents → level
                "is_header": _is_section_header(label, values),
                "values": values,
            }
        )

    return {
        "property_name": prop.name,
        "years": years,
        "rows": rows,
        "summary": {
            "unlevered_irr": _jsonable_value(result.unlevered_irr),
            "levered_irr": _jsonable_value(result.levered_irr),
            "unlevered_equity_multiple": _jsonable_value(result.unlevered_equity_multiple),
            "levered_equity_multiple": _jsonable_value(result.levered_equity_multiple),
            "going_in_cap": _jsonable_value(result.going_in_cap),
            "stabilized_cap": _jsonable_value(result.stabilized_cap),
            "stabilized_noi": _jsonable_value(getattr(result, "stabilized_noi", None)),
        },
    }
