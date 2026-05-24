"""
Robust PDF parser designed for flat PDF images using DPI-independent normalized coordinates.
"""

from pathlib import Path
import logging
import math
import re
import json
import urllib.request
from typing import Dict, List, Tuple
from decimal import Decimal
from datetime import datetime
import pickle

import pymupdf
from PIL import Image
from ocrmac import ocrmac

from utils.errors import (
    TaxCalcError, 
    PDFParsingError, 
    OCRError, 
    CoordinateExtractionError, 
    NonEURError
)
from config import OCR_CACHE_FILE
from core.models import Asset, Transaction, BuyTransaction, SellTransaction, Dividend

logger = logging.getLogger(__name__)

_CACHE_FILE = Path(__file__).parent / "cache_isin_to_ticker.json"
_isin_cache: Dict[str, Dict[str, str]] = {}

def _load_isin_cache():
    global _isin_cache
    if _CACHE_FILE.exists():
        with open(_CACHE_FILE) as f:
            _isin_cache = json.load(f)

def lookup_isin(isin: str) -> Tuple[str, str]:
    if not _isin_cache:
        _load_isin_cache()
    if isin not in _isin_cache:
        logger.info(f"Fetching ticker from Yahoo Finance for ISIN: {isin}")
        try:
            req = urllib.request.Request(
                f"https://query2.finance.yahoo.com/v1/finance/search?q={isin}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req) as resp:
                quotes = json.loads(resp.read()).get("quotes", [])
                if quotes:
                    _isin_cache[isin] = {
                        "symbol": quotes[0].get("symbol", isin),
                        "longname": quotes[0].get("longname", isin),
                    }
                else:
                    _isin_cache[isin] = {"symbol": isin, "longname": isin}
        except Exception:
            _isin_cache[isin] = {"symbol": isin, "longname": isin}
        try:
            _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_CACHE_FILE, "w") as f:
                json.dump(_isin_cache, f, indent=4)
        except Exception as e:
            logger.warning(f"Could not save ISIN cache: {e}")
    info = _isin_cache.get(isin, {})
    ticker = info.get("symbol", "") or isin
    longname = info.get("longname", "")
    return ticker, longname

# =========================================================================
# Structured Configuration (DPI-independent Normalized [0.0 - 1.0] Bounds)
# =========================================================================

class DocumentCoordinates:
    # Original coordinates mapped down to [0.0 - 1.0] scale
    account_number = (0.686, 0.728, "left")
    asset_title = (0.135, 0.620, "left")
    asset_isin = (0.864, 0.623, "right")
    quantity = (0.136, 0.574, "left")
    statement_id = (0.480, 0.789, "left")
    
    div_payment_per_unit = (0.386, 0.573, "left")
    div_exchange_rate = (0.800, 0.536, "right")
    
    tx_price_per_unit = (0.386, 0.573, "left")
    tx_market_value = (0.835, 0.574, "right")
    tx_event_time = (0.867, 0.517, "right")
    
    tx_eur_1 = (0.460, 0.574, "right")
    tx_eur_2 = (0.867, 0.574, "right")
    tx_sell_eur = (0.867, 0.442, "right")
    tx_sell_capital_gain = (0.835, 0.442, "right")

    @staticmethod
    def eur_gross(montant_y: float) -> Tuple[float, float, str]: 
        return 0.867, montant_y + 0.058, "right"
    @staticmethod
    def eur_tax(montant_y: float) -> Tuple[float, float, str]: 
        return 0.867, montant_y + 0.031, "right"
    @staticmethod
    def eur_net(montant_y: float) -> Tuple[float, float, str]: 
        return 0.867, montant_y - 0.016, "right"

    @staticmethod
    def div_gross_amount(montant_y: float) -> Tuple[float, float, str]: 
        return 0.835, montant_y + 0.058, "right"
    @staticmethod
    def div_tax(montant_y: float) -> Tuple[float, float, str]: 
        return 0.835, montant_y + 0.031, "right"
    @staticmethod
    def div_event_time(montant_y: float) -> Tuple[float, float, str]: 
        return 0.129, montant_y - 0.016, "left"

    @staticmethod
    def net_cash_flow(montant_y: float) -> Tuple[float, float, str]: 
        return 0.835, montant_y - 0.016, "right"


