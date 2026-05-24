import json
import pytest
from pathlib import Path
from decimal import Decimal
from datetime import datetime
from unittest.mock import patch

import core.parser as parser_mod
from core.parser import parse_decimal, parse_datetime, build_dividend, build_transaction, lookup_isin, parse_documents
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


def test_lookup_isin_cache_miss_hit(monkeypatch, tmp_path):
    cache_file = tmp_path / "cache_isin_to_ticker.json"
    monkeypatch.setattr(parser_mod, "_CACHE_FILE", cache_file)
    monkeypatch.setattr(parser_mod, "_isin_cache", {})

    api_calls = []
    def tracking_urlopen(req, **kw):
        api_calls.append(req.full_url)
        body = MOCK_YAHOO_RESPONSE if "FR0012345678" in req.full_url else b'{"quotes":[]}'
        return _make_mock_urlopen(body)(req)
    monkeypatch.setattr("urllib.request.urlopen", tracking_urlopen)

    ticker, longname = lookup_isin("FR0012345678")
    assert ticker == "MYTICK.PA"
    assert longname == "Ma Societe Test SA"
    assert len(api_calls) == 1
    assert cache_file.exists()

    cached = json.loads(cache_file.read_text())
    assert cached["FR0012345678"]["symbol"] == "MYTICK.PA"
    assert cached["FR0012345678"]["longname"] == "Ma Societe Test SA"

    ticker2, longname2 = lookup_isin("FR0012345678")
    assert ticker2 == "MYTICK.PA"
    assert longname2 == "Ma Societe Test SA"
    assert len(api_calls) == 1

    monkeypatch.setattr(parser_mod, "_isin_cache", {})
    ticker3, longname3 = lookup_isin("FR0012345678")
    assert ticker3 == "MYTICK.PA"
    assert longname3 == "Ma Societe Test SA"
    assert len(api_calls) == 1


def test_lookup_isin_api_failure_fallback(monkeypatch, tmp_path):
    cache_file = tmp_path / "cache_fallback.json"
    monkeypatch.setattr(parser_mod, "_CACHE_FILE", cache_file)
    monkeypatch.setattr(parser_mod, "_isin_cache", {})

    def failing_urlopen(req, **kw):
        raise OSError("Network unreachable")
    monkeypatch.setattr("urllib.request.urlopen", failing_urlopen)

    ticker, longname = lookup_isin("US0000000001")
    assert ticker == "US0000000001"
    assert longname == "US0000000001"
    assert cache_file.exists()

    cached = json.loads(cache_file.read_text())
    assert cached["US0000000001"]["symbol"] == "US0000000001"


def test_lookup_isin_no_quotes_from_api(monkeypatch, tmp_path):
    cache_file = tmp_path / "cache_noquotes.json"
    monkeypatch.setattr(parser_mod, "_CACHE_FILE", cache_file)
    monkeypatch.setattr(parser_mod, "_isin_cache", {})

    empty_response = _make_mock_urlopen(b'{"quotes":[]}')
    monkeypatch.setattr("urllib.request.urlopen", empty_response)

    ticker, longname = lookup_isin("DE0000000001")
    assert ticker == "DE0000000001"
    assert longname == "DE0000000001"


def test_ocr_empty_annotations_raises_ocerror(monkeypatch):
    """OCRError is raised when annotate_page returns no annotations."""
    FIXTURE_DIR = Path(__file__).parent / "fixtures" / "pdfs"
    pdf_path = list(FIXTURE_DIR.glob("buy_order_*.pdf"))[0]

    monkeypatch.setattr("core.parser.annotate_page", lambda page: [])

    with pytest.raises(OCRError, match="Could not extract text"):
        parse_documents([pdf_path], use_cache=False)
