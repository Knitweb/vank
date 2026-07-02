"""CID-addressable tax ruleset (OpenFisca two-layer pattern, JSON serialisable)."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

__all__ = ["BracketType", "TaxBracket", "TaxParameter", "TaxRuleset"]

class BracketType(Enum):
    MARGINAL_RATE = "marginal_rate"       # progressive brackets: rate applies to slice
    MARGINAL_AMOUNT = "marginal_amount"   # fixed amount per bracket
    SINGLE_AMOUNT = "single_amount"       # flat amount regardless of income
    FLAT_RATE = "flat_rate"               # single rate on full base
    ZERO = "zero"                         # jurisdiction levies no tax (15 zero-CIT countries)
    EXEMPT = "exempt"                     # entity type exempt from this tax

@dataclass
class TaxBracket:
    threshold: float         # lower bound of this bracket (0 for first)
    rate: float              # rate or amount depending on BracketType
    bracket_type: BracketType = BracketType.MARGINAL_RATE

@dataclass
class TaxParameter:
    """A single tax instrument (e.g. corporate_income_tax, vat_standard, payroll_employer)."""
    key: str                          # e.g. "corporate_income_tax"
    label: str
    bracket_type: BracketType
    brackets: list[TaxBracket] = field(default_factory=list)
    flat_rate: float | None = None    # used for FLAT_RATE / ZERO
    currency: str = "EUR"
    notes: str = ""

    def compute(self, base: float) -> float:
        """Compute tax amount for a given base (income, profit, salary, etc.)."""
        if self.bracket_type == BracketType.ZERO:
            return 0.0
        if self.bracket_type == BracketType.EXEMPT:
            return 0.0
        if self.bracket_type == BracketType.FLAT_RATE:
            return base * (self.flat_rate or 0.0)
        if self.bracket_type == BracketType.SINGLE_AMOUNT:
            return self.brackets[0].rate if self.brackets else 0.0
        # MARGINAL_RATE or MARGINAL_AMOUNT
        total = 0.0
        sorted_brackets = sorted(self.brackets, key=lambda b: b.threshold)
        for i, b in enumerate(sorted_brackets):
            upper = sorted_brackets[i+1].threshold if i+1 < len(sorted_brackets) else float("inf")
            slice_base = max(0.0, min(base, upper) - b.threshold)
            if slice_base <= 0:
                continue
            if self.bracket_type == BracketType.MARGINAL_RATE:
                total += slice_base * b.rate
            else:  # MARGINAL_AMOUNT
                total += b.rate
        return total

@dataclass
class TaxRuleset:
    """A jurisdiction's tax rules for a given fiscal year. CID-addressable."""
    jurisdiction_code: str    # ISO code, e.g. "NL"
    fiscal_year: int
    entity_types: list[str]   # which entity types this ruleset applies to
    parameters: dict[str, TaxParameter] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)   # URLs / official docs
    zero_cit: bool = False    # True for the 15 no-CIT jurisdictions

    def add(self, param: TaxParameter) -> None:
        self.parameters[param.key] = param

    def get(self, key: str) -> TaxParameter | None:
        return self.parameters.get(key)

    def to_dict(self) -> dict:
        return {
            "kind": "tax-ruleset",
            "jurisdiction": self.jurisdiction_code,
            "fiscal_year": self.fiscal_year,
            "entity_types": self.entity_types,
            "zero_cit": self.zero_cit,
            "parameters": {
                k: {
                    "key": p.key, "label": p.label,
                    "bracket_type": p.bracket_type.value,
                    "brackets": [{"threshold": b.threshold, "rate": b.rate, "bracket_type": b.bracket_type.value} for b in p.brackets],
                    "flat_rate": p.flat_rate,
                    "currency": p.currency,
                    "notes": p.notes,
                }
                for k, p in self.parameters.items()
            },
            "sources": self.sources,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TaxRuleset":
        rs = cls(
            jurisdiction_code=d["jurisdiction"],
            fiscal_year=d["fiscal_year"],
            entity_types=d.get("entity_types", []),
            zero_cit=d.get("zero_cit", False),
            sources=d.get("sources", []),
        )
        for k, pd in d.get("parameters", {}).items():
            brackets = [TaxBracket(b["threshold"], b["rate"], BracketType(b.get("bracket_type", "marginal_rate"))) for b in pd.get("brackets", [])]
            rs.add(TaxParameter(
                key=pd["key"], label=pd["label"],
                bracket_type=BracketType(pd["bracket_type"]),
                brackets=brackets,
                flat_rate=pd.get("flat_rate"),
                currency=pd.get("currency", "EUR"),
                notes=pd.get("notes", ""),
            ))
        return rs

    def cid(self) -> str:
        """SHA2-256 CID of canonical JSON — content-addressable for knitweb gossip."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",",":"))
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        return f"sha256:{digest}"

    @staticmethod
    def load_from_file(path: str) -> "TaxRuleset":
        with Path(path).open("r", encoding="utf-8") as f:
            return TaxRuleset.from_dict(json.load(f))
