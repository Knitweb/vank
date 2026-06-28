"""Property tests for FieldLedger TaxRuleset + TaxEngine."""
import sys, json, os
sys.path.insert(0, '/tmp/vank-dest/src')

import pytest
from vank.fieldledger.ruleset import TaxRuleset, TaxParameter, BracketType, TaxBracket
from vank.fieldledger.engine import TaxEngine, TaxObligation

RULESETS_DIR = '/tmp/vank-dest/src/vank/fieldledger/rulesets'

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def nl_ruleset():
    return TaxRuleset.load_from_file(os.path.join(RULESETS_DIR, 'NL_2025.json'))


@pytest.fixture
def us_ruleset():
    return TaxRuleset.load_from_file(os.path.join(RULESETS_DIR, 'US_2025.json'))


@pytest.fixture
def nl_vpb(nl_ruleset):
    return nl_ruleset.get('corporate_income_tax')


@pytest.fixture
def nl_income_tax(nl_ruleset):
    return nl_ruleset.get('income_tax')


@pytest.fixture
def us_cit(us_ruleset):
    return us_ruleset.get('corporate_income_tax')


def make_marginal_rate_param(key='test_mr') -> TaxParameter:
    """Two-bracket marginal rate: 19% up to 200_000, 25.8% above."""
    return TaxParameter(
        key=key,
        label='Test MR',
        bracket_type=BracketType.MARGINAL_RATE,
        brackets=[
            TaxBracket(threshold=0, rate=0.19),
            TaxBracket(threshold=200_000, rate=0.258),
        ],
    )


def make_zero_param(key='test_zero') -> TaxParameter:
    return TaxParameter(
        key=key,
        label='Zero CIT',
        bracket_type=BracketType.ZERO,
        brackets=[],
    )


def make_flat_rate_param(key='test_flat', rate=0.21) -> TaxParameter:
    return TaxParameter(
        key=key,
        label='Flat rate',
        bracket_type=BracketType.FLAT_RATE,
        flat_rate=rate,
        brackets=[],
    )


def make_marginal_amount_param(key='test_ma') -> TaxParameter:
    """Fixed-amount-per-bracket: €500 for income in [0, 50k), €1500 for [50k, ∞)."""
    return TaxParameter(
        key=key,
        label='Test MA',
        bracket_type=BracketType.MARGINAL_AMOUNT,
        brackets=[
            TaxBracket(threshold=0, rate=500),
            TaxBracket(threshold=50_000, rate=1_500),
        ],
    )


# ---------------------------------------------------------------------------
# TaxParameter – MARGINAL_RATE
# ---------------------------------------------------------------------------

