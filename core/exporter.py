from pathlib import Path
from typing import Dict, List, Any
from decimal import Decimal
import logging

try:
    import pandas as pd
except ImportError:
    pd = None

from core.models import Asset, TaxYearDashboard, BuyTransaction, SellTransaction, Dividend

logger = logging.getLogger(__name__)


def export_to_excel(
    assets: Dict[str, Asset],
    filepath: Path,
    dashboards: List[TaxYearDashboard],
    audit_rows: List,
    positions: Dict[str, Any],
    year_events: List[tuple],
    year: int,
) -> None:
    if pd is None:
        logger.error("pandas not available, skipping Excel export")
        return

    logger.info(f"Exporting to Excel: {filepath}")

    def _round2(x):
        return float(round(x, 2)) if isinstance(x, (int, float, Decimal)) else x

    try:
        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            dashboard = dashboards[0] if dashboards else None
            if dashboard:
                tax_data = [
                    {
                        "Année": year,
                        "Formulaire": item.form,
                        "Case": item.box,
                        "Description": item.description,
                        "Valeur": item.value,
                    }
                    for item in dashboard.declarations
                ]
                pd.DataFrame(tax_data).to_excel(writer, sheet_name="Déclarations", index=False)

                if dashboard.form_2047_details:
                    pd.DataFrame(dashboard.form_2047_details).to_excel(
                        writer, sheet_name="Détails_2047", index=False
                    )

            pos_list = []
            for isin, pos in (positions or {}).items():
                if hasattr(pos, "total_quantity") and pos.total_quantity > 0:
                    pos_list.append({
                        "ISIN": isin,
                        "Ticker": assets[isin].ticker if isin in assets else "",
                        "Quantity": _round2(pos.total_quantity),
                        "Total_Cost": _round2(pos.total_cost),
                    })
            df_pos = pd.DataFrame(
                sorted(pos_list, key=lambda x: x["Ticker"])
            ) if pos_list else pd.DataFrame(columns=["ISIN", "Ticker", "Quantity", "Total_Cost"])
            df_pos.to_excel(writer, sheet_name="Actifs_Restants", index=False)

            buys, sells, divs = [], [], []
            for ev, isin in year_events or []:
                asset = assets.get(isin)
                ticker = asset.ticker if asset else ""
                base = {
                    "Date": ev.event_time.strftime("%Y-%m-%d"),
                    "Ticker": ticker,
                }
                if isinstance(ev, BuyTransaction):
                    base.update({
                        "Price_per_unit": _round2(ev.price_per_unit),
                        "Units": _round2(ev.quantity),
                        "Market_Value": _round2(ev.market_value),
                        "Fees": _round2(ev.tax_and_fees),
                    })
                    buys.append(base)
                elif isinstance(ev, SellTransaction):
                    base.update({
                        "Price_per_unit": _round2(ev.price_per_unit),
                        "Units": _round2(ev.quantity),
                        "Market_Value": _round2(ev.market_value),
                        "Fees": _round2(ev.tax_and_fees),
                        "Plus_Value": _round2(getattr(ev, "capital_gain", 0)),
                    })
                    sells.append(base)
                elif isinstance(ev, Dividend):
                    base.update({
                        "Units": _round2(ev.quantity),
                        "Dividends_per_unit": _round2(ev.payment_per_unit),
                        "Taxed": _round2(ev.tax),
                        "Revenu_Total": _round2(ev.gross_amount),
                        "Pays_Emetteur": isin[:2] if isin else "",
                    })
                    divs.append(base)

            def to_df(data, cols):
                return (
                    pd.DataFrame(sorted(data, key=lambda x: x["Date"]))
                    if data else pd.DataFrame(columns=cols)
                )

            to_df(buys, ["Date", "Ticker", "Price_per_unit", "Units", "Market_Value", "Fees"]).to_excel(
                writer, sheet_name="Achats", index=False
            )
            to_df(sells, ["Date", "Ticker", "Price_per_unit", "Units", "Market_Value", "Fees", "Plus_Value"]).to_excel(
                writer, sheet_name="Ventes", index=False
            )
            to_df(divs, ["Date", "Ticker", "Units", "Dividends_per_unit", "Taxed", "Revenu_Total", "Pays_Emetteur"]).to_excel(
                writer, sheet_name="Dividendes", index=False
            )

        logger.info(f"Successfully exported to {filepath}")
    except Exception as e:
        logger.error(f"Excel export failed: {e}")
        raise
