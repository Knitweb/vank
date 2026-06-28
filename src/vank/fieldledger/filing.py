"""Filing package: export tax data to JSON and SAF-T XML format."""
from __future__ import annotations
import json
from dataclasses import dataclass
from xml.etree.ElementTree import Element, SubElement, tostring, indent

__all__ = ["FilingPackage", "SAFTExporter", "JSONExporter"]

@dataclass
class FilingPackage:
    """Collects all data for a single tax filing: entity + obligations + payslips."""
    entity_id: str
    jurisdiction_code: str
    fiscal_year: int
    obligations: list[dict] = None      # TaxObligation.to_dict() list
    payslips: list[dict] = None         # Payslip.to_dict() list
    ledger_summary: dict = None         # trial_balance dict from vank.ledger

    def __post_init__(self):
        self.obligations = self.obligations or []
        self.payslips = self.payslips or []
        self.ledger_summary = self.ledger_summary or {}

class JSONExporter:
    """Export FilingPackage as JSON (offline storage + knitweb record)."""
    @staticmethod
    def export(pkg: FilingPackage) -> str:
        d = {
            "kind": "tax-filing",
            "entity_id": pkg.entity_id,
            "jurisdiction": pkg.jurisdiction_code,
            "fiscal_year": pkg.fiscal_year,
            "obligations": pkg.obligations,
            "payslips": pkg.payslips,
            "ledger_summary": pkg.ledger_summary,
        }
        return json.dumps(d, indent=2, ensure_ascii=False)

class SAFTExporter:
    """Export as OECD SAF-T XML skeleton (structure only — jurisdiction-specific
    schemas require additional mapping)."""

    @staticmethod
    def export(pkg: FilingPackage, company_name: str = "") -> str:
        root = Element("AuditFile")
        root.set("xmlns", "urn:StandardAuditFile-Taxation:NO")

        header = SubElement(root, "Header")
        SubElement(header, "AuditFileVersion").text = "1.0"
        SubElement(header, "AuditFileCountry").text = pkg.jurisdiction_code
        SubElement(header, "AuditFileDateCreated").text = str(pkg.fiscal_year)
        SubElement(header, "CompanyID").text = pkg.entity_id
        SubElement(header, "TaxRegistrationNumber").text = pkg.entity_id
        SubElement(header, "TaxPeriodStart").text = f"{pkg.fiscal_year}-01-01"
        SubElement(header, "TaxPeriodEnd").text = f"{pkg.fiscal_year}-12-31"
        SubElement(header, "DefaultCurrencyCode").text = "EUR"

        company = SubElement(root, "Company")
        SubElement(company, "RegistrationNumber").text = pkg.entity_id
        SubElement(company, "Name").text = company_name

        # General Ledger Accounts
        master = SubElement(root, "MasterFiles")
        gl = SubElement(master, "GeneralLedgerAccounts")
        for acct_id, balance in pkg.ledger_summary.items():
            acct = SubElement(gl, "Account")
            SubElement(acct, "AccountID").text = str(acct_id)
            SubElement(acct, "OpeningDebitBalance").text = str(max(0, balance))
            SubElement(acct, "OpeningCreditBalance").text = str(max(0, -balance))

        # Tax obligations as annotations
        tax_decl = SubElement(root, "TaxDeclarations")
        for obl in pkg.obligations:
            decl = SubElement(tax_decl, "TaxDeclaration")
            SubElement(decl, "TaxType").text = "CIT"
            SubElement(decl, "Period").text = str(pkg.fiscal_year)
            SubElement(decl, "TaxAmount").text = str(obl.get("total", 0))

        indent(root, space="  ")
        return tostring(root, encoding="unicode", xml_declaration=False)
