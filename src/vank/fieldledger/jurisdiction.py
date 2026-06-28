"""Jurisdiction identification — ISO 3166-1 alpha-2 + optional ISO 3166-2 sub-national."""
from __future__ import annotations
from dataclasses import dataclass

__all__ = ["Jurisdiction", "TIER_1", "TIER_2"]

@dataclass(frozen=True)
class Jurisdiction:
    """Uniquely identifies a tax authority.

    country:     ISO 3166-1 alpha-2 (e.g. "NL", "US", "GB")
    subdivision: ISO 3166-2 sub-code after hyphen (e.g. "TX" for US-TX), or None
    display:     Human-readable name
    oecd_x5:     True for stateless/non-ISO jurisdictions (OECD CbC X5)
    """
    country: str
    subdivision: str | None = None
    display: str = ""
    oecd_x5: bool = False

    @property
    def code(self) -> str:
        """Full ISO code: "NL", "US-TX", or "X5"."""
        if self.oecd_x5:
            return "X5"
        if self.subdivision:
            return f"{self.country}-{self.subdivision}"
        return self.country

    @classmethod
    def from_code(cls, code: str, display: str = "") -> "Jurisdiction":
        """Parse "NL", "US-TX", or "X5"."""
        if code == "X5":
            return cls(country="X5", oecd_x5=True, display=display or "Stateless (OECD X5)")
        if "-" in code:
            country, sub = code.split("-", 1)
            return cls(country=country.upper(), subdivision=sub.upper(), display=display)
        return cls(country=code.upper(), display=display)

    def is_eu(self) -> bool:
        EU_COUNTRIES = {
            "AT","BE","BG","CY","CZ","DE","DK","EE","ES","FI","FR","GR",
            "HR","HU","IE","IT","LT","LU","LV","MT","NL","PL","PT","RO",
            "SE","SI","SK"
        }
        return self.country in EU_COUNTRIES

# Tier 1: priority implementations
TIER_1: dict[str, Jurisdiction] = {
    "NL": Jurisdiction("NL", display="Netherlands"),
    "US": Jurisdiction("US", display="United States"),
    "GB": Jurisdiction("GB", display="United Kingdom"),
    "AU": Jurisdiction("AU", display="Australia"),
    "DE": Jurisdiction("DE", display="Germany"),
    "FR": Jurisdiction("FR", display="France"),
    "EU": Jurisdiction("EU", display="European Union (VAT OSS)"),
}

# Tier 2
TIER_2: dict[str, Jurisdiction] = {
    "CA": Jurisdiction("CA", display="Canada"),
    "BR": Jurisdiction("BR", display="Brazil"),
    "SG": Jurisdiction("SG", display="Singapore"),
    "IN": Jurisdiction("IN", display="India"),
    "JP": Jurisdiction("JP", display="Japan"),
    "CH": Jurisdiction("CH", display="Switzerland"),
    "NO": Jurisdiction("NO", display="Norway"),
    "SE": Jurisdiction("SE", display="Sweden"),
}
