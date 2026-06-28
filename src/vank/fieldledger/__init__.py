"""FieldLedger — P2P offline accounting, global tax engine, payroll, encrypted vault."""
from vank.fieldledger.jurisdiction import Jurisdiction, TIER_1, TIER_2
from vank.fieldledger.entity import Entity, EntityType
from vank.fieldledger.ruleset import TaxRuleset, TaxParameter, BracketType, TaxBracket
from vank.fieldledger.engine import TaxEngine, TaxObligation
from vank.fieldledger.payroll import Employee, PayrollRun, Payslip, PayslipLine, PayslipCategory
from vank.fieldledger.secure_store import SecureStore
from vank.fieldledger.filing import FilingPackage, JSONExporter, SAFTExporter

__all__ = [
    "Jurisdiction", "TIER_1", "TIER_2",
    "Entity", "EntityType",
    "TaxRuleset", "TaxParameter", "BracketType", "TaxBracket",
    "TaxEngine", "TaxObligation",
    "Employee", "PayrollRun", "Payslip", "PayslipLine", "PayslipCategory",
    "SecureStore",
    "FilingPackage", "JSONExporter", "SAFTExporter",
]

import os as _os
RULESETS_DIR = _os.path.join(_os.path.dirname(__file__), "rulesets")

def load_ruleset(jurisdiction: str, year: int = 2025) -> TaxRuleset | None:
    import json as _json
    path = _os.path.join(RULESETS_DIR, f"{jurisdiction}_{year}.json")
    if not _os.path.exists(path):
        return None
    return TaxRuleset.from_dict(_json.load(open(path)))
