from decimal import Decimal
from datetime import datetime

from core.models import (
    Asset, BuyTransaction, SellTransaction, TaxPosition,
)

from core.calculator import compute_tax_data


def test_empty_assets():
    result = compute_tax_data({})
    assert result == ([], [], {}, {})


def test_single_buy(sample_buy):
    asset = Asset(title="Test", isin="US1234567890", transactions=[sample_buy])
    assets = {"US1234567890": asset}
    audit_rows, dashboards, positions_by_year, events_by_year = compute_tax_data(assets)

    assert len(audit_rows) == 1
    assert audit_rows[0]["Type"] == "Buy"
    assert audit_rows[0]["Quantity"] == float(sample_buy.quantity)

    assert len(dashboards) == 1
    assert dashboards[0].year == 2024

    pos = positions_by_year[2024]["US1234567890"]
    assert pos.total_quantity == Decimal("10")
    assert pos.total_cost == Decimal("1510.00")


def test_buy_then_sell(sample_buy, sample_sell):
    asset = Asset(
        title="Test", isin="US1234567890",
        transactions=[sample_buy, sample_sell],
    )
    assets = {"US1234567890": asset}
    audit_rows, dashboards, positions_by_year, events_by_year = compute_tax_data(assets)

    assert len(audit_rows) == 2

    pos = positions_by_year[2024]["US1234567890"]
    assert pos.total_quantity == Decimal("5")

    assert dashboards[0].declarations[1].box == "3VG"
    assert dashboards[0].declarations[1].value > 0


def test_buy_sell_buy_sequence():
    tx1 = BuyTransaction(
        document="a.pdf", statement_id="S1",
        event_time=datetime(2024, 1, 1, 0, 0, 0),
        quantity=Decimal("10"), price_per_unit=Decimal("100"),
        market_value=Decimal("1000"), net_cash_flow=Decimal("-1010"),
    )
    tx2 = SellTransaction(
        document="b.pdf", statement_id="S2",
        event_time=datetime(2024, 6, 1, 0, 0, 0),
        quantity=Decimal("5"), price_per_unit=Decimal("120"),
        market_value=Decimal("600"), net_cash_flow=Decimal("595"),
    )
    tx3 = BuyTransaction(
        document="c.pdf", statement_id="S3",
        event_time=datetime(2024, 12, 1, 0, 0, 0),
        quantity=Decimal("3"), price_per_unit=Decimal("110"),
        market_value=Decimal("330"), net_cash_flow=Decimal("-335"),
    )

    asset = Asset(
        title="Test", isin="DE1234567890",
        transactions=[tx1, tx2, tx3],
    )
    assets = {"DE1234567890": asset}
    audit_rows, dashboards, positions_by_year, events_by_year = compute_tax_data(assets)

    assert len(audit_rows) == 3

    pos = positions_by_year[2024]["DE1234567890"]
    assert pos.total_quantity == Decimal("8")

    assert pos.total_cost == Decimal("840.0")


def test_dividend_tracking(sample_dividend):
    asset = Asset(
        title="Test", isin="US1234567890",
        dividends=[sample_dividend],
    )
    assets = {"US1234567890": asset}
    audit_rows, dashboards, positions_by_year, events_by_year = compute_tax_data(assets)

    assert len(audit_rows) == 1
    assert audit_rows[0]["Type"] == "Dividend"

    assert dashboards[0].declarations[0].box == "2DC"
    assert dashboards[0].declarations[0].value == 100.0


def test_tax_year_report():
    buy1 = BuyTransaction(
        document="a.pdf", statement_id="S1",
        event_time=datetime(2024, 1, 1, 0, 0, 0),
        quantity=Decimal("10"), price_per_unit=Decimal("100"),
        market_value=Decimal("1000"), net_cash_flow=Decimal("-1010"),
    )
    sell1 = SellTransaction(
        document="b.pdf", statement_id="S2",
        event_time=datetime(2024, 6, 1, 0, 0, 0),
        quantity=Decimal("10"), price_per_unit=Decimal("150"),
        market_value=Decimal("1500"), net_cash_flow=Decimal("1490"),
    )

    asset = Asset(
        title="Test", isin="DE1234567890",
        transactions=[buy1, sell1],
    )
    assets = {"DE1234567890": asset}
    audit_rows, dashboards, positions_by_year, events_by_year = compute_tax_data(assets)

    gain_decl = [d for d in dashboards[0].declarations if d.box == "3VG"][0]
    assert gain_decl.value == 480.0

    loss_decl = [d for d in dashboards[0].declarations if d.box == "3VH"][0]
    assert loss_decl.value == 0.0


