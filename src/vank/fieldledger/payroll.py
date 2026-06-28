"""Payroll engine: employees, payslip lines, payslip generation."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

__all__ = ["PayslipCategory", "PayslipLine", "Payslip", "Employee", "PayrollRun"]


class PayslipCategory(Enum):
    GROSS_SALARY = "gross_salary"
    ALLOWANCE = "allowance"
    EMPLOYEE_TAX = "employee_tax"          # loonheffing / income tax withheld
    EMPLOYEE_SOCIAL = "employee_social"    # employee social security (WW/AOW etc.)
    EMPLOYER_SOCIAL = "employer_social"    # employer contributions
    PENSION_EMPLOYEE = "pension_employee"
    PENSION_EMPLOYER = "pension_employer"
    DEDUCTION = "deduction"
    REIMBURSEMENT = "reimbursement"
    NET_PAY = "net_pay"


@dataclass
class PayslipLine:
    category: PayslipCategory
    description: str
    amount: float           # positive = income, negative = deduction


@dataclass
class Employee:
    id: str
    name: str
    jurisdiction_code: str   # where taxes are withheld
    annual_salary: float
    currency: str = "EUR"
    pension_pct: float = 0.0  # employee pension contribution as fraction of gross
    allowances: dict[str, float] = field(default_factory=dict)  # {name: monthly_amount}


@dataclass
class Payslip:
    employee_id: str
    period: str              # e.g. "2025-06" (YYYY-MM)
    lines: list[PayslipLine] = field(default_factory=list)
    employer_id: str = ""

    def gross(self) -> float:
        return sum(l.amount for l in self.lines if l.category in {
            PayslipCategory.GROSS_SALARY, PayslipCategory.ALLOWANCE})

    def net(self) -> float:
        return sum(l.amount for l in self.lines)

    def to_dict(self) -> dict:
        return {
            "employee_id": self.employee_id,
            "period": self.period,
            "employer_id": self.employer_id,
            "lines": [
                {"category": l.category.value, "description": l.description, "amount": l.amount}
                for l in self.lines
            ],
            "gross": self.gross(),
            "net": self.net(),
        }


class PayrollRun:
    """Generate payslips for a period using a TaxRuleset for withholding."""

    def __init__(self, ruleset, employer_id: str = ""):
        self.ruleset = ruleset
        self.employer_id = employer_id

    def generate(self, employee: Employee, period: str) -> Payslip:
        """Generate a payslip for one employee for one period (month).

        Steps:
        1. Monthly gross = annual_salary / 12 + sum(allowances)
        2. Compute employee_tax = ruleset.get("payroll_employee").compute(monthly_gross * 12) / 12
           (annualize → compute → monthly)
        3. Compute employer_social = ruleset.get("payroll_employer").compute(monthly_gross * 12) / 12
        4. Pension = monthly_gross * employee.pension_pct
        5. Net = gross - employee_tax - employee_social - pension
        6. Build PayslipLine list in category order
        """
        # 1. Gross
        base_monthly = employee.annual_salary / 12.0
        monthly_allowances = sum(employee.allowances.values())
        monthly_gross = base_monthly + monthly_allowances
        annual_gross = monthly_gross * 12.0

        # 2. Employee income tax withheld
        _emp_tax_param = self.ruleset.get("payroll_employee")
        employee_tax = (_emp_tax_param.compute(annual_gross) / 12.0) if _emp_tax_param else 0.0

        # 3. Employer social contributions (informational; not deducted from employee net)
        _er_social_param = self.ruleset.get("payroll_employer")
        employer_social = (_er_social_param.compute(annual_gross) / 12.0) if _er_social_param else 0.0

        # Employee-side social security (optional key; 0 if not defined)
        _ee_social_param = self.ruleset.get("payroll_employee_social")
        employee_social = (_ee_social_param.compute(annual_gross) / 12.0) if _ee_social_param else 0.0

        # 4. Pension (employee contribution)
        pension = monthly_gross * employee.pension_pct

        # 5. Net take-home (employer_social is NOT deducted from employee net)
        # net = gross - employee_tax - employee_social - pension

        # 6. Build lines in category order
        payslip = Payslip(
            employee_id=employee.id,
            period=period,
            employer_id=self.employer_id,
        )

        # Gross salary
        payslip.lines.append(PayslipLine(
            PayslipCategory.GROSS_SALARY,
            "Gross salary",
            base_monthly,
        ))

        # Allowances
        for name, amount in employee.allowances.items():
            payslip.lines.append(PayslipLine(
                PayslipCategory.ALLOWANCE,
                name,
                amount,
            ))

        # Employee income tax (negative = withheld)
        if employee_tax:
            payslip.lines.append(PayslipLine(
                PayslipCategory.EMPLOYEE_TAX,
                "Income tax withheld",
                -employee_tax,
            ))

        # Employee social security (negative = withheld)
        if employee_social:
            payslip.lines.append(PayslipLine(
                PayslipCategory.EMPLOYEE_SOCIAL,
                "Employee social security",
                -employee_social,
            ))

        # Employee pension contribution (negative = withheld)
        if pension:
            payslip.lines.append(PayslipLine(
                PayslipCategory.PENSION_EMPLOYEE,
                "Pension (employee)",
                -pension,
            ))

        return payslip

    def run_all(self, employees: list[Employee], period: str) -> list[Payslip]:
        return [self.generate(e, period) for e in employees]
