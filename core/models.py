from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime
from typing import List, Dict


@dataclass
class FinancialEvent:
    document: str
    statement_id: str
    event_time: datetime
    quantity: Decimal
    net_cash_flow: Decimal


@dataclass
class Transaction(FinancialEvent):
    price_per_unit: Decimal
    market_value: Decimal

    @property
    def tax_and_fees(self) -> Decimal:
        return abs(abs(self.net_cash_flow) - self.market_value)


@dataclass
class BuyTransaction(Transaction):
    pass


@dataclass
class SellTransaction(Transaction):
    _pdf_capital_gain: Decimal = Decimal("0.0")


@dataclass
class Dividend(FinancialEvent):
    payment_per_unit: Decimal
    exchange_rate: Decimal
    gross_amount: Decimal
    tax: Decimal


@dataclass
class Asset:
    title: str
    isin: str
    ticker: str = ""
    longname: str = ""
    transactions: List[Transaction] = field(default_factory=list)
    dividends: List[Dividend] = field(default_factory=list)


@dataclass
class TaxPosition:
    isin: str
    total_quantity: Decimal = Decimal("0.0")
    total_cost: Decimal = Decimal("0.0")

    @property
    def pmp(self) -> Decimal:
        return self.total_cost / self.total_quantity if self.total_quantity > 0 else Decimal("0.0")

    def buy(self, qty: Decimal, cost: Decimal) -> None:
        self.total_quantity += qty
        self.total_cost += cost

    def sell(self, qty: Decimal) -> None:
        if self.total_quantity <= 0:
            return
        basis_cost = self.total_cost * (qty / self.total_quantity)
        self.total_quantity -= qty
        self.total_cost -= basis_cost
        if self.total_quantity <= Decimal("1e-9"):
            self.total_quantity = Decimal("0.0")
            self.total_cost = Decimal("0.0")


COUNTRY_NAMES = {
    "US": "États-Unis", "DE": "Allemagne", "GB": "Royaume-Uni",
    "NL": "Pays-Bas", "CH": "Suisse", "IE": "Irlande",
    "LU": "Luxembourg", "CN": "Chine", "FR": "France",
}


@dataclass
class TaxDeclarationItem:
    form: str
    box: str
    description: str
    value: float


@dataclass
class TaxYearDashboard:
    year: int
    declarations: List[TaxDeclarationItem]
    form_2047_details: List[Dict]
