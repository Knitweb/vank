import json
import tempfile
import unittest
from pathlib import Path

from vank.core import (
    MintAuthority,
    MintGrant,
    MintNode,
    VankState,
    load_state,
    save_state,
    verify_report,
)
from vank.crypto import generate_keypair, verify_payload


class VankMintNodeTest(unittest.TestCase):
    def make_registered_node(self):
        state = VankState(
            node=MintNode(generate_keypair()),
            authority=MintAuthority(generate_keypair()),
        )
        state.node.register(
            state.authority,
            kvk_number="93406797",
            xrf_lab_accreditation="RvA-L123",
            sample_custody_ref="SLAG-COC-2026-0007",
            materials=["v2o5", "vanadium"],
        )
        return state

    def test_grant_requires_complete_evidence(self):
        authority = MintAuthority(generate_keypair())
        producer = generate_keypair()
        with self.assertRaises(ValueError):
            authority.issue_grant(
                producer_public_key=producer.public_key,
                kvk_number="",
                xrf_lab_accreditation="RvA-L123",
                sample_custody_ref="COC",
                materials=["v2o5"],
            )

    def test_register_creates_signed_grant(self):
        state = self.make_registered_node()
        self.assertIsNotNone(state.node.grant)
        self.assertTrue(state.node.grant.verify(state.authority.keypair.public_key))

    def test_measure_mints_integer_tokens(self):
        state = self.make_registered_node()
        event = state.node.measure(
            material="v2o5",
            batch_id="SLAG-IJM-2026-021",
            mass_kg="1000",
            grade_ppm=10_000,
            assay_id="XRF-2026-0421",
        )
        self.assertEqual(event.contained_ug, 1_000_000 * 10_000)
        self.assertEqual(event.tokens_delta, 10_000)
        self.assertEqual(state.node.balance(), 10_000)
        self.assertTrue(event.verify())

    def test_duplicate_unit_is_rejected(self):
        state = self.make_registered_node()
        kwargs = dict(
            material="v2o5",
            batch_id="SLAG-IJM-2026-021",
            mass_kg="1000",
            grade_ppm=10_000,
            assay_id="XRF-2026-0421",
        )
        state.node.measure(**kwargs)
        with self.assertRaises(ValueError):
            state.node.measure(**kwargs)

    def test_revalue_burns_downward_difference(self):
        state = self.make_registered_node()
        state.node.measure(
            material="v2o5",
            batch_id="SLAG-IJM-2026-021",
            mass_kg="1000",
            grade_ppm=10_000,
            assay_id="XRF-2026-0421",
        )
        burn = state.node.revalue(
            material="v2o5",
            batch_id="SLAG-IJM-2026-021",
            mass_kg="1000",
            grade_ppm=9_500,
            assay_id="XRF-2026-0421-R1",
        )
        self.assertEqual(burn.tokens_delta, -500)
        self.assertEqual(state.node.balance(), 9_500)
        self.assertTrue(state.node.audit()["ok"])

    def test_revalue_cannot_increase_value(self):
        state = self.make_registered_node()
        state.node.measure(
            material="v2o5",
            batch_id="SLAG-IJM-2026-021",
            mass_kg="1000",
            grade_ppm=10_000,
            assay_id="XRF-2026-0421",
        )
        with self.assertRaises(ValueError):
            state.node.revalue(
                material="v2o5",
                batch_id="SLAG-IJM-2026-021",
                mass_kg="1000",
                grade_ppm=10_500,
                assay_id="XRF-2026-0421-R1",
            )

    def test_report_is_self_verifying(self):
        state = self.make_registered_node()
        state.node.measure(
            material="v2o5",
            batch_id="SLAG-IJM-2026-021",
            mass_kg="1000",
            grade_ppm=10_000,
            assay_id="XRF-2026-0421",
        )
        result = verify_report(state.node.export_report())
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["balance"], 10_000)

    def test_state_roundtrip(self):
        state = self.make_registered_node()
        state.node.measure(
            material="v2o5",
            batch_id="SLAG-IJM-2026-021",
            mass_kg="1000",
            grade_ppm=10_000,
            assay_id="XRF-2026-0421",
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            save_state(state, path)
            restored = load_state(path)
            self.assertEqual(restored.node.balance(), 10_000)
            self.assertTrue(restored.node.audit()["ok"])

    def test_install_out_of_band_grant(self):
        demo = self.make_registered_node()
        grant_json = demo.node.grant.to_dict()
        state = VankState(
            node=MintNode(demo.node.producer_keypair),
            authority=None,
        )
        state.node.install_grant(MintGrant.from_dict(json.loads(json.dumps(grant_json))))
        self.assertTrue(state.node.grant.verify())

    def test_verify_payload_rejects_malformed_keys(self):
        self.assertFalse(verify_payload("not-base64", {"ok": True}, "not-a-signature"))

    def test_grant_expiry_roundtrip_accepts_string_timestamp(self):
        authority = MintAuthority(generate_keypair())
        producer = generate_keypair()
        grant_data = authority.issue_grant(
            producer_public_key=producer.public_key,
            kvk_number="93406797",
            xrf_lab_accreditation="RvA-L123",
            sample_custody_ref="SLAG-COC-2026-0007",
            materials=["v2o5"],
            expires_at=9_999_999_999,
        ).to_dict()
        grant_data["expires_at"] = str(grant_data["expires_at"])
        grant = MintGrant.from_dict(grant_data)
        self.assertIsInstance(grant.expires_at, int)
        self.assertTrue(grant.verify(now=grant.issued_at))


if __name__ == "__main__":
    unittest.main()
