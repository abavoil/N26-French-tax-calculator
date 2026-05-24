import os
import tempfile
import pytest


@pytest.fixture(autouse=True, scope="session")
def isolate_config():
    """Use an isolated temp directory for all config paths during tests."""
    tmp = tempfile.mkdtemp()
    os.environ["N26_APP_DIR"] = tmp
    yield
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


from datetime import datetime
from decimal import Decimal
from typing import Dict

from core.models import (
    Asset, BuyTransaction, SellTransaction, Dividend,
    TaxPosition, TaxYearDashboard, TaxDeclarationItem,
)


@pytest.fixture
def sample_buy() -> BuyTransaction:
    return BuyTransaction(
        document="/tmp/buy_order_test.pdf",
        statement_id="STMT001",
        event_time=datetime(2024, 1, 15, 10, 0, 0),
        quantity=Decimal("10"),
        price_per_unit=Decimal("150.00"),
        market_value=Decimal("1500.00"),
        net_cash_flow=Decimal("-1510.00"),
    )


@pytest.fixture
def sample_sell() -> SellTransaction:
    return SellTransaction(
        document="/tmp/sell_order_test.pdf",
        statement_id="STMT002",
        event_time=datetime(2024, 6, 15, 14, 30, 0),
        quantity=Decimal("5"),
        price_per_unit=Decimal("180.00"),
        market_value=Decimal("900.00"),
        net_cash_flow=Decimal("895.00"),
    )


@pytest.fixture
def sample_dividend() -> Dividend:
    return Dividend(
        document="/tmp/income_distribution_test.pdf",
        statement_id="STMT003",
        event_time=datetime(2024, 3, 1, 0, 0, 0),
        quantity=Decimal("10"),
        net_cash_flow=Decimal("80.00"),
        payment_per_unit=Decimal("10.00"),
        exchange_rate=Decimal("1.0"),
        gross_amount=Decimal("100.00"),
        tax=Decimal("20.00"),
    )


@pytest.fixture
def sample_asset(sample_buy, sample_sell, sample_dividend) -> Asset:
    return Asset(
        title="Test ETF",
        isin="US1234567890",
        ticker="TEST",
        transactions=[sample_buy, sample_sell],
        dividends=[sample_dividend],
    )


@pytest.fixture
def sample_dashboard() -> TaxYearDashboard:
    return TaxYearDashboard(
        year=2024,
        declarations=[
            TaxDeclarationItem("2042", "2DC", "Dividend Income", 100.0),
            TaxDeclarationItem("2042", "3VG", "Capital Gains", 150.0),
            TaxDeclarationItem("2042", "3VH", "Capital Losses", 0.0),
        ],
        form_2047_details=[],
    )


@pytest.fixture
def sample_positions() -> Dict[str, TaxPosition]:
    pos = TaxPosition(isin="US1234567890")
    pos.total_quantity = Decimal("5")
    pos.total_cost = Decimal("755.0")
    return {"US1234567890": pos}
