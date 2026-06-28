"""Tax engine: apply a TaxRuleset to an entity's financials → obligations."""
from __future__ import annotations
from dataclasses import dataclass, field
from vank.fieldledger.ruleset import TaxRuleset

__all__ = ["TaxObligation", "TaxEngine"]

# Maps parameter key prefixes/names to the financial input key.
_BASE_MAP: dict[str, str] = {
    "corporate_income_tax": "gross_profit",
    "income_tax": "taxable_income",
    "payroll_employee": "gross_salary",
    "payroll_employer": "gross_salary",
    "vat_standard": "vat_turnover",
}

@dataclass
class TaxObligation:
    jurisdiction: str
    fiscal_year: int
    entity_id: str
    items: dict[str, float] = field(default_factory=dict)  # {parameter_key: amount_due}
    notes: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return sum(self.items.values())

    def to_dict(self) -> dict:
        return {
            "jurisdiction": self.jurisdiction,
            "fiscal_year": self.fiscal_year,
            "entity_id": self.entity_id,
            "items": self.items,
            "total": self.total,
            "notes": self.notes,
        }


class TaxEngine:
    def __init__(self, ruleset: TaxRuleset) -> None:
        self.ruleset = ruleset

    def compute(self, entity_id: str, financials: dict[str, float]) -> TaxObligation:
        """Apply all parameters in the ruleset to financials, return an obligation.

        financials keys:
          gross_profit    → corporate_income_tax
          taxable_income  → income_tax
          gross_salary    → payroll_employee, payroll_employer
          vat_turnover    → vat_standard
        Unknown parameter keys fall back to a direct key match in financials.
        """
        obl = TaxObligation(
            jurisdiction=self.ruleset.jurisdiction_code,
            fiscal_year=self.ruleset.fiscal_year,
            entity_id=entity_id,
        )
        for key, param in self.ruleset.parameters.items():
            # Resolve the base amount: try explicit map first, then direct key match.
            base_key = _BASE_MAP.get(key, key)
            base = financials.get(base_key, 0.0)
            amount = param.compute(base)
            obl.items[key] = amount
            if param.notes:
                obl.notes.append(f"{key}: {param.notes}")
        return obl
