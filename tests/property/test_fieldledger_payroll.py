"""Property tests for vank.fieldledger.payroll."""
import sys
sys.path.insert(0, '/tmp/vank-dest/src')

import pytest
from vank.fieldledger.payroll import Employee, PayrollRun, PayslipCategory, Payslip
from vank.fieldledger.ruleset import TaxRuleset, TaxParameter, BracketType, TaxBracket


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _nl_ruleset() -> TaxRuleset:
    """Minimal NL-like ruleset with progressive employee tax and flat employer social."""
    rs = TaxRuleset(
        jurisdiction_code="NL",
        fiscal_year=2025,
        entity_types=["employee"],
    )
    # payroll_employee: marginal_rate (two brackets, ~37% and ~49.5%)
    rs.add(TaxParameter(
        key="payroll_employee",
        label="Loonheffing",
        bracket_type=BracketType.MARGINAL_RATE,
        brackets=[
            TaxBracket(threshold=0.0,     rate=0.3697),
            TaxBracket(threshold=75518.0, rate=0.495),
        ],
    ))
    # payroll_employer: flat_rate (~20% social contributions)
    rs.add(TaxParameter(
        key="payroll_employer",
        label="Werkgeverslasten",
        bracket_type=BracketType.FLAT_RATE,
        flat_rate=0.20,
    ))
    return rs


@pytest.fixture()
def ruleset() -> TaxRuleset:
    return _nl_ruleset()


@pytest.fixture()
def run(ruleset) -> PayrollRun:
    return PayrollRun(ruleset, employer_id="ACME-BV")


@pytest.fixture()
def basic_employee() -> Employee:
    return Employee(
        id="E001",
        name="Jan de Vries",
        jurisdiction_code="NL",
        annual_salary=60_000.0,
    )


@pytest.fixture()
def payslip(run, basic_employee) -> Payslip:
    return run.generate(basic_employee, "2025-06")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _lines_of(payslip: Payslip, category: PayslipCategory):
    return [l for l in payslip.lines if l.category == category]


# ---------------------------------------------------------------------------
# Test 1 – Monthly gross == annual_salary / 12
# ---------------------------------------------------------------------------

def test_monthly_gross_equals_annual_over_12(run, basic_employee):
    slip = run.generate(basic_employee, "2025-06")
    expected_base = basic_employee.annual_salary / 12.0
    gross_lines = _lines_of(slip, PayslipCategory.GROSS_SALARY)
    assert len(gross_lines) == 1
    assert abs(gross_lines[0].amount - expected_base) < 1e-9


# ---------------------------------------------------------------------------
# Test 2 – Payslip has exactly one GROSS_SALARY line
# ---------------------------------------------------------------------------

def test_payslip_has_gross_salary_line(payslip):
    gross_lines = _lines_of(payslip, PayslipCategory.GROSS_SALARY)
    assert len(gross_lines) == 1, "Expected exactly one GROSS_SALARY line"


# ---------------------------------------------------------------------------
# Test 3 – GROSS_SALARY line amount is correct
# ---------------------------------------------------------------------------

def test_gross_salary_line_amount_correct(run, basic_employee):
    slip = run.generate(basic_employee, "2025-06")
    [line] = _lines_of(slip, PayslipCategory.GROSS_SALARY)
    assert abs(line.amount - basic_employee.annual_salary / 12.0) < 1e-9


# ---------------------------------------------------------------------------
# Test 4 – net() < gross() when taxes exist
# ---------------------------------------------------------------------------

def test_net_less_than_gross(payslip):
    assert payslip.net() < payslip.gross(), "Net should be less than gross after tax"


# ---------------------------------------------------------------------------
# Test 5 – employee_tax line is negative
# ---------------------------------------------------------------------------

def test_employee_tax_line_is_negative(payslip):
    tax_lines = _lines_of(payslip, PayslipCategory.EMPLOYEE_TAX)
    assert tax_lines, "Expected at least one EMPLOYEE_TAX line"
    for line in tax_lines:
        assert line.amount < 0, f"EMPLOYEE_TAX line must be negative, got {line.amount}"


# ---------------------------------------------------------------------------
# Test 6 – employer_social: any EMPLOYER_SOCIAL lines present are negative
#           (employer cost convention; current impl is informational / not on employee slip)
# ---------------------------------------------------------------------------

def test_employer_social_lines_are_non_positive(payslip):
    er_lines = _lines_of(payslip, PayslipCategory.EMPLOYER_SOCIAL)
    for line in er_lines:
        assert line.amount <= 0, (
            f"EMPLOYER_SOCIAL amount must be <= 0 (cost), got {line.amount}"
        )


def test_employer_social_ruleset_computes_positive_cost(ruleset, basic_employee):
    """Employer social contribution is a positive cost to the employer."""
    param = ruleset.get("payroll_employer")
    assert param is not None
    annual_cost = param.compute(basic_employee.annual_salary)
    assert annual_cost > 0, "Employer social should be a positive cost"


# ---------------------------------------------------------------------------
# Test 7 – pension deducted when pension_pct > 0
# ---------------------------------------------------------------------------

