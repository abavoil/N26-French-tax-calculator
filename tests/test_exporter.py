from pathlib import Path
from decimal import Decimal
from datetime import datetime
import tempfile

from core.models import (
    Asset, BuyTransaction, SellTransaction,
)
from core.exporter import export_to_excel


def _make_asset(ticker: str = "TEST") -> Asset:
    tx1 = BuyTransaction(
        document=f"/tmp/{ticker}_buy.pdf", statement_id="S1",
        event_time=datetime(2024, 1, 15, 10, 0, 0),
        quantity=Decimal("10"), price_per_unit=Decimal("100"),
        market_value=Decimal("1000"), net_cash_flow=Decimal("-1010"),
    )
    return Asset(title="Test Asset", isin="US1234567890", ticker=ticker, transactions=[tx1])


def _make_sell() -> SellTransaction:
    t = SellTransaction(
        document="/tmp/sell.pdf", statement_id="S2",
        event_time=datetime(2024, 6, 15, 14, 0, 0),
        quantity=Decimal("5"), price_per_unit=Decimal("150"),
        market_value=Decimal("750"), net_cash_flow=Decimal("745"),
        _pdf_capital_gain=Decimal("250"),
    )
    t.capital_gain = Decimal("250")
    return t


def test_export_creates_file(sample_dashboard, sample_positions):
    assets = {"US1234567890": _make_asset()}
    asset_sell = _make_sell()

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = Path(f.name)

    try:
        positions = sample_positions
        year_events = [(asset_sell, "US1234567890")]

        export_to_excel(
            assets, path, [sample_dashboard], [],
            positions, year_events, 2024,
        )
        assert path.exists()
        assert path.stat().st_size > 0
    finally:
        path.unlink(missing_ok=True)


def test_export_empty_assets():
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = Path(f.name)

    try:
        export_to_excel(
            {}, path, [], [],
            {}, [], 2024,
        )
        assert path.exists()
    finally:
        path.unlink(missing_ok=True)


def test_export_with_dividends(sample_dividend, sample_dashboard, sample_positions):
    assets = {"US1234567890": _make_asset()}
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = Path(f.name)

    try:
        year_events = [(sample_dividend, "US1234567890")]
        export_to_excel(
            assets, path, [sample_dashboard], [],
            sample_positions, year_events, 2024,
        )
        assert path.exists()
    finally:
        path.unlink(missing_ok=True)