class Annotation:
    """Structured, DPI-independent text block normalized to [0.0 - 1.0]."""
    def __init__(self, text: str, bbox: List[float]):
        self.text = text
        # Input bbox values from ocrmac are already fractional coordinates [0.0 - 1.0]
        self.x = bbox[0]
        self.y = bbox[1]
        self.w = bbox[2]
        self.h = bbox[3]

    @property
    def x_mid(self) -> float:
        return self.x + (self.w / 2.0)

    def __repr__(self) -> str:
        return f"({self.text!r}, [{self.x:.3f}, {self.y:.3f}, {self.w:.3f}, {self.h:.3f}])"


# ==========================================
# Layout-Engine & OCR Logic
# ==========================================

def annotate_page(page: pymupdf.Page) -> List[Annotation]:
    """Render flattened PDF page to high-quality image and execute macOS OCR.

    Uses the livetext Vision framework only.  The default engine is NOT
    used as a fallback because it groups words into sentences, breaking
    the per-word coordinate extraction that the layout parser relies on.
    If livetext raises or returns empty the document cannot be processed
    (OCRError).  See ROADMAP.md "Known Issues" for details.
    """
    pix = page.get_pixmap()
    mode = "RGBA" if pix.alpha else "RGB"
    image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)

    raw_annotations = ocrmac.OCR(image, framework="livetext").recognize()

    annotations = []
    for text, conf, bbox in raw_annotations:
        if not text.strip():
            continue
        annotations.append(Annotation(text, bbox))

    logger.info(f"OCR extracted {len(raw_annotations)} raw segments, {len(annotations)} annotations")
    return annotations

def _get_anchor(annotations: List[Annotation], tx: float, ty: float, align: str) -> Annotation:
    def dist(a: Annotation) -> float:
        ax = a.x if align == "left" else a.x + a.w
        return math.hypot(ax - tx, a.y - ty)
    return min(annotations, key=dist)


def _extract_text(
    annotations: List[Annotation], 
    tx: float, 
    ty: float, 
    align: str, 
    merge_tol: float, 
    space_tol: float, 
    y_tol: float
) -> str:
    """Assembles neighboring word blocks horizontally based on a coordinate target."""
    if not annotations:
        raise ValueError("No annotations available")
    
    anchor = _get_anchor(annotations, tx, ty, align)
    row = sorted([a for a in annotations if abs(a.y - anchor.y) < y_tol], key=lambda a: a.x)
    idx = row.index(anchor)
    
    step = 1 if align == "left" else -1
    res = anchor.text
    curr = anchor
    
    for i in range(idx + step, len(row) if step == 1 else -1, step):
        nxt = row[i]
        if not nxt.text.strip(): 
            continue
        gap = nxt.x - (curr.x + curr.w) if step == 1 else curr.x - (nxt.x + nxt.w)
        
        if gap < merge_tol:
            res = res + nxt.text if step == 1 else nxt.text + res
        elif gap < space_tol:
            res = res + " " + nxt.text if step == 1 else nxt.text + " " + res
        else:
            break
        curr = nxt
        
    return res


def get_closest_text(annotations: List[Annotation], tx: float, ty: float, align: str = "left", merge_tol: float = 1e-9, y_tol: float = 0.005) -> str:
    # y_tol scaled down to [0.0 - 1.0] coordinates matching legacy 0.5% tolerance
    return _extract_text(annotations, tx, ty, align, merge_tol, merge_tol, y_tol)


def get_text_row(annotations: List[Annotation], tx: float, ty: float, align: str = "left", merge_tol: float = 0.0001, space_tol: float = 0.01, y_tol: float = 0.005) -> str:
    # tolerances scaled down to [0.0 - 1.0] coordinates (1% gap width merge limits)
    return _extract_text(annotations, tx, ty, align, merge_tol, space_tol, y_tol)