def test_pension_deducted_when_pension_pct_positive(run):
    emp = Employee(
        id="E002", name="Piet Pension", jurisdiction_code="NL",
        annual_salary=48_000.0, pension_pct=0.05,
    )
    slip = run.generate(emp, "2025-06")
    pension_lines = _lines_of(slip, PayslipCategory.PENSION_EMPLOYEE)
    assert pension_lines, "Expected a PENSION_EMPLOYEE line when pension_pct > 0"
    for line in pension_lines:
        assert line.amount < 0, "Pension deduction must be negative"

    expected_pension = (emp.annual_salary / 12.0) * emp.pension_pct
    total_pension = sum(abs(l.amount) for l in pension_lines)
    assert abs(total_pension - expected_pension) < 1e-9


# ---------------------------------------------------------------------------
# Test 8 – no pension line when pension_pct == 0
# ---------------------------------------------------------------------------

def test_no_pension_line_when_zero_pct(run, basic_employee):
    assert basic_employee.pension_pct == 0.0
    slip = run.generate(basic_employee, "2025-06")
    assert not _lines_of(slip, PayslipCategory.PENSION_EMPLOYEE)


# ---------------------------------------------------------------------------
# Test 9 – allowances add to gross
# ---------------------------------------------------------------------------

def test_allowances_add_to_gross(run):
    emp = Employee(
        id="E003", name="Anna Allowance", jurisdiction_code="NL",
        annual_salary=36_000.0,
        allowances={"Reiskostenvergoeding": 200.0, "Thuiswerkvergoeding": 50.0},
    )
    slip = run.generate(emp, "2025-06")

    # Each allowance has its own ALLOWANCE line
    allowance_lines = _lines_of(slip, PayslipCategory.ALLOWANCE)
    assert len(allowance_lines) == 2

    expected_gross = emp.annual_salary / 12.0 + 200.0 + 50.0
    assert abs(slip.gross() - expected_gross) < 1e-9


# ---------------------------------------------------------------------------
# Test 10 – net() == sum of ALL lines
# ---------------------------------------------------------------------------

def test_net_equals_sum_of_all_lines(payslip):
    total = sum(l.amount for l in payslip.lines)
    assert abs(payslip.net() - total) < 1e-9


# ---------------------------------------------------------------------------
# Test 11 – gross() == sum of GROSS_SALARY + ALLOWANCE lines only
# ---------------------------------------------------------------------------

def test_gross_equals_gross_salary_plus_allowance_lines(run):
    emp = Employee(
        id="E004", name="Boris Both", jurisdiction_code="NL",
        annual_salary=42_000.0, pension_pct=0.04,
        allowances={"Maaltijdvergoeding": 100.0},
    )
    slip = run.generate(emp, "2025-06")

    expected = sum(
        l.amount for l in slip.lines
        if l.category in {PayslipCategory.GROSS_SALARY, PayslipCategory.ALLOWANCE}
    )
    assert abs(slip.gross() - expected) < 1e-9


# ---------------------------------------------------------------------------
# Test 12 – Payslip.to_dict() contains all required keys
# ---------------------------------------------------------------------------

def test_to_dict_contains_required_keys(payslip):
    d = payslip.to_dict()
    required = {"employee_id", "period", "employer_id", "lines", "gross", "net"}
    assert required.issubset(d.keys()), f"Missing keys: {required - d.keys()}"
    assert isinstance(d["lines"], list)
    assert isinstance(d["gross"], float)
    assert isinstance(d["net"], float)


def test_to_dict_line_keys(payslip):
    """Each line dict has category, description, amount."""
    d = payslip.to_dict()
    for line in d["lines"]:
        assert "category" in line
        assert "description" in line
        assert "amount" in line


# ---------------------------------------------------------------------------
# Test 13 – PayrollRun.run_all generates one payslip per employee
# ---------------------------------------------------------------------------

def test_run_all_generates_one_payslip_per_employee(run):
    employees = [
        Employee(id=f"E{i:03d}", name=f"Werknemer {i}", jurisdiction_code="NL",
                 annual_salary=30_000.0 + i * 1000)
        for i in range(5)
    ]
    slips = run.run_all(employees, "2025-06")
    assert len(slips) == len(employees)
    ids = [s.employee_id for s in slips]
    assert ids == [e.id for e in employees], "Payslip order must match employee order"


# ---------------------------------------------------------------------------
# Test 14 – period string preserved in payslip
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ["2025-01", "2025-06", "2026-12", "2024-03"])
def test_period_preserved_in_payslip(run, basic_employee, period):
    slip = run.generate(basic_employee, period)
    assert slip.period == period


# ---------------------------------------------------------------------------
# Test 15 – employer_id propagated from PayrollRun to Payslip
# ---------------------------------------------------------------------------

def test_employer_id_propagated(run, basic_employee):
    slip = run.generate(basic_employee, "2025-06")
    assert slip.employer_id == "ACME-BV"


# ---------------------------------------------------------------------------
# Test 16 – zero salary edge: gross is 0, net <= 0
# ---------------------------------------------------------------------------

def test_zero_salary_gross_is_zero(run):
    emp = Employee(id="E999", name="Onbetaald", jurisdiction_code="NL",
                   annual_salary=0.0)
    slip = run.generate(emp, "2025-06")
    assert slip.gross() == 0.0
    assert slip.net() == 0.0
