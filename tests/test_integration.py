"""
Integration tests: full pipeline from parsed data to Excel export.
These tests do NOT require real PDFs or macOS — they use pre-built model data.
"""
import csv
import json
import tempfile
from pathlib import Path
from decimal import Decimal

import pytest

from core.calculator import compute_tax_data
from core.exporter import export_to_excel
from core.models import Asset
from tests.fixtures.sample_data import (
    make_us_stock_portfolio,
    make_euro_etf_portfolio,
    make_dividend_portfolio,
    make_multi_year_portfolio,
)


def test_us_stock_full_pipeline():
    """Full pipeline: parse-like data → calculate → export."""
    assets = make_us_stock_portfolio()
    audit_rows, dashboards, positions_by_year, events_by_year = compute_tax_data(assets)

    assert len(audit_rows) == 3
    assert len(dashboards) == 1
    assert dashboards[0].year == 2024

    # Check PMP after buys
    aapl_pos = positions_by_year[2024]["US0378331005"]
    expected_cost = Decimal("1510") + Decimal("808")  # both buys
    expected_qty = Decimal("10") + Decimal("5")  # both buys
    assert aapl_pos.total_quantity == expected_qty - Decimal("3")  # after sell
    assert aapl_pos.total_cost == Decimal("2318") * (Decimal("12") / Decimal("15"))

    # Check gain is reported in form 3VG
    gain = sum(d.value for d in dashboards[0].declarations if d.box == "3VG")
    assert gain > 0

    # Export
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = Path(f.name)
    try:
        positions = positions_by_year[2024]
        year_events = events_by_year[2024]
        export_to_excel(
            assets, path, dashboards, audit_rows,
            positions, year_events, 2024,
        )
        assert path.exists()
        assert path.stat().st_size > 1000
    finally:
        path.unlink(missing_ok=True)


def test_dividend_full_pipeline():
    """Pipeline with dividends: verify 2DC form box."""
    assets = make_dividend_portfolio()
    audit_rows, dashboards, positions_by_year, events_by_year = compute_tax_data(assets)

    assert len(audit_rows) == 2
    assert len(dashboards) == 1

    div_income = sum(d.value for d in dashboards[0].declarations if d.box == "2DC")
    assert div_income == pytest.approx(4.44, rel=0.01)

    # Check 2047: US dividends should appear
    assert len(dashboards[0].form_2047_details) == 1
    assert dashboards[0].form_2047_details[0]["L202_Pays"] == "États-Unis"

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = Path(f.name)
    try:
        positions = positions_by_year[2024]
        year_events = events_by_year[2024]
        export_to_excel(
            assets, path, dashboards, audit_rows,
            positions, year_events, 2024,
        )
        assert path.exists()
    finally:
        path.unlink(missing_ok=True)


def test_multi_year_pipeline():
    """Portfolio spanning 2023-2024: positions snapshot at year boundary."""
    assets = make_multi_year_portfolio()
    audit_rows, dashboards, positions_by_year, events_by_year = compute_tax_data(assets)

    assert 2023 in positions_by_year
    assert 2024 in positions_by_year

    pos_2023 = positions_by_year[2023]["DE000BASF111"]
    assert pos_2023.total_quantity == Decimal("15")

    pos_2024 = positions_by_year[2024]["DE000BASF111"]
    assert pos_2024.total_quantity == Decimal("10")

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = Path(f.name)
    try:
        latest = max(positions_by_year.keys())
        export_to_excel(
            assets, path, dashboards, audit_rows,
            positions_by_year[latest], events_by_year[latest], latest,
        )
        assert path.exists()
    finally:
        path.unlink(missing_ok=True)


def test_two_assets_pipeline():
    """Multiple assets in one pipeline."""
    assets = make_us_stock_portfolio()
    assets.update(make_euro_etf_portfolio())
    audit_rows, dashboards, positions_by_year, events_by_year = compute_tax_data(assets)

    assert len(audit_rows) == 4
    assert "US0378331005" in positions_by_year[2024]
    assert "FR0010315770" in positions_by_year[2024]


@pytest.mark.skipif(not (Path(__file__).parent / "fixtures" / "pdfs").exists(), reason="No tests/fixtures/pdfs/ directory")
def test_real_pdf_parsing():
    """Parse real N26 PDFs if available. Requires macOS + real PDFs."""
    pdf_dir = Path(__file__).parent / "fixtures" / "pdfs"
    pdfs = sorted(pdf_dir.glob("*.pdf"))

    if not pdfs:
        pytest.skip("No PDF files in test-pdfs/")

    from core.parser import parse_documents

    assets, transactions, dividends = parse_documents(pdfs, use_cache=False)
    assert len(assets) > 0
    assert len(transactions) + len(dividends) > 0
    assert all(isinstance(a, Asset) for a in assets.values())


@pytest.mark.skipif(not (Path(__file__).parent / "fixtures" / "pdfs").exists(), reason="No tests/fixtures/pdfs/ directory")
def test_real_pdf_golden_output():
    """Full pipeline on real PDFs: compare output against golden expected files.
    Requires macOS + real PDFs."""
    pdf_dir = Path(__file__).parent / "fixtures" / "pdfs"
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        pytest.skip("No PDF files in test-pdfs/")

    expected_dir = Path(__file__).parent / "fixtures" / "expected"
    expected_json = expected_dir / "tax_reports.json"
    expected_csv = expected_dir / "audit_trail.csv"
    if not expected_json.exists() or not expected_csv.exists():
        pytest.skip("Golden expected files not found")

    with open(expected_json) as f:
        expected_reports = json.load(f)

    from core.parser import parse_documents
    from core.calculator import compute_tax_data

    assets, _, _ = parse_documents(pdfs, use_cache=False)
    audit_rows, dashboards, _, _ = compute_tax_data(assets)

    for expected in expected_reports:
        year = expected["year"]
        dashboard = next((d for d in dashboards if d.year == year), None)
        assert dashboard is not None, f"Missing dashboard for year {year}"

        for exp_decl in expected["declarations"]:
            act_decl = next(
                d for d in dashboard.declarations
                if d.form == exp_decl["form"] and d.box == exp_decl["box"]
            )
            if exp_decl["box"] == "8UU":
                assert act_decl.value == 1
            else:
                assert act_decl.value == pytest.approx(exp_decl["value"], rel=0.01)

        assert len(dashboard.form_2047_details) == len(expected["form_2047_details"])
        for act, exp in zip(dashboard.form_2047_details, expected["form_2047_details"]):
            assert act["L202_Pays"] == exp["L202_Pays"]
            assert act["L203_Montant_net_encaisse"] == pytest.approx(exp["L203_Montant_net_encaisse"], rel=0.01)
            assert act["L206_Impot_supporte_etranger"] == pytest.approx(exp["L206_Impot_supporte_etranger"], rel=0.01)

    with open(expected_csv) as f:
        expected_rows = list(csv.DictReader(f))
    assert len(audit_rows) == len(expected_rows)
