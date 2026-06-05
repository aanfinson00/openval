"""Tests for the web API core (``web/api/_lib``).

Tests the JSON-in / JSON-out function that the Vercel serverless handler
wraps. No HTTP layer; just verify the function shape, sign conventions,
and that a known Property roundtrips into a meaningful Argus block.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The api lib lives outside the regular `src/` package layout so we add
# its directory to sys.path. (The lib itself also adds src/ to sys.path
# so openval imports keep working from within it.)
WEB_API_DIR = Path(__file__).parent.parent / "web" / "api"
sys.path.insert(0, str(WEB_API_DIR))

from _lib import build_cashflow_report  # type: ignore[import-not-found]  # noqa: E402


def _minimal_property() -> dict:
    """Single-lease NNN deal — enough to exercise every code path of the
    cashflow reporter without depending on a fixture."""
    return {
        "name": "API test deal",
        "rentable_sf": 50_000,
        "leases": [
            {
                "suite_id": "100",
                "tenant_name": "Acme",
                "area_sf": 50_000,
                "start_date": "2026-01-01",
                "end_date": "2031-01-01",
                "base_rent_steps": [
                    {"start_date": "2026-01-01", "annual_psf": "30"},
                ],
                "expense_structure": "NNN",
                "market_leasing_assumption": {
                    "market_rent_psf": "30",
                    "market_rent_growth_pct": "0",
                    "new_term_months": 60,
                    "renewal_probability": "1.0",
                },
            }
        ],
        "opex_annual": {str(y): str(500_000) for y in range(2026, 2031)},
        "acquisition_date": "2026-01-01",
        "acquisition_price": "20000000",
        "hold_years": 5,
        "exit_cap_rate": "0.07",
    }


def test_response_has_property_name_years_rows():
    out = build_cashflow_report(_minimal_property())
    assert out["property_name"] == "API test deal"
    assert out["years"] == [f"Year {i}" for i in range(1, 6)]
    assert len(out["rows"]) == 34  # full Argus block


def test_row_shape_is_label_indent_is_header_values():
    out = build_cashflow_report(_minimal_property())
    for r in out["rows"]:
        assert set(r.keys()) == {"label", "indent", "is_header", "values"}
        assert isinstance(r["label"], str)
        assert isinstance(r["indent"], int)
        assert isinstance(r["is_header"], bool)
        assert isinstance(r["values"], list)
        assert len(r["values"]) == 5  # 5-year hold


def test_section_headers_marked_and_values_null():
    out = build_cashflow_report(_minimal_property())
    headers = [r for r in out["rows"] if r["is_header"]]
    expected_header_labels = {
        "Rental Revenue", "Other Tenant Revenue", "Vacancy & Credit Loss",
        "Operating Expenses", "Leasing Costs", "Capital Expenditures",
    }
    assert {h["label"] for h in headers} >= expected_header_labels
    for h in headers:
        assert all(v is None for v in h["values"])


def test_indent_levels_match_argus_layout():
    out = build_cashflow_report(_minimal_property())
    label_to_indent = {r["label"]: r["indent"] for r in out["rows"]}
    # Top-level rows (no indent in Argus output)
    assert label_to_indent["Effective Gross Revenue"] == 0
    assert label_to_indent["Net Operating Income"] == 0
    assert label_to_indent["Cash Flow Before Debt Service"] == 0
    # Sub-rows (one indent level in Argus output)
    assert label_to_indent["Potential Base Rent"] == 1
    assert label_to_indent["Total Expense Recoveries"] == 1
    assert label_to_indent["Tenant Improvements"] == 1


def test_numeric_rows_are_floats_or_none():
    out = build_cashflow_report(_minimal_property())
    body_rows = [r for r in out["rows"] if not r["is_header"]]
    for r in body_rows:
        for v in r["values"]:
            assert v is None or isinstance(v, float), (
                f"row {r['label']!r} has non-float value {v!r} ({type(v).__name__})"
            )


def test_total_rental_revenue_is_positive_for_normal_lease():
    out = build_cashflow_report(_minimal_property())
    trr = next(r for r in out["rows"] if r["label"] == "Total Rental Revenue")
    assert all(v > 0 for v in trr["values"])


def test_invalid_payload_raises_validation_error():
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        build_cashflow_report({"name": "incomplete"})


def test_unbound_stub_payload_produces_known_y1_sbr():
    """Roundtrip the Unbound stub through the API and confirm Y1 Scheduled
    Base Rent matches the pinned $742,308 — pegs the API layer to the
    same Argus parity we have for the engine."""
    sys.path.insert(0, str(Path(__file__).parent.parent / "validation"))
    from argus_unbound import build_stub_property  # noqa: E402

    prop = build_stub_property()
    payload = prop.model_dump(mode="json")
    out = build_cashflow_report(payload)
    sbr = next(r for r in out["rows"] if r["label"] == "Scheduled Base Rent")
    assert abs(sbr["values"][0] - 742_308) < 25