class TestMarginalRate:
    def test_single_bracket_below_threshold(self):
        """compute(150_000) stays fully in first bracket: 150_000 * 0.19."""
        param = make_marginal_rate_param()
        assert param.compute(150_000) == pytest.approx(150_000 * 0.19)

    def test_two_brackets_above_threshold(self):
        """compute(300_000) spans both brackets correctly."""
        param = make_marginal_rate_param()
        expected = 200_000 * 0.19 + 100_000 * 0.258
        assert param.compute(300_000) == pytest.approx(expected)

    def test_exactly_at_bracket_boundary(self):
        """compute(200_000) touches the boundary; second slice is zero."""
        param = make_marginal_rate_param()
        assert param.compute(200_000) == pytest.approx(200_000 * 0.19)

    def test_zero_base(self):
        param = make_marginal_rate_param()
        assert param.compute(0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# TaxParameter – FLAT_RATE
# ---------------------------------------------------------------------------

class TestFlatRate:
    def test_flat_rate_compute(self):
        param = make_flat_rate_param(rate=0.21)
        assert param.compute(1_000_000) == pytest.approx(210_000.0)

    def test_flat_rate_zero_base(self):
        param = make_flat_rate_param(rate=0.21)
        assert param.compute(0) == pytest.approx(0.0)

    def test_flat_rate_arbitrary_base(self):
        param = make_flat_rate_param(rate=0.125)
        assert param.compute(40_000) == pytest.approx(40_000 * 0.125)


# ---------------------------------------------------------------------------
# TaxParameter – ZERO
# ---------------------------------------------------------------------------

class TestZeroParam:
    def test_zero_returns_zero_for_any_base(self):
        param = make_zero_param()
        assert param.compute(999_999) == 0.0

    def test_zero_returns_zero_for_zero_base(self):
        param = make_zero_param()
        assert param.compute(0) == 0.0

    def test_zero_returns_zero_for_large_base(self):
        param = make_zero_param()
        assert param.compute(1_000_000_000) == 0.0


# ---------------------------------------------------------------------------
# TaxParameter – MARGINAL_AMOUNT
# ---------------------------------------------------------------------------

class TestMarginalAmount:
    def test_single_bracket_applies(self):
        """Base below second threshold: only first bracket amount added."""
        param = make_marginal_amount_param()
        assert param.compute(30_000) == pytest.approx(500.0)

    def test_both_brackets_apply(self):
        """Base above second threshold: both fixed amounts summed."""
        param = make_marginal_amount_param()
        assert param.compute(80_000) == pytest.approx(500.0 + 1_500.0)


# ---------------------------------------------------------------------------
# TaxRuleset – CID
# ---------------------------------------------------------------------------

class TestTaxRulesetCID:
    def test_cid_is_deterministic(self, nl_ruleset):
        """Same ruleset object produces the same CID on repeated calls."""
        assert nl_ruleset.cid() == nl_ruleset.cid()

    def test_cid_changes_on_parameter_mutation(self, nl_ruleset):
        """Altering a bracket rate must yield a different CID."""
        cid_before = nl_ruleset.cid()
        # Mutate: change the first bracket rate of VPB
        nl_ruleset.parameters['corporate_income_tax'].brackets[0].rate = 0.20
        cid_after = nl_ruleset.cid()
        assert cid_before != cid_after

    def test_cid_round_trip_via_dict(self, nl_ruleset):
        """to_dict() → from_dict() produces an object with the same CID."""
        original_cid = nl_ruleset.cid()
        restored = TaxRuleset.from_dict(nl_ruleset.to_dict())
        assert restored.cid() == original_cid


# ---------------------------------------------------------------------------
# TaxRuleset – from_dict / load
# ---------------------------------------------------------------------------

class TestTaxRulesetLoad:
    def test_from_dict_nl_2025_jurisdiction(self, nl_ruleset):
        assert nl_ruleset.jurisdiction_code == 'NL'

    def test_from_dict_nl_2025_fiscal_year(self, nl_ruleset):
        assert nl_ruleset.fiscal_year == 2025

    def test_from_dict_nl_2025_has_vpb(self, nl_ruleset):
        assert nl_ruleset.get('corporate_income_tax') is not None

    def test_from_dict_nl_2025_has_income_tax(self, nl_ruleset):
        assert nl_ruleset.get('income_tax') is not None


# ---------------------------------------------------------------------------
# NL VPB (corporate_income_tax) known values
# ---------------------------------------------------------------------------

class TestNLVPB:
    def test_vpb_200k_equals_38000(self, nl_vpb):
        """€200k profit → exactly 19% (boundary; second slice = 0)."""
        assert nl_vpb.compute(200_000) == pytest.approx(38_000.0)

    def test_vpb_400k_uses_both_brackets(self, nl_vpb):
        """€400k profit → 19% on first 200k + 25.8% on remaining 200k."""
        expected = 38_000 + 200_000 * 0.258
        assert nl_vpb.compute(400_000) == pytest.approx(expected)

    def test_vpb_zero_profit(self, nl_vpb):
        assert nl_vpb.compute(0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# NL income_tax known values
# ---------------------------------------------------------------------------

class TestNLIncomeTax:
    def test_income_tax_at_bracket_ceiling(self, nl_income_tax):
        """At exactly €75_624 the entire amount is taxed at 36.97%."""
        expected = 75_624 * 0.3697
        assert nl_income_tax.compute(75_624) == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# US CIT known values
# ---------------------------------------------------------------------------

class TestUSCIT:
    def test_us_cit_flat_21_pct(self, us_cit):
        """US CIT is a flat 21% rate (TCJA); €1M → $210k."""
        assert us_cit.compute(1_000_000) == pytest.approx(210_000.0)


# ---------------------------------------------------------------------------
# TaxEngine
# ---------------------------------------------------------------------------

class TestTaxEngine:
    def test_engine_returns_tax_obligation(self, nl_ruleset):
        engine = TaxEngine(nl_ruleset)
        obl = engine.compute('entity-001', {'gross_profit': 200_000})
        assert isinstance(obl, TaxObligation)

    def test_engine_vpb_item_correct(self, nl_ruleset):
        """Engine maps gross_profit → corporate_income_tax correctly."""
        engine = TaxEngine(nl_ruleset)
        obl = engine.compute('entity-001', {'gross_profit': 200_000})
        assert obl.items['corporate_income_tax'] == pytest.approx(38_000.0)

    def test_obligation_total_equals_sum_of_items(self, nl_ruleset):
        """TaxObligation.total must equal sum(items.values())."""
        engine = TaxEngine(nl_ruleset)
        obl = engine.compute('entity-001', {
            'gross_profit': 400_000,
            'gross_salary': 60_000,
            'vat_turnover': 50_000,
        })
        assert obl.total == pytest.approx(sum(obl.items.values()))

    def test_engine_zero_cit_param_contributes_zero(self):
        """A ZERO bracket_type parameter never adds to obligations."""
        rs = TaxRuleset(jurisdiction_code='XX', fiscal_year=2025, entity_types=['corp'])
        rs.add(make_zero_param(key='corporate_income_tax'))
        engine = TaxEngine(rs)
        obl = engine.compute('e1', {'gross_profit': 5_000_000})
        assert obl.items['corporate_income_tax'] == 0.0
        assert obl.total == pytest.approx(0.0)

    def test_engine_entity_id_and_jurisdiction_propagated(self, nl_ruleset):
        engine = TaxEngine(nl_ruleset)
        obl = engine.compute('my-bv-42', {'gross_profit': 100_000})
        assert obl.entity_id == 'my-bv-42'
        assert obl.jurisdiction == 'NL'
        assert obl.fiscal_year == 2025