def detect_document_type(filename: str) -> str:
    if filename.startswith("buy_order_"):
        return "buy"
    elif filename.startswith("sell_order_"):
        return "sell"
    elif filename.startswith("income_distribution_"):
        return "dividend"
    else:
        raise ValueError(f"Unknown document type: {filename}")


# ==========================================
# Extraction Logic
# ==========================================

def extract_base_data(annotations: List[Annotation], pdf_path: Path, statement_id: str, doc_type: str) -> Dict:
    montant_headers = [a for a in annotations if "Montant" in a.text]
    if not montant_headers:
        raise ValueError("Could not locate 'Montant' layout anchor")
    montant_y = montant_headers[0].y
    
    data = {
        "type": doc_type,
        "document": str(pdf_path),
        "statement_id": statement_id,
        "account_number": get_closest_text(annotations, *DocumentCoordinates.account_number),
        "asset_title": get_text_row(annotations, *DocumentCoordinates.asset_title),
        "asset_isin": get_closest_text(annotations, *DocumentCoordinates.asset_isin),
        "quantity": get_text_row(annotations, *DocumentCoordinates.quantity),
        "montant_y": montant_y,
    }
    
    if get_closest_text(annotations, *DocumentCoordinates.eur_net(montant_y)) != "EUR":
        raise ValueError(f"Valeur non-EUR détectées dans {data['document']}")
        
    data["net_cash_flow"] = get_text_row(annotations, *DocumentCoordinates.net_cash_flow(montant_y))
    return data


def extract_dividend_data(annotations: List[Annotation], data: Dict) -> Dict:
    montant_y = data.pop("montant_y")
    if get_closest_text(annotations, *DocumentCoordinates.eur_gross(montant_y)) != "EUR":
        raise ValueError(f"Valeur non-EUR détectées dans {data['document']}")
    if get_closest_text(annotations, *DocumentCoordinates.eur_tax(montant_y)) != "EUR":
        raise ValueError(f"Valeur non-EUR détectées dans {data['document']}")

    data["payment_per_unit"] = get_text_row(annotations, *DocumentCoordinates.div_payment_per_unit)
    data["exchange_rate"] = get_text_row(annotations, *DocumentCoordinates.div_exchange_rate) \
            if any("Taux" in a.text for a in annotations) \
            else "1.0"
    data["gross_amount"] = get_text_row(annotations, *DocumentCoordinates.div_gross_amount(montant_y))
    data["tax"] = get_text_row(annotations, *DocumentCoordinates.div_tax(montant_y))
    data["event_time"] = get_closest_text(annotations, *DocumentCoordinates.div_event_time(montant_y))
    return data


def extract_transaction_data(annotations: List[Annotation], data: Dict) -> Dict:
    montant_y = data.pop("montant_y")
    if get_closest_text(annotations, *DocumentCoordinates.tx_eur_1) != "EUR":
        raise ValueError(f"Valeur non-EUR détectées dans {data['document']}")
    if get_closest_text(annotations, *DocumentCoordinates.tx_eur_2) != "EUR":
        raise ValueError(f"Valeur non-EUR détectées dans {data['document']}")

    data["price_per_unit"] = get_text_row(annotations, *DocumentCoordinates.tx_price_per_unit)
    data["market_value"] = get_text_row(annotations, *DocumentCoordinates.tx_market_value)
    data["event_time"] = get_text_row(annotations, *DocumentCoordinates.tx_event_time)
    
    if data["type"] == "sell":
        if get_closest_text(annotations, *DocumentCoordinates.tx_sell_eur) != "EUR":
            raise ValueError(f"Valeur non-EUR détectées dans {data['document']}")
        data["capital_gain"] = get_text_row(annotations, *DocumentCoordinates.tx_sell_capital_gain)
    return data


