"""Command-line interface for the Vank mint node."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from vank.core import (
    DEFAULT_GRADE_PPM_MAX,
    DEFAULT_UG_PER_TOKEN,
    MintGrant,
    load_state,
    save_state,
)
from vank.server import serve


def _load(args: argparse.Namespace):
    return load_state(args.state, demo_authority=not getattr(args, "no_demo_authority", False))


def _print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def cmd_serve(args: argparse.Namespace) -> None:
    serve(
        host=args.host,
        port=args.port,
        state_path=args.state,
        demo_authority=not args.no_demo_authority,
    )


def cmd_register(args: argparse.Namespace) -> None:
    state = _load(args)
    if state.authority is None:
        raise SystemExit("no local authority available; install an out-of-band grant first")
    grant = state.node.register(
        state.authority,
        kvk_number=args.kvk,
        xrf_lab_accreditation=args.lab,
        sample_custody_ref=args.custody,
        materials=args.material,
        ug_per_token=args.ug_per_token,
        grade_ppm_max=args.grade_ppm_max,
    )
    save_state(state, args.state)
    _print({"ok": True, "grant": grant.to_dict()})


def cmd_install_grant(args: argparse.Namespace) -> None:
    state = _load(args)
    with Path(args.grant_json).open("r", encoding="utf-8") as f:
        grant = MintGrant.from_dict(json.load(f))
    state.node.install_grant(grant)
    save_state(state, args.state)
    _print({"ok": True, "grant_id": grant.grant_id})


def cmd_measure(args: argparse.Namespace) -> None:
    state = _load(args)
    event = state.node.measure(
        material=args.material,
        batch_id=args.batch_id,
        mass_kg=args.mass_kg,
        grade_ppm=args.grade_ppm,
        assay_id=args.assay_id,
    )
    save_state(state, args.state)
    _print({"ok": True, "event": event.to_dict(), "balance": state.node.balance()})


def cmd_revalue(args: argparse.Namespace) -> None:
    state = _load(args)
    event = state.node.revalue(
        material=args.material,
        batch_id=args.batch_id,
        mass_kg=args.mass_kg,
        grade_ppm=args.grade_ppm,
        assay_id=args.assay_id,
    )
    save_state(state, args.state)
    _print({"ok": True, "event": event.to_dict(), "balance": state.node.balance()})


def cmd_balance(args: argparse.Namespace) -> None:
    state = _load(args)
    _print({"balance": state.node.balance(), "unit_count": len(state.node.unit_state())})


def cmd_audit(args: argparse.Namespace) -> None:
    state = _load(args)
    _print(state.node.audit())


def cmd_export(args: argparse.Namespace) -> None:
    state = _load(args)
    report = state.node.export_report()
    output = Path(args.output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _print({"ok": True, "output": str(output), "audit": report["audit"]})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vank", description="Vank mint node")
    parser.add_argument("--state", default=None, help="state file (default ~/.vank/mint-node.json)")
    sub = parser.add_subparsers(dest="command", required=True)

    serve_p = sub.add_parser("serve", help="run GUI + JSON API")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8799)
    serve_p.add_argument("--no-demo-authority", action="store_true")
    serve_p.set_defaults(func=cmd_serve)

    reg = sub.add_parser("register", help="certify this producer and create a mint grant")
    reg.add_argument("--kvk", required=True)
    reg.add_argument("--lab", required=True)
    reg.add_argument("--custody", required=True)
    reg.add_argument("--material", action="append", required=True)
    reg.add_argument("--ug-per-token", type=int, default=DEFAULT_UG_PER_TOKEN)
    reg.add_argument("--grade-ppm-max", type=int, default=DEFAULT_GRADE_PPM_MAX)
    reg.add_argument("--no-demo-authority", action="store_true")
    reg.set_defaults(func=cmd_register)

    install = sub.add_parser("install-grant", help="install an out-of-band mint grant JSON")
    install.add_argument("grant_json")
    install.add_argument("--no-demo-authority", action="store_true")
    install.set_defaults(func=cmd_install_grant)

    measure = sub.add_parser("measure", help="report an XRF measurement and mint")
    measure.add_argument("material")
    measure.add_argument("batch_id")
    measure.add_argument("mass_kg")
    measure.add_argument("grade_ppm", type=int)
    measure.add_argument("assay_id")
    measure.set_defaults(func=cmd_measure)

    revalue = sub.add_parser("revalue", help="process a downward re-assay burn")
    revalue.add_argument("material")
    revalue.add_argument("batch_id")
    revalue.add_argument("mass_kg")
    revalue.add_argument("grade_ppm", type=int)
    revalue.add_argument("assay_id")
    revalue.set_defaults(func=cmd_revalue)

    balance = sub.add_parser("balance", help="show current VANK balance")
    balance.set_defaults(func=cmd_balance)

    audit = sub.add_parser("audit", help="verify grant, events and token math")
    audit.set_defaults(func=cmd_audit)

    export = sub.add_parser("export", help="write a vank.report.v1 bundle")
    export.add_argument("output")
    export.set_defaults(func=cmd_export)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
