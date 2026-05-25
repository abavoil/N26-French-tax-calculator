import json
import logging
import pytest
from pathlib import Path
from decimal import Decimal
from datetime import datetime
from unittest.mock import patch

import core.parser as parser_mod
from core.parser import parse_decimal, parse_datetime, build_dividend, build_transaction, lookup_isin, parse_documents, Annotation
from utils.errors import OCRError


def test_parse_decimal_comma():
    assert parse_decimal("1,5") == Decimal("1.5")


def test_parse_decimal_dot():
    assert parse_decimal("3.14") == Decimal("3.14")


def test_parse_decimal_empty():
    assert parse_decimal("") == Decimal("0.0")


def test_parse_decimal_garbage():
    assert parse_decimal("abc") == Decimal("0.0")


def test_parse_decimal_currency():
    assert parse_decimal("1 234,56") == Decimal("1234.56")


def test_parse_datetime_full():
    result = parse_datetime("15.01.2024 10:30:00")
    assert result == datetime(2024, 1, 15, 10, 30, 0)


def test_parse_datetime_short():
    result = parse_datetime("15.01.2024")
    assert result == datetime(2024, 1, 15, 0, 0, 0)


def test_parse_datetime_invalid():
    from core.parser import parse_datetime
    try:
        parse_datetime("not a date")
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_build_dividend():
    d = {
        "document": "/tmp/test.pdf",
        "statement_id": "STMT001",
        "quantity": "10",
        "payment_per_unit": "5,50",
        "exchange_rate": "1.0",
        "gross_amount": "55,00",
        "tax": "11,00",
        "net_cash_flow": "44,00",
        "event_time": "01.03.2024",
    }
    div = build_dividend(d)
    assert div.quantity == Decimal("10")
    assert div.payment_per_unit == Decimal("5.50")
    assert div.exchange_rate == Decimal("1.0")
    assert div.gross_amount == Decimal("55.00")
    assert div.tax == Decimal("11.00")
    assert div.net_cash_flow == Decimal("44.00")
    assert div.event_time == datetime(2024, 3, 1, 0, 0, 0)


def test_build_buy_transaction():
    d = {
        "document": "/tmp/buy.pdf",
        "statement_id": "STMT002",
        "quantity": "10",
        "price_per_unit": "150,00",
        "market_value": "1500,00",
        "net_cash_flow": "1510,00",
        "event_time": "15.01.2024 10:00:00",
        "type": "buy",
    }
    tx = build_transaction(d)
    from core.models import BuyTransaction
    assert isinstance(tx, BuyTransaction)
    assert tx.quantity == Decimal("10")
    assert tx.price_per_unit == Decimal("150.00")
    assert tx.market_value == Decimal("1500.00")
    assert tx.net_cash_flow == Decimal("-1510.00")


def test_build_sell_transaction():
    d = {
        "document": "/tmp/sell.pdf",
        "statement_id": "STMT003",
        "quantity": "5",
        "price_per_unit": "180,00",
        "market_value": "900,00",
        "net_cash_flow": "895,00",
        "event_time": "15.06.2024 14:30:00",
        "type": "sell",
    }
    tx = build_transaction(d)
    from core.models import SellTransaction
    assert isinstance(tx, SellTransaction)
    assert tx.quantity == Decimal("5")
    assert tx.net_cash_flow == Decimal("895.00")


MOCK_YAHOO_RESPONSE = json.dumps({
    "quotes": [{
        "symbol": "MYTICK.PA", "longname": "Ma Societe Test SA",
        "exchange": "PAR", "quoteType": "EQUITY"
    }]
}).encode()


def _make_mock_urlopen(response_body):
    class MockResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return response_body
    return lambda req, **kw: MockResponse()


def _make_mock_annotations(statement_id: str = "STMT001") -> list:
    """Minimal mock annotations — enough to pass through get_closest_text without error."""
    return [
        Annotation("Montant", [0.5, 0.4, 0.04, 0.01]),
        Annotation(statement_id, [0.48, 0.789, 0.04, 0.01]),
        Annotation("EUR", [0.867, 0.384, 0.04, 0.01]),
    ]


def test_duplicate_document_skipped(monkeypatch, caplog):
    """Duplicate statement_id is skipped with a warning, no error raised."""
    FIXTURE_DIR = Path(__file__).parent / "fixtures" / "pdfs"
    buy_pdfs = sorted(FIXTURE_DIR.glob("buy_order_*.pdf"))
    original = buy_pdfs[0]
    copy = next((p for p in buy_pdfs if "copy" in p.name), None)
    assert copy is not None, "Expected a copy PDF (buy_order_*copy.pdf) in fixtures"

    monkeypatch.setattr("core.parser.annotate_page",
                        lambda page: _make_mock_annotations("DUP001"))
    monkeypatch.setattr(
        "core.parser.extract_base_data",
        lambda annotations, pdf_path, statement_id, doc_type: {
            "type": doc_type,
            "document": str(pdf_path),
            "statement_id": "DUP001",
            "asset_title": "Test Asset",
            "asset_isin": "FR0012345678",
            "quantity": "10",
            "montant_y": 0.4,
            "net_cash_flow": "100,00",
        },
    )
    monkeypatch.setattr(
        "core.parser.extract_transaction_data",
        lambda annotations, data: {**data,
            "price_per_unit": "150,00",
            "market_value": "1500,00",
            "event_time": "15.01.2024 10:30:00",
        },
    )
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, **kw: _make_mock_urlopen(b'{"quotes":[]}'))

    caplog.set_level(logging.WARNING)

    assets, transactions, dividends = parse_documents([original, copy], use_cache=False)

    assert len(assets) == 1
    assert len(transactions) == 1
    skip_msgs = [r.message for r in caplog.records if "Skipping duplicate" in r.message]
    assert len(skip_msgs) >= 1
    assert "copy" in skip_msgs[0].lower()
