"""Legal entity: the subject of tax obligations."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from vank.fieldledger.jurisdiction import Jurisdiction

__all__ = ["EntityType", "Entity"]

class EntityType(Enum):
    INDIVIDUAL = "individual"         # natural person (IB, income tax)
    COMPANY_BV = "company_bv"         # Netherlands BV
    COMPANY_LTD = "company_ltd"       # UK Ltd
    COMPANY_CORP = "company_corp"     # US C-Corp / S-Corp
    COMPANY_LLC = "company_llc"       # US LLC (pass-through)
    PARTNERSHIP = "partnership"       # VOF / LLP
    FOUNDATION = "foundation"         # stichting / NGO
    SOLE_TRADER = "sole_trader"       # ZZP / eenmanszaak

@dataclass
class Entity:
    id: str                              # internal UUID or handle
    legal_name: str
    entity_type: EntityType
    jurisdiction: Jurisdiction           # primary tax residence
    registration_number: str = ""        # KvK, EIN, UTR, ABN, etc.
    vat_number: str = ""                 # BTW, VAT, GST number
    fiscal_year_start: int = 1           # month (1=Jan, 4=Apr for UK)
    employees: list[str] = field(default_factory=list)   # employee ids

    def is_corporate(self) -> bool:
        return self.entity_type not in {EntityType.INDIVIDUAL, EntityType.SOLE_TRADER}

    def is_eu_vat_registered(self) -> bool:
        return bool(self.vat_number) and self.jurisdiction.is_eu()

    def to_record(self) -> dict:
        """Serialisable dict (safe to store in SecureStore)."""
        return {
            "id": self.id,
            "legal_name": self.legal_name,
            "entity_type": self.entity_type.value,
            "jurisdiction": self.jurisdiction.code,
            "registration_number": self.registration_number,
            "vat_number": self.vat_number,
            "fiscal_year_start": self.fiscal_year_start,
        }

    @classmethod
    def from_record(cls, d: dict) -> "Entity":
        return cls(
            id=d["id"],
            legal_name=d["legal_name"],
            entity_type=EntityType(d["entity_type"]),
            jurisdiction=Jurisdiction.from_code(d["jurisdiction"]),
            registration_number=d.get("registration_number",""),
            vat_number=d.get("vat_number",""),
            fiscal_year_start=d.get("fiscal_year_start",1),
        )
