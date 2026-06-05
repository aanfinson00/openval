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

# Make the openval package importable when this module is loaded from the
# Vercel serverless function (`web/api/cashflow.py`) or from tests. The
# repo root is two levels above this file.
_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

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
    }