def parse_pdf_file(pdf_path: Path) -> Dict:
    """Parses single N26 file with direct coordinates extraction."""
    try:
        doc_type = detect_document_type(pdf_path.name)
    except ValueError as e:
        raise PDFParsingError(pdf_path.name, str(e))

    try:
        doc = pymupdf.open(pdf_path)
        raw_ann = annotate_page(doc[0])
        # Skip standard header information sitting in the top 10% of the page
        annotations = [a for a in raw_ann if a.y >= 0.10]
        doc.close()
        logger.info(f"{pdf_path.name}: {len(annotations)} usable annotations (filtered from {len(raw_ann)})")
    except Exception as e:
        logger.exception(f"System error while reading PDF or running OCR on {pdf_path.name}")
        raise OCRError(pdf_path.name)

    if not annotations:
        logger.error(f"OCR returned 0 annotations for {pdf_path.name}. Vision engine might have failed.")
        raise OCRError(pdf_path.name)

    # Resolve document contents based on layout configurations
    try:
        statement_id = get_closest_text(annotations, *DocumentCoordinates.statement_id)
        data = extract_base_data(annotations, pdf_path, statement_id, doc_type)
        
        if doc_type == "dividend":
            data = extract_dividend_data(annotations, data)
        else:
            data = extract_transaction_data(annotations, data)
            
    except ValueError as e:
        if "non-EUR" in str(e):
            raise NonEURError(pdf_path.name)
        raise CoordinateExtractionError(pdf_path.name, str(e))
    except Exception as e:
        raise CoordinateExtractionError(pdf_path.name, str(e))

    return data


# ==========================================
# Model Builders
# ==========================================

def parse_decimal(val: str) -> Decimal:
    cleaned = re.sub(r"[^0-9,.]", "", val).replace(",", ".")
    return Decimal(cleaned) if cleaned else Decimal("0.0")


def parse_datetime(val: str) -> datetime:
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    raise ValueError(f"Invalid date: {val}")


def build_dividend(d: Dict) -> Dividend:
    return Dividend(
        document=d["document"], statement_id=d["statement_id"],
        quantity=parse_decimal(d["quantity"]),
        payment_per_unit=parse_decimal(d["payment_per_unit"]),
        exchange_rate=parse_decimal(d["exchange_rate"]),
        gross_amount=parse_decimal(d["gross_amount"]),
        tax=parse_decimal(d["tax"]),
        net_cash_flow=parse_decimal(d["net_cash_flow"]),
        event_time=parse_datetime(d["event_time"]),
    )


def build_transaction(d: Dict) -> Transaction:
    base_kwargs = {
        "document": d["document"], "statement_id": d["statement_id"],
        "quantity": parse_decimal(d["quantity"]),
        "price_per_unit": parse_decimal(d["price_per_unit"]),
        "market_value": parse_decimal(d["market_value"]),
        "net_cash_flow": parse_decimal(d["net_cash_flow"]) * (Decimal("-1") if d["type"] == "buy" else Decimal("1")),
        "event_time": parse_datetime(d["event_time"]),
    }
    if d["type"] == "buy":
        return BuyTransaction(**base_kwargs)
    elif d["type"] == "sell":
        pdf_gain = parse_decimal(d.get("capital_gain", "0"))
        return SellTransaction(**base_kwargs, _pdf_capital_gain=pdf_gain)


