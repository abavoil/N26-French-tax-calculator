from typing import Dict, List, Tuple, Any
from decimal import Decimal
from collections import defaultdict
from pathlib import Path
import copy
import logging

from core.models import (
    Asset, Transaction, BuyTransaction, Dividend,
    TaxPosition, TaxYearDashboard, TaxDeclarationItem, COUNTRY_NAMES,
)

logger = logging.getLogger(__name__)


class TaxYearReport:
    def __init__(self, year: int):
        self.year = year
        self.gross_divs_by_country: Dict[str, Decimal] = defaultdict(Decimal)
        self.net_divs_by_country: Dict[str, Decimal] = defaultdict(Decimal)
        self.tax_credit_by_country: Dict[str, Decimal] = defaultdict(Decimal)
        self.capital_gains = Decimal("0.0")
        self.capital_losses = Decimal("0.0")


def compute_tax_data(assets: Dict[str, Asset]) -> Tuple[List, List, Dict, Dict]:
    events = [
        (ev.event_time, ev, isin)
        for isin, asset in assets.items()
        for ev in asset.transactions + asset.dividends
    ]
    events.sort(key=lambda x: x[0])

    positions: Dict[str, TaxPosition] = {}
    reports: Dict[int, TaxYearReport] = {}
    audit_rows = []
    positions_by_year: Dict[int, Dict[str, TaxPosition]] = {}
    events_by_year: Dict[int, List[tuple]] = defaultdict(list)

    if not events:
        return [], [], {}, {}

    current_year = events[0][0].year

    for date, event, isin in events:
        year = date.year
        while current_year < year:
            positions_by_year[current_year] = copy.deepcopy(positions)
            current_year += 1

        if year not in reports:
            reports[year] = TaxYearReport(year)
        if isin not in positions:
            positions[isin] = TaxPosition(isin)

        pos = positions[isin]
        country = isin[:2]
        report = reports[year]
        events_by_year[year].append((event, isin))

        ticker = assets[isin].ticker or ""
        event_type = type(event).__name__.replace("Transaction", "")

        audit_row: Dict[str, Any] = {
            "Date": date.strftime("%Y-%m-%d"),
            "Ticker": ticker,
            "Type": event_type,
            "Quantity": float(event.quantity),
            "Price_per_unit": Decimal("0.0"),
            "Net_cash_flow": float(event.net_cash_flow),
            "Fees": Decimal("0.0"),
            "Currency": "EUR",
            "Total_Qty": float(pos.total_quantity),
            "PMP": float(pos.pmp),
            "Notes": f"Doc: {Path(event.document).name}",
        }

        if isinstance(event, Transaction):
            audit_row["Price_per_unit"] = float(event.price_per_unit)
            audit_row["Fees"] = float(event.tax_and_fees)

            if isinstance(event, BuyTransaction):
                pos.buy(event.quantity, event.market_value + event.tax_and_fees)
            else:
                actual_cost = Decimal("0.0")
                if pos.total_quantity > 0:
                    actual_cost = pos.total_cost * (event.quantity / pos.total_quantity)
                pos.sell(event.quantity)
                gain_loss = event.net_cash_flow - actual_cost
                if gain_loss >= 0:
                    report.capital_gains += gain_loss
                else:
                    report.capital_losses -= gain_loss
                event.capital_gain = float(gain_loss)
                audit_row["Notes"] += f" | Gain/Loss: {gain_loss:.2f}"

        elif isinstance(event, Dividend):
            report.gross_divs_by_country[country] += event.gross_amount
            report.net_divs_by_country[country] += event.net_cash_flow
            report.tax_credit_by_country[country] += event.tax
            audit_row["Notes"] += f" | Gross: {event.gross_amount:.2f} | Tax: {event.tax:.2f}"

        audit_row["Total_Qty"] = float(pos.total_quantity)
        audit_row["PMP"] = float(pos.pmp)
        audit_rows.append(audit_row)

    positions_by_year[current_year] = copy.deepcopy(positions)

    def _round2(x):
        return float(round(x, 2))
    yearly_dashboards = []

    for year, report in sorted(reports.items()):
        net_result = report.capital_gains - report.capital_losses
        gain = max(Decimal("0.0"), net_result)
        loss = max(Decimal("0.0"), -net_result)

        total_gross_divs = sum(report.gross_divs_by_country.values())
        total_tax_credit = sum(report.tax_credit_by_country.values())

        declarations = [
            TaxDeclarationItem("2042", "2DC", "Revenus des actions et parts", _round2(total_gross_divs)),
            TaxDeclarationItem("2042", "3VG", "Plus-values de cession de valeurs mobilières", _round2(gain)),
            TaxDeclarationItem("2042", "3VH", "Moins-values de cession de valeurs mobilières", _round2(loss)),
            TaxDeclarationItem("2042", "8VL", "Crédits d'impôt sur valeurs étrangères", _round2(total_tax_credit)),
            TaxDeclarationItem("2042", "8UU", "Comptes ouverts, détenus, utilisés ou clos à l'étranger", 1),
            TaxDeclarationItem("2047", "L260", "Récapitulatif des dividendes", _round2(total_gross_divs)),
            TaxDeclarationItem("2047", "L30", "Plus-values étrangères (report en 3VG)", _round2(gain)),
            TaxDeclarationItem("2074", "L21", "Plus-values", _round2(gain)),
        ]

        form_2047_details = [
            {
                "L202_Pays": COUNTRY_NAMES.get(c, c),
                "L203_Montant_net_encaisse": _round2(report.net_divs_by_country[c]),
                "L204_Taux_applicable": "cf. Annexe",
                "L205_Resultat": "L203*L204",
                "L206_Impot_supporte_etranger": _round2(report.tax_credit_by_country[c]),
                "L207_Credit_impot_retenu": "min(L205, L206)",
            }
            for c in report.gross_divs_by_country
            if c != "FR"
        ]

        yearly_dashboards.append(TaxYearDashboard(year, declarations, form_2047_details))

    return audit_rows, yearly_dashboards, positions_by_year, events_by_year
