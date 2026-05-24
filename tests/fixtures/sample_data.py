"""
Factory functions for realistic test data mimicking N26 statements.
"""

from decimal import Decimal
from datetime import datetime
from typing import Dict

from core.models import Asset, BuyTransaction, SellTransaction, Dividend


def make_us_stock_portfolio() -> Dict[str, Asset]:
    """Create a realistic portfolio with a US stock (Apple)."""
    isin = "US0378331005"  # Apple
    asset = Asset(title="APPLE INC.", isin=isin, ticker="AAPL")

    # Buy 10 shares at $150 each + $10 fees
    asset.transactions.append(
        BuyTransaction(
            document="/tmp/buy_order_aapl_1.pdf",
            statement_id="STMT001",
            event_time=datetime(2024, 1, 15, 10, 30, 0),
            quantity=Decimal("10"),
            price_per_unit=Decimal("150.00"),
            market_value=Decimal("1500.00"),
            net_cash_flow=Decimal("-1510.00"),
        )
    )

    # Buy 5 more shares at $160 each + $8 fees
    asset.transactions.append(
        BuyTransaction(
            document="/tmp/buy_order_aapl_2.pdf",
            statement_id="STMT002",
            event_time=datetime(2024, 3, 20, 14, 15, 0),
            quantity=Decimal("5"),
            price_per_unit=Decimal("160.00"),
            market_value=Decimal("800.00"),
            net_cash_flow=Decimal("-808.00"),
        )
    )

    # Sell 3 shares at $180 each - $6 fees
    asset.transactions.append(
        SellTransaction(
            document="/tmp/sell_order_aapl_1.pdf",
            statement_id="STMT003",
            event_time=datetime(2024, 6, 10, 9, 45, 0),
            quantity=Decimal("3"),
            price_per_unit=Decimal("180.00"),
            market_value=Decimal("540.00"),
            net_cash_flow=Decimal("534.00"),
        )
    )

    return {isin: asset}


def make_euro_etf_portfolio() -> Dict[str, Asset]:
    """Create a portfolio with a EUR-listed ETF."""
    isin = "FR0010315770"  # Lyxor MSCI World
    asset = Asset(title="LYXOR MSCI WORLD", isin=isin, ticker="EWLD")

    asset.transactions.append(
        BuyTransaction(
            document="/tmp/buy_order_etf_1.pdf",
            statement_id="STMT010",
            event_time=datetime(2024, 2, 1, 11, 0, 0),
            quantity=Decimal("20"),
            price_per_unit=Decimal("45.50"),
            market_value=Decimal("910.00"),
            net_cash_flow=Decimal("-915.00"),
        )
    )

    return {isin: asset}


def make_dividend_portfolio() -> Dict[str, Asset]:
    """Create a portfolio with a dividend payment."""
    isin = "US0378331005"
    asset = Asset(title="APPLE INC.", isin=isin, ticker="AAPL")

    # First the buy
    asset.transactions.append(
        BuyTransaction(
            document="/tmp/buy_order_aapl_1.pdf",
            statement_id="STMT020",
            event_time=datetime(2024, 1, 15, 10, 0, 0),
            quantity=Decimal("20"),
            price_per_unit=Decimal("150.00"),
            market_value=Decimal("3000.00"),
            net_cash_flow=Decimal("-3010.00"),
        )
    )

    # Then dividend
    asset.dividends.append(
        Dividend(
            document="/tmp/income_distribution_aapl.pdf",
            statement_id="STMT021",
            event_time=datetime(2024, 5, 15, 0, 0, 0),
            quantity=Decimal("20"),
            payment_per_unit=Decimal("0.24"),
            exchange_rate=Decimal("1.08"),
            gross_amount=Decimal("4.44"),
            tax=Decimal("0.89"),
            net_cash_flow=Decimal("3.55"),
        )
    )

    return {isin: asset}


def make_multi_year_portfolio() -> Dict[str, Asset]:
    """Portfolio with transactions spanning two years."""
    isin = "DE000BASF111"
    asset = Asset(title="BASF SE", isin=isin, ticker="BAS")

    # Buy in 2023
    asset.transactions.append(
        BuyTransaction(
            document="/tmp/buy_order_basf_2023.pdf",
            statement_id="STMT030",
            event_time=datetime(2023, 11, 10, 10, 0, 0),
            quantity=Decimal("15"),
            price_per_unit=Decimal("48.00"),
            market_value=Decimal("720.00"),
            net_cash_flow=Decimal("-725.00"),
        )
    )

    # Partial sell in 2024
    asset.transactions.append(
        SellTransaction(
            document="/tmp/sell_order_basf_2024.pdf",
            statement_id="STMT031",
            event_time=datetime(2024, 3, 5, 14, 0, 0),
            quantity=Decimal("5"),
            price_per_unit=Decimal("52.00"),
            market_value=Decimal("260.00"),
            net_cash_flow=Decimal("257.00"),
        )
    )

    return {isin: asset}