# ==========================================
# Interface Adaptor for Web Pipeline
# ==========================================
def parse_documents(pdf_paths: List[Path], use_cache: bool = True, progress_callback=None) -> Tuple[Dict, Dict, Dict]:
    """
    Parse multiple PDF files, utilizing an incremental raw annotation cache.
    Args:
        pdf_paths: List of PDF file paths
        use_cache: Whether to use the OCR annotation cache
        progress_callback: Optional callable(current, total, filename) called per file
    """
    logger.info(f"Parsing {len(pdf_paths)} PDF files")
    
    # 1. Load existing OCR annotations cache
    annotation_cache = {}
    if use_cache and OCR_CACHE_FILE.exists():
        try:
            with open(OCR_CACHE_FILE, 'rb') as f:
                annotation_cache = pickle.load(f)
            logger.info(f"Loaded {len(annotation_cache)} cached document annotations")
        except Exception as e:
            logger.warning(f"Cache load failed: {e}. Starting fresh...")

    all_data = []
    seen_statement_ids = set()
    cache_updated = False
    
    for i, pdf_path in enumerate(pdf_paths, 1):
        if progress_callback:
            progress_callback(i, len(pdf_paths), pdf_path.name)
        try:
            data = None
            # Compute a unique identifier for the file (e.g., filename + size) to prevent collisions
            file_key = f"{pdf_path.name}_{pdf_path.stat().st_size}"

            # Check if we have the RAW annotations for this file cached
            if use_cache and file_key in annotation_cache:
                logger.info(f"[{i}/{len(pdf_paths)}] OCR Cache HIT for {pdf_path.name}")
                annotations = annotation_cache[file_key]
                
                # Re-run coordinate extraction on cached text (instant)
                try:
                    statement_id = get_closest_text(annotations, *DocumentCoordinates.statement_id)
                    data = extract_base_data(annotations, pdf_path, statement_id, detect_document_type(pdf_path.name))
                    if data["type"] == "dividend":
                        data = extract_dividend_data(annotations, data)
                    else:
                        data = extract_transaction_data(annotations, data)
                except Exception as e:
                    logger.warning(f"Failed to extract fields from cached annotations for {pdf_path.name}: {e}. Re-running OCR...")
                    data = None

            # If no cache hit, run OCR
            if data is None:
                logger.info(f"[{i}/{len(pdf_paths)}] OCR Cache MISS - Running OCR for {pdf_path.name}")
                # Open PDF and generate annotations
                doc = pymupdf.open(pdf_path)
                raw_ann = annotate_page(doc[0])
                annotations = [a for a in raw_ann if a.y >= 0.10]
                doc.close()
                logger.info(f"[{i}/{len(pdf_paths)}] {pdf_path.name}: {len(annotations)} annotations (filtered from {len(raw_ann)})")

                if not annotations:
                    raise OCRError(pdf_path.name)

                # Extract data
                statement_id = get_closest_text(annotations, *DocumentCoordinates.statement_id)
                data = extract_base_data(annotations, pdf_path, statement_id, detect_document_type(pdf_path.name))
                if data["type"] == "dividend":
                    data = extract_dividend_data(annotations, data)
                else:
                    data = extract_transaction_data(annotations, data)

                # Save raw annotations to cache map
                annotation_cache[file_key] = annotations
                cache_updated = True

            # Check for duplicates within this run
            stmt_id = data['statement_id']
            if stmt_id in seen_statement_ids:
                logger.warning(f"Skipping duplicate: {pdf_path.name} (statement ID: {stmt_id})")
                continue
            seen_statement_ids.add(stmt_id)
            all_data.append(data)
            
        except TaxCalcError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error parsing {pdf_path.name}: {e}")
            raise PDFParsingError(pdf_path.name, str(e))
    
    if not all_data:
        from utils.errors import NoValidDocumentsError
        raise NoValidDocumentsError(len(pdf_paths))
    
    # Write updated annotations cache back to disk
    if cache_updated:
        try:
            OCR_CACHE_FILE.parent.mkdir(exist_ok=True)
            with open(OCR_CACHE_FILE, 'wb') as f:
                pickle.dump(annotation_cache, f)
            logger.info("OCR annotations cache updated on disk")
        except Exception as e:
            logger.warning(f"Could not save updated OCR cache: {e}")

    # Build model objects
    assets: Dict[str, Asset] = {}
    transactions: Dict[str, Transaction] = {}
    dividends: Dict[str, Dividend] = {}

    for d in all_data:
        isin = d["asset_isin"]
        if isin not in assets:
            ticker, longname = lookup_isin(isin)
            assets[isin] = Asset(title=d["asset_title"], isin=isin, ticker=ticker, longname=longname)

        if d["type"] == "dividend":
            div = build_dividend(d)
            assets[isin].dividends.append(div)
            dividends[div.document] = div
        else:
            tx = build_transaction(d)
            assets[isin].transactions.append(tx)
            transactions[tx.document] = tx

    return (assets, transactions, dividends)