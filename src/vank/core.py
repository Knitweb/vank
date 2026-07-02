"""Vank commodity mint node.

The mint node reports signed XRF assay events to a content-addressed ledger and
mints VANK units within a network-issued mint grant. All value math is integer
only: ppm is micrograms per gram, and ``ug_per_token`` defines one token unit.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from vank.crypto import (
    KeyPair,
    content_hash,
    generate_keypair,
    sign_payload,
    verify_payload,
)

__all__ = [
    "DEFAULT_UG_PER_TOKEN",
    "MintGrant",
    "MintEvent",
    "MintAuthority",
    "MintNode",
    "VankState",
    "load_state",
    "save_state",
    "mass_kg_to_g",
    "unit_key",
    "verify_report",
]

DEFAULT_UG_PER_TOKEN = 1_000_000
DEFAULT_GRADE_PPM_MAX = 1_000_000


def _now() -> int:
    return int(time.time())


def _require_positive_int(name: str, value: int) -> None:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def mass_kg_to_g(mass_kg: str | int | Decimal) -> int:
    """Parse kg into integer grams without floating point math."""
    try:
        grams = Decimal(str(mass_kg)) * Decimal(1000)
    except InvalidOperation as exc:
        raise ValueError("mass_kg must be numeric") from exc
    if grams <= 0:
        raise ValueError("mass_kg must be positive")
    if grams != grams.to_integral_value():
        raise ValueError("mass_kg must resolve to whole grams")
    return int(grams)


def unit_key(producer_public_key: str, material: str, batch_id: str) -> str:
    payload = {
        "producer_public_key": producer_public_key,
        "material": material.lower().strip(),
        "batch_id": batch_id.strip(),
    }
    return content_hash(payload)


@dataclass(frozen=True)
class MintGrant:
    grant_id: str
    authority_public_key: str
    producer_public_key: str
    kvk_number: str
    xrf_lab_accreditation: str
    sample_custody_ref: str
    materials: tuple[str, ...]
    ug_per_token: int = DEFAULT_UG_PER_TOKEN
    grade_ppm_max: int = DEFAULT_GRADE_PPM_MAX
    issued_at: int = field(default_factory=_now)
    expires_at: int | None = None
    signature: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "type": "vank.mint_grant.v1",
            "grant_id": self.grant_id,
            "authority_public_key": self.authority_public_key,
            "producer_public_key": self.producer_public_key,
            "kvk_number": self.kvk_number,
            "xrf_lab_accreditation": self.xrf_lab_accreditation,
            "sample_custody_ref": self.sample_custody_ref,
            "materials": list(self.materials),
            "ug_per_token": self.ug_per_token,
            "grade_ppm_max": self.grade_ppm_max,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }

    def to_dict(self) -> dict[str, Any]:
        return self.payload() | {"signature": self.signature}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MintGrant":
        expires_at = data.get("expires_at")
        return cls(
            grant_id=data["grant_id"],
            authority_public_key=data["authority_public_key"],
            producer_public_key=data["producer_public_key"],
            kvk_number=data["kvk_number"],
            xrf_lab_accreditation=data["xrf_lab_accreditation"],
            sample_custody_ref=data["sample_custody_ref"],
            materials=tuple(data["materials"]),
            ug_per_token=int(data["ug_per_token"]),
            grade_ppm_max=int(data["grade_ppm_max"]),
            issued_at=int(data["issued_at"]),
            expires_at=int(expires_at) if expires_at is not None else None,
            signature=data["signature"],
        )

    def verify(self, authority_public_key: str | None = None, now: int | None = None) -> bool:
        if authority_public_key and authority_public_key != self.authority_public_key:
            return False
        current_time = now if now is not None else _now()
        if self.expires_at is not None and current_time > self.expires_at:
            return False
        return verify_payload(self.authority_public_key, self.payload(), self.signature)


@dataclass(frozen=True)
class MintEvent:
    event_id: str
    event_type: str
    producer_public_key: str
    grant_id: str
    material: str
    batch_id: str
    mass_g: int
    grade_ppm: int
    assay_id: str
    contained_ug: int
    tokens_delta: int
    unit_key: str
    created_at: int
    previous_event_id: str | None = None
    signature: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "type": "vank.mint_event.v1",
            "event_type": self.event_type,
            "producer_public_key": self.producer_public_key,
            "grant_id": self.grant_id,
            "material": self.material,
            "batch_id": self.batch_id,
            "mass_g": self.mass_g,
            "grade_ppm": self.grade_ppm,
            "assay_id": self.assay_id,
            "contained_ug": self.contained_ug,
            "tokens_delta": self.tokens_delta,
            "unit_key": self.unit_key,
            "created_at": self.created_at,
            "previous_event_id": self.previous_event_id,
        }

    def to_dict(self) -> dict[str, Any]:
        return self.payload() | {
            "event_id": self.event_id,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MintEvent":
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            producer_public_key=data["producer_public_key"],
            grant_id=data["grant_id"],
            material=data["material"],
            batch_id=data["batch_id"],
            mass_g=int(data["mass_g"]),
            grade_ppm=int(data["grade_ppm"]),
            assay_id=data["assay_id"],
            contained_ug=int(data["contained_ug"]),
            tokens_delta=int(data["tokens_delta"]),
            unit_key=data["unit_key"],
            created_at=int(data["created_at"]),
            previous_event_id=data.get("previous_event_id"),
            signature=data["signature"],
        )

    def verify(self) -> bool:
        expected_id = content_hash(self.payload())
        return self.event_id == expected_id and verify_payload(
            self.producer_public_key,
            self.payload(),
            self.signature,
        )


@dataclass(frozen=True)
class MintAuthority:
    keypair: KeyPair
    allowed_labs: tuple[str, ...] = ()

    def issue_grant(
        self,
        *,
        producer_public_key: str,
        kvk_number: str,
        xrf_lab_accreditation: str,
        sample_custody_ref: str,
        materials: list[str] | tuple[str, ...],
        ug_per_token: int = DEFAULT_UG_PER_TOKEN,
        grade_ppm_max: int = DEFAULT_GRADE_PPM_MAX,
        expires_at: int | None = None,
    ) -> MintGrant:
        if not kvk_number.strip():
            raise ValueError("kvk_number is required")
        if not xrf_lab_accreditation.strip():
            raise ValueError("xrf_lab_accreditation is required")
        if not sample_custody_ref.strip():
            raise ValueError("sample_custody_ref is required")
        if not materials:
            raise ValueError("at least one material is required")
        if self.allowed_labs and xrf_lab_accreditation not in self.allowed_labs:
            raise ValueError("xrf_lab_accreditation is not in the authority allowlist")
        _require_positive_int("ug_per_token", ug_per_token)
        _require_positive_int("grade_ppm_max", grade_ppm_max)

        clean_materials = tuple(sorted({m.lower().strip() for m in materials if m.strip()}))
        if not clean_materials:
            raise ValueError("at least one non-empty material is required")
        payload = {
            "authority_public_key": self.keypair.public_key,
            "producer_public_key": producer_public_key,
            "kvk_number": kvk_number.strip(),
            "xrf_lab_accreditation": xrf_lab_accreditation.strip(),
            "sample_custody_ref": sample_custody_ref.strip(),
            "materials": list(clean_materials),
            "ug_per_token": ug_per_token,
            "grade_ppm_max": grade_ppm_max,
            "issued_at": _now(),
            "expires_at": expires_at,
        }
        grant_id = content_hash({"type": "vank.mint_grant.id.v1", **payload})
        grant = MintGrant(grant_id=grant_id, **payload, signature="")
        return MintGrant(
            **{k: v for k, v in grant.__dict__.items() if k != "signature"},
            signature=sign_payload(self.keypair.private_key, grant.payload()),
        )


class MintNode:
    def __init__(
        self,
        producer_keypair: KeyPair,
        *,
        grant: MintGrant | None = None,
        events: list[MintEvent] | None = None,
    ) -> None:
        self.producer_keypair = producer_keypair
        self.grant = grant
        self.events = events or []

    @property
    def producer_public_key(self) -> str:
        return self.producer_keypair.public_key

    def install_grant(self, grant: MintGrant) -> None:
        if grant.producer_public_key != self.producer_public_key:
            raise ValueError("grant producer key does not match this node")
        if not grant.verify():
            raise ValueError("grant signature is invalid")
        self.grant = grant

    def register(
        self,
        authority: MintAuthority,
        *,
        kvk_number: str,
        xrf_lab_accreditation: str,
        sample_custody_ref: str,
        materials: list[str] | tuple[str, ...],
        ug_per_token: int = DEFAULT_UG_PER_TOKEN,
        grade_ppm_max: int = DEFAULT_GRADE_PPM_MAX,
        expires_at: int | None = None,
    ) -> MintGrant:
        grant = authority.issue_grant(
            producer_public_key=self.producer_public_key,
            kvk_number=kvk_number,
            xrf_lab_accreditation=xrf_lab_accreditation,
            sample_custody_ref=sample_custody_ref,
            materials=materials,
            ug_per_token=ug_per_token,
            grade_ppm_max=grade_ppm_max,
            expires_at=expires_at,
        )
        self.install_grant(grant)
        return grant

    def measure(
        self,
        *,
        material: str,
        batch_id: str,
        mass_kg: str | int | Decimal,
        grade_ppm: int,
        assay_id: str,
    ) -> MintEvent:
        grant = self._active_grant_for(material, grade_ppm)
        key = unit_key(self.producer_public_key, material, batch_id)
        if any(e.unit_key == key and e.event_type == "assay_mint" for e in self.events):
            raise ValueError("unit_key already minted for this producer/material/batch")
        mass_g = mass_kg_to_g(mass_kg)
        event = self._signed_event(
            grant=grant,
            event_type="assay_mint",
            material=material,
            batch_id=batch_id,
            mass_g=mass_g,
            grade_ppm=grade_ppm,
            assay_id=assay_id,
            previous_event_id=None,
            tokens_delta=(mass_g * grade_ppm) // grant.ug_per_token,
        )
        if event.tokens_delta <= 0:
            raise ValueError("measurement resolves to zero tokens")
        self.events.append(event)
        return event

    def revalue(
        self,
        *,
        material: str,
        batch_id: str,
        mass_kg: str | int | Decimal,
        grade_ppm: int,
        assay_id: str,
    ) -> MintEvent:
        grant = self._active_grant_for(material, grade_ppm)
        key = unit_key(self.producer_public_key, material, batch_id)
        current = self.unit_state().get(key)
        if current is None:
            raise ValueError("unit_key has not been minted")
        new_mass_g = mass_kg_to_g(mass_kg)
        new_tokens = (new_mass_g * grade_ppm) // grant.ug_per_token
        current_tokens = current["tokens"]
        delta = new_tokens - current_tokens
        if delta > 0:
            raise ValueError("re-assay cannot increase minted value")
        previous_event_id = current["last_event_id"]
        event = self._signed_event(
            grant=grant,
            event_type="re_assay_burn",
            material=material,
            batch_id=batch_id,
            mass_g=new_mass_g,
            grade_ppm=grade_ppm,
            assay_id=assay_id,
            previous_event_id=previous_event_id,
            tokens_delta=delta,
        )
        self.events.append(event)
        return event

    def balance(self) -> int:
        return sum(e.tokens_delta for e in self.events)

    def unit_state(self) -> dict[str, dict[str, Any]]:
        state: dict[str, dict[str, Any]] = {}
        for event in self.events:
            item = state.setdefault(
                event.unit_key,
                {"tokens": 0, "contained_ug": 0, "last_event_id": None},
            )
            item["tokens"] += event.tokens_delta
            item["contained_ug"] = event.contained_ug
            item["last_event_id"] = event.event_id
        return state

    def audit(self) -> dict[str, Any]:
        errors: list[str] = []
        if self.grant is None:
            errors.append("missing mint grant")
        elif not self.grant.verify():
            errors.append("invalid mint grant signature")
        seen_mints: set[str] = set()
        running_units: dict[str, int] = {}
        for idx, event in enumerate(self.events):
            prefix = f"event[{idx}]"
            if not event.verify():
                errors.append(f"{prefix}: invalid signature or event_id")
            if self.grant and event.grant_id != self.grant.grant_id:
                errors.append(f"{prefix}: grant_id mismatch")
            if event.contained_ug != event.mass_g * event.grade_ppm:
                errors.append(f"{prefix}: contained_ug mismatch")
            if self.grant:
                expected_tokens = event.contained_ug // self.grant.ug_per_token
                if event.event_type == "assay_mint":
                    if event.tokens_delta != expected_tokens:
                        errors.append(f"{prefix}: mint token math mismatch")
                    if event.unit_key in seen_mints:
                        errors.append(f"{prefix}: duplicate unit mint")
                    seen_mints.add(event.unit_key)
                    running_units[event.unit_key] = event.tokens_delta
                elif event.event_type == "re_assay_burn":
                    previous = running_units.get(event.unit_key)
                    if previous is None:
                        errors.append(f"{prefix}: burn without prior mint")
                    elif event.tokens_delta != expected_tokens - previous:
                        errors.append(f"{prefix}: burn token math mismatch")
                    elif event.tokens_delta > 0:
                        errors.append(f"{prefix}: burn increases value")
                    running_units[event.unit_key] = expected_tokens
                else:
                    errors.append(f"{prefix}: unknown event_type")
        return {
            "ok": not errors,
            "errors": errors,
            "event_count": len(self.events),
            "balance": self.balance(),
            "producer_public_key": self.producer_public_key,
            "grant_id": self.grant.grant_id if self.grant else None,
        }

    def export_report(self) -> dict[str, Any]:
        return {
            "type": "vank.report.v1",
            "producer_public_key": self.producer_public_key,
            "grant": self.grant.to_dict() if self.grant else None,
            "events": [e.to_dict() for e in self.events],
            "balance": self.balance(),
            "audit": self.audit(),
        }

    def _active_grant_for(self, material: str, grade_ppm: int) -> MintGrant:
        if self.grant is None:
            raise ValueError("node has no mint grant")
        if self.grant.producer_public_key != self.producer_public_key:
            raise ValueError("grant producer key does not match this node")
        if not self.grant.verify():
            raise ValueError("grant signature is invalid or expired")
        material_clean = material.lower().strip()
        if material_clean not in self.grant.materials:
            raise ValueError("material is not covered by mint grant")
        _require_positive_int("grade_ppm", grade_ppm)
        if grade_ppm > self.grant.grade_ppm_max:
            raise ValueError("grade_ppm exceeds mint grant cap")
        return self.grant

    def _signed_event(
        self,
        *,
        grant: MintGrant,
        event_type: str,
        material: str,
        batch_id: str,
        mass_g: int,
        grade_ppm: int,
        assay_id: str,
        previous_event_id: str | None,
        tokens_delta: int,
    ) -> MintEvent:
        contained_ug = mass_g * grade_ppm
        event = MintEvent(
            event_id="",
            event_type=event_type,
            producer_public_key=self.producer_public_key,
            grant_id=grant.grant_id,
            material=material.lower().strip(),
            batch_id=batch_id.strip(),
            mass_g=mass_g,
            grade_ppm=grade_ppm,
            assay_id=assay_id.strip(),
            contained_ug=contained_ug,
            tokens_delta=tokens_delta,
            unit_key=unit_key(self.producer_public_key, material, batch_id),
            previous_event_id=previous_event_id,
            created_at=_now(),
            signature="",
        )
        event_id = content_hash(event.payload())
        signature = sign_payload(self.producer_keypair.private_key, event.payload())
        return MintEvent(**{**event.__dict__, "event_id": event_id, "signature": signature})


@dataclass
class VankState:
    node: MintNode
    authority: MintAuthority | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "vank.state.v1",
            "producer_private_key": self.node.producer_keypair.private_key,
            "producer_public_key": self.node.producer_keypair.public_key,
            "authority_private_key": (
                self.authority.keypair.private_key if self.authority else None
            ),
            "authority_public_key": (
                self.authority.keypair.public_key if self.authority else None
            ),
            "grant": self.node.grant.to_dict() if self.node.grant else None,
            "events": [e.to_dict() for e in self.node.events],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VankState":
        producer = KeyPair(data["producer_private_key"], data["producer_public_key"])
        grant = MintGrant.from_dict(data["grant"]) if data.get("grant") else None
        events = [MintEvent.from_dict(e) for e in data.get("events", [])]
        node = MintNode(producer, grant=grant, events=events)
        authority = None
        if data.get("authority_private_key") and data.get("authority_public_key"):
            authority = MintAuthority(
                KeyPair(data["authority_private_key"], data["authority_public_key"])
            )
        return cls(node=node, authority=authority)


def default_state_path() -> Path:
    return Path.home() / ".vank" / "mint-node.json"


def load_state(path: str | os.PathLike[str] | None = None, *, demo_authority: bool = True) -> VankState:
    state_path = Path(path) if path else default_state_path()
    if state_path.exists():
        with state_path.open("r", encoding="utf-8") as f:
            return VankState.from_dict(json.load(f))
    producer = generate_keypair()
    authority = MintAuthority(generate_keypair()) if demo_authority else None
    return VankState(node=MintNode(producer), authority=authority)


def save_state(state: VankState, path: str | os.PathLike[str] | None = None) -> Path:
    state_path = Path(path) if path else default_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    try:
        os.chmod(state_path, 0o600)
    except OSError:
        pass
    return state_path


def verify_report(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("type") != "vank.report.v1":
        return {"ok": False, "errors": ["invalid report type"]}
    errors: list[str] = []
    grant_data = report.get("grant")
    if not grant_data:
        return {"ok": False, "errors": ["missing grant"]}
    grant = MintGrant.from_dict(grant_data)
    if not grant.verify():
        errors.append("invalid grant")
    producer = KeyPair(private_key="", public_key=grant.producer_public_key)
    node = MintNode(
        producer,
        grant=grant,
        events=[MintEvent.from_dict(e) for e in report.get("events", [])],
    )
    audit = node.audit()
    errors.extend(audit["errors"])
    if report.get("balance") != node.balance():
        errors.append("reported balance mismatch")
    return {
        "ok": not errors,
        "errors": errors,
        "balance": node.balance(),
        "event_count": len(node.events),
    }