def test_multi_year():
    buy1 = BuyTransaction(
        document="a.pdf", statement_id="S1",
        event_time=datetime(2023, 12, 1, 0, 0, 0),
        quantity=Decimal("10"), price_per_unit=Decimal("100"),
        market_value=Decimal("1000"), net_cash_flow=Decimal("-1010"),
    )
    sell1 = SellTransaction(
        document="b.pdf", statement_id="S2",
        event_time=datetime(2024, 1, 15, 0, 0, 0),
        quantity=Decimal("5"), price_per_unit=Decimal("120"),
        market_value=Decimal("600"), net_cash_flow=Decimal("595"),
    )

    asset = Asset(
        title="Test", isin="FR1234567890",
        transactions=[buy1, sell1],
    )
    assets = {"FR1234567890": asset}
    audit_rows, dashboards, positions_by_year, events_by_year = compute_tax_data(assets)

    assert 2023 in positions_by_year
    assert 2024 in positions_by_year

    pos_2023 = positions_by_year[2023]["FR1234567890"]
    assert pos_2023.total_quantity == Decimal("10")

    pos_2024 = positions_by_year[2024]["FR1234567890"]
    assert pos_2024.total_quantity == Decimal("5")


def test_tax_position():
    pos = TaxPosition(isin="US123")
    pos.buy(Decimal("10"), Decimal("1000"))
    assert pos.total_quantity == Decimal("10")
    assert pos.total_cost == Decimal("1000")
    assert pos.pmp == Decimal("100")

    pos.sell(Decimal("5"))
    assert pos.total_quantity == Decimal("5")
    assert pos.total_cost == Decimal("500")
    assert pos.pmp == Decimal("100")

    pos.sell(Decimal("5"))
    assert pos.total_quantity == Decimal("0")
    assert pos.total_cost == Decimal("0")


def test_tax_position_sell_more_than_owned():
    pos = TaxPosition(isin="US123")
    pos.buy(Decimal("5"), Decimal("500"))
    pos.sell(Decimal("10"))
    assert pos.total_quantity == Decimal("0")


def test_pmp_unchanged_after_partial_sell():
    """French tax rule: PMP of remaining shares must be unchanged after a partial sale."""
    pos = TaxPosition(isin="FR123")
    pos.buy(Decimal("10"), Decimal("1000"))
    original_pmp = pos.pmp
    assert original_pmp == Decimal("100")

    pos.sell(Decimal("4"))
    assert pos.total_quantity == Decimal("6")
    assert pos.total_cost == Decimal("600")
    assert pos.pmp == Decimal("100")


def test_pmp_includes_fees():
    """French tax rule: acquisition fees are included in the PMP cost basis."""
    pos = TaxPosition(isin="FR123")
    pos.buy(Decimal("10"), Decimal("1000"))
    pos.buy(Decimal("5"), Decimal("520"))
    expected_pmp = Decimal("1520") / Decimal("15")
    assert pos.pmp == expected_pmp


def test_pmp_after_multiple_buys():
    pos = TaxPosition(isin="FR123")
    pos.buy(Decimal("10"), Decimal("1000"))
    assert pos.pmp == Decimal("100")
    pos.buy(Decimal("5"), Decimal("600"))
    expected = Decimal("1600") / Decimal("15")
    assert pos.pmp == expected


def test_calculator_pmp_matches_taxposition():
    """Verify the calculator's PMP tracking matches direct TaxPosition usage."""
    from datetime import datetime
    buy = BuyTransaction(
        document="a.pdf", statement_id="S1",
        event_time=datetime(2024, 1, 1, 0, 0, 0),
        quantity=Decimal("10"), price_per_unit=Decimal("100"),
        market_value=Decimal("1000"), net_cash_flow=Decimal("-1010"),
    )
    assets = {"FR123": Asset(title="Test", isin="FR123", transactions=[buy])}
    _, _, positions_by_year, _ = compute_tax_data(assets)
    pos = positions_by_year[2024]["FR123"]

    direct = TaxPosition(isin="FR123")
    direct.buy(Decimal("10"), Decimal("1010"))

    assert pos.total_quantity == direct.total_quantity
    assert pos.total_cost == direct.total_cost
    assert pos.pmp == direct.pmp


def test_pmp_gain_loss_audit():
    """PMP-based gain/loss appears correctly in audit rows."""
    buy = BuyTransaction(
        document="a.pdf", statement_id="S1",
        event_time=datetime(2024, 1, 1, 0, 0, 0),
        quantity=Decimal("10"), price_per_unit=Decimal("100"),
        market_value=Decimal("1000"), net_cash_flow=Decimal("-1010"),
    )
    sell = SellTransaction(
        document="b.pdf", statement_id="S2",
        event_time=datetime(2024, 6, 1, 0, 0, 0),
        quantity=Decimal("5"), price_per_unit=Decimal("150"),
        market_value=Decimal("750"), net_cash_flow=Decimal("745"),
    )
    asset = Asset(title="Test", isin="FR123", transactions=[buy, sell])
    audit_rows, _, _, _ = compute_tax_data({"FR123": asset})

    sell_row = audit_rows[1]
    assert "Gain/Loss" in sell_row["Notes"]
    assert sell_row["PMP"] == 101.0
    assert sell_row["Total_Qty"] == 5.0
