"""
core/payroll_engine.py — Payroll Calculation Engine
=====================================================
Implements EXACT formulas from SamplePaysheet.xlsx (Feb 2026).
All formula parameters are loaded from data/payroll_reference/formula_config.json
so the Finance team can change rates/slabs without touching Python code.

Excel Formula Mapping (column letters from Anchors_Feb'26 sheet):
  Q  Current Month Salary  = StdSalary / 28 * PayableDays
  R  Basic                 = CurrentSalary * basic_pct        (100% Anchor / 90% AMIA)
  S  HRA                   = CurrentSalary * hra_pct          (0% Anchor / 10% AMIA)
  V  Gross Salary          = ROUND(Basic + HRA + LTA + SA, 0)
  W  One-Time Bonus        = StdSalary − GrossSalary          (resigned only, ≥ threshold)
  X  Gratuity              = GratuityAmount (AR)
  Y  Final Gross           = GrossSalary + Bonus + Gratuity
  Z  Gross for PF          = ROUND(Basic + LTA + SA, 0)       excludes HRA
  AA EPF Wages             = ROUND(IF(GrossForPF>15000, 15000, GrossForPF), 0)
  AB PF (12%)              = ROUND(IF(GrossForPF>15000, 1800, GrossForPF×12%), 0)
  AD ESI (0.75%)           = ROUNDUP(IF(StdSal>21000, 0, (FinalGross−Gratuity)×0.75%), 0)
  AE EPF Employer (8.33%)  = ROUND(PF12% / 12% × 8.33%, 0)
  AF PF Employer (3.67%)   = PF12% − EPF833%
  AG ESI Employer (3.25%)  = IF(StdSal>21000, 0, (FinalGross−Gratuity)×3.25%)  [unrounded]
  AK Profession Tax        = IF(Gross≥20001,200, IF(Gross≥15001,150, 0))
  AM PF+ESI+LWF            = PF12% + ESI075% + LWF
  AN Net Salary            = ROUND(FinalGross − (TDS+Others+Insurance+ProfTax+PFESIL WF), 0)
  AP Completed Years       = ROUND((DOE−DOJ)/365, 0)
  AR Gratuity Amount       = ROUND(LastDrawnBasic×15/26×Years, 0)

Attendance CSV Column Positions (0-indexed, data starts row 3):
  1:emp_id  2:name  3:customer  4:project  5:sub_project  7:mobile  8:email
  9:doj  10:doe  39:present  40:wo  41:leaves  42:hfl  43:holidays
  44:mg  45:ml  46:ul  51:total_days  66:lop (leave-balance LOP, KEY column)
  56:open_cl  57:open_sl  58:open_el  59:open_mg  60:open_extra_el
  68:close_cl  69:close_sl  70:close_el  71:close_mg  72:close_extra_el
"""

import json
import math
import logging
from datetime import datetime, date
from pathlib import Path

import pandas as pd

logger = logging.getLogger("Sleuth.PayrollEngine")

# ── Config path ────────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent.parent / "data" / "payroll_reference" / "formula_config.json"

# ── Attendance CSV column index map (0-based) ──────────────────────────────
ATT = {
    "emp_id": 1, "name": 2, "customer": 3, "project": 4,
    "sub_project": 5, "location": 6, "mobile": 7, "email": 8,
    "doj": 9, "doe": 10,
    "present": 39, "wo": 40, "leaves": 41, "hfl": 42,
    "holidays": 43, "mg_days": 44, "ml": 45, "ul": 46,
    "total_days": 51,
    "lop": 66,           # KEY: Leave-balance utilization LOP (Attendance BB column)
    "open_cl": 56, "open_sl": 57, "open_el": 58,
    "open_mg": 59, "open_extra_el": 60,
    "close_cl": 68, "close_sl": 69, "close_el": 70,
    "close_mg": 71, "close_extra_el": 72,
}


# ── Helpers ────────────────────────────────────────────────────────────────
def _load_config() -> dict:
    """Load formula configuration from JSON. Falls back to built-in defaults."""
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load formula_config.json: {e}. Using defaults.")
        return _default_config()


def _default_config() -> dict:
    return {
        "month_days": 28,
        "bonus_threshold_days": 15,
        "salary_slabs": {
            "anchor": {"label": "Standard Anchor", "standard": 12360, "basic_pct": 1.0, "hra_pct": 0.0},
            "amia":   {"label": "AMIA / Maternity", "standard": 17000, "basic_pct": 0.9, "hra_pct": 0.1},
            "asset":  {"label": "Asset",            "standard": 17000, "basic_pct": 0.9, "hra_pct": 0.1},
        },
        "leave_accrual": {"cl": 0.5, "sl": 0.5, "el": 1.0, "extra_el": 0.25},
        "epf":  {"employee_rate": 0.12, "pension_rate": 0.0833, "ceiling": 15000},
        "esi":  {"employee_rate": 0.0075, "employer_rate": 0.0325, "exemption_threshold": 21000},
        "profession_tax_slabs": [
            {"from_amount": 20001, "tax_amount": 200},
            {"from_amount": 15001, "tax_amount": 150},
            {"from_amount": 0,     "tax_amount": 0},
        ],
        "lwf": 0,
        "gratuity": {"min_years": 5, "multiplier": 15, "divisor": 26},
        "slab_detection": {
            "amia_keywords":  ["aima", "amia"],
            "asset_keywords": ["bht", "asset"],
        },
    }


def save_config(cfg: dict) -> None:
    """Persist updated config to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def _round_half_up(x: float) -> int:
    """
    Excel ROUND(..., 0) — always rounds 0.5 upward.
    Python's built-in round() uses banker's rounding which differs for .5 cases.
    """
    return math.floor(x + 0.5)


def _roundup(x: float) -> int:
    """Excel ROUNDUP(..., 0) — always rounds away from zero (ceiling for positive)."""
    return math.ceil(x)


def _f(val, default: float = 0.0) -> float:
    """Safe float conversion from CSV cell."""
    try:
        if val is None:
            return default
        s = str(val).strip().replace(",", "")
        return float(s) if s not in ("", "nan", "None", "-") else default
    except (ValueError, TypeError):
        return default


def _parse_date(s) -> date | None:
    if not s:
        return None
    s = str(s).strip()
    if s in ("", "nan", "None", "No"):
        return None
    for fmt in ("%d-%B-%Y", "%d-%b-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _completed_years(doj: date, doe: date) -> int:
    """
    Excel: =ROUND((DOE−DOJ)/365, 0)
    Rounds to nearest year; ≥6 months counts as a full year (matches Indian Gratuity Act).
    """
    return _round_half_up((doe - doj).days / 365)


def _detect_slab(customer: str, cfg: dict) -> str:
    c = str(customer).lower()
    amia_kw  = cfg.get("slab_detection", {}).get("amia_keywords",  ["aima", "amia"])
    asset_kw = cfg.get("slab_detection", {}).get("asset_keywords", ["bht", "asset"])
    if any(kw in c for kw in amia_kw):
        return "amia"
    if any(kw in c for kw in asset_kw):
        return "asset"
    return "anchor"


def _profession_tax(gross_excl_gratuity: float, slabs: list) -> int:
    """
    Excel: =IF((Y-X)>=20001,200, IF((Y-X)>=15001,150, 0))
    Slabs are checked in descending from_amount order.
    """
    for slab in sorted(slabs, key=lambda s: s["from_amount"], reverse=True):
        if gross_excl_gratuity >= slab["from_amount"]:
            return slab["tax_amount"]
    return 0


def _status(ml: float, ul: float, month_days: int, is_resigned: bool) -> str:
    if is_resigned:
        return "Resigned"
    if ml >= month_days:
        return "Maternity"
    if ul >= month_days:
        return "Long Leave"
    return "Active"


# ── Core Engine ────────────────────────────────────────────────────────────
def process_attendance_csv(
    file_path_or_buffer,
    cfg: dict | None = None,
) -> dict:
    """
    Parse the monthly Anchor-Attendance CSV and compute full payroll.
    Formulas match exactly to SamplePaysheet.xlsx.

    Args:
        file_path_or_buffer: Path or file-like object for the attendance CSV.
        cfg: Optional config dict; if None, loads from formula_config.json.

    Returns:
        { "employees": [...], "summary": {...}, "config": {...} }
    """
    if cfg is None:
        cfg = _load_config()

    month_days         = int(cfg.get("month_days", 28))
    bonus_threshold    = int(cfg.get("bonus_threshold_days", 15))
    slabs_cfg          = cfg.get("salary_slabs", {})
    epf_cfg            = cfg.get("epf", {})
    esi_cfg            = cfg.get("esi", {})
    ptax_slabs         = cfg.get("profession_tax_slabs", [])
    lwf_amount         = float(cfg.get("lwf", 0))
    grat_cfg           = cfg.get("gratuity", {})

    epf_employee_rate   = float(epf_cfg.get("employee_rate", 0.12))
    epf_pension_rate    = float(epf_cfg.get("pension_rate", 0.0833))
    epf_ceiling         = float(epf_cfg.get("ceiling", 15000))
    esi_employee_rate   = float(esi_cfg.get("employee_rate", 0.0075))
    esi_employer_rate   = float(esi_cfg.get("employer_rate", 0.0325))
    esi_exempt_threshold= float(esi_cfg.get("exemption_threshold", 21000))
    grat_min_years      = int(grat_cfg.get("min_years", 5))
    grat_multiplier     = int(grat_cfg.get("multiplier", 15))
    grat_divisor        = int(grat_cfg.get("divisor", 26))

    # Read raw CSV — no automatic header detection (complex multi-row structure)
    raw = pd.read_csv(file_path_or_buffer, header=None, dtype=str, keep_default_na=False)

    # Skip rows 0 (group header), 1 (column header), 2 (accrual values); data from row 3
    data = raw.iloc[3:].reset_index(drop=True)

    # Retain only valid EMP ID rows
    mask = data.iloc[:, ATT["emp_id"]].str.match(r"^JAI-\d+$", na=False)
    data = data[mask].copy()

    employees = []

    for _, row in data.iterrows():
        emp_id   = str(row.iloc[ATT["emp_id"]]).strip()
        name     = str(row.iloc[ATT["name"]]).strip()
        email    = str(row.iloc[ATT["email"]]).strip()
        mobile   = str(row.iloc[ATT["mobile"]]).strip()
        customer = str(row.iloc[ATT["customer"]]).strip()
        project  = str(row.iloc[ATT["project"]]).strip()
        location = str(row.iloc[ATT["location"]]).strip()
        doj_str  = str(row.iloc[ATT["doj"]]).strip()
        doe_str  = str(row.iloc[ATT["doe"]]).strip()

        # Attendance counts
        present    = _f(row.iloc[ATT["present"]])
        wo         = _f(row.iloc[ATT["wo"]])
        leaves     = _f(row.iloc[ATT["leaves"]])
        hfl        = _f(row.iloc[ATT["hfl"]])
        holidays   = _f(row.iloc[ATT["holidays"]])
        mg_days    = _f(row.iloc[ATT["mg_days"]])
        ml         = _f(row.iloc[ATT["ml"]])
        ul         = _f(row.iloc[ATT["ul"]])
        total_days = _f(row.iloc[ATT["total_days"]])
        lop        = _f(row.iloc[ATT["lop"]])   # leave-balance section LOP (col BO)

        # Opening / closing leave balances
        open_cl     = _f(row.iloc[ATT["open_cl"]])
        open_sl     = _f(row.iloc[ATT["open_sl"]])
        open_el     = _f(row.iloc[ATT["open_el"]])
        close_cl    = _f(row.iloc[ATT["close_cl"]])
        close_sl    = _f(row.iloc[ATT["close_sl"]])
        close_el    = _f(row.iloc[ATT["close_el"]])
        close_mg    = _f(row.iloc[ATT["close_mg"]])
        close_extra = _f(row.iloc[ATT["close_extra_el"]])

        # Dates and status
        doj = _parse_date(doj_str)
        doe = _parse_date(doe_str)
        is_resigned = doe is not None
        status = _status(ml, ul, month_days, is_resigned)

        # Salary slab
        slab     = _detect_slab(customer, cfg)
        slab_def = slabs_cfg.get(slab, slabs_cfg.get("anchor", {}))
        std_sal  = float(slab_def.get("standard", 12360))
        basic_pct= float(slab_def.get("basic_pct", 1.0))
        hra_pct  = float(slab_def.get("hra_pct", 0.0))

        # ─────────────────────────────────────────────────────────────────
        # Excel: BB = TotalDays − (UL + LOP)   → Payable Days
        # ─────────────────────────────────────────────────────────────────
        payable_days = max(0.0, total_days - ul - lop)

        # ─────────────────────────────────────────────────────────────────
        # Excel: Q = StdSalary / 28 * PayableDays
        #        R (Basic)  = Q * basic_pct
        #        S (HRA)    = Q * hra_pct
        #        V (Gross)  = ROUND(Basic + HRA + LTA + SA, 0)
        # ─────────────────────────────────────────────────────────────────
        current_salary_raw = std_sal * payable_days / month_days
        basic = _round_half_up(current_salary_raw * basic_pct)
        hra   = _round_half_up(current_salary_raw * hra_pct)
        lta   = 0
        special_allowances = 0
        gross_salary = _round_half_up(basic + hra + lta + special_allowances)

        # ─────────────────────────────────────────────────────────────────
        # Excel: Z = ROUND(Basic + LTA + SA, 0)   [Gross for PF — excl. HRA]
        # ─────────────────────────────────────────────────────────────────
        gross_for_pf = _round_half_up(basic + lta + special_allowances)

        # ─────────────────────────────────────────────────────────────────
        # Excel: W = StdSalary − GrossSalary   [One-Time Bonus for resigned]
        # Only if resigned AND worked until at least bonus_threshold_days
        # ─────────────────────────────────────────────────────────────────
        bonus = 0
        if is_resigned and total_days >= bonus_threshold:
            gap = _round_half_up(std_sal) - gross_salary
            if gap > 0:
                bonus = gap

        # ─────────────────────────────────────────────────────────────────
        # Gratuity: Excel AP = ROUND((DOE−DOJ)/365, 0)
        #           Excel AR = ROUND(StdSalary × 15 / 26 × Years, 0)
        # ─────────────────────────────────────────────────────────────────
        gratuity        = 0
        completed_years = 0
        if is_resigned and doj and doe:
            completed_years = _completed_years(doj, doe)
            if completed_years >= grat_min_years:
                gratuity = _round_half_up(std_sal * grat_multiplier / grat_divisor * completed_years)

        # ─────────────────────────────────────────────────────────────────
        # Excel: Y = GrossSalary + Bonus + Gratuity   [Final Gross]
        # ESI base = FinalGross − Gratuity = GrossSalary + Bonus
        # ─────────────────────────────────────────────────────────────────
        final_gross = gross_salary + bonus + gratuity
        esi_base    = final_gross - gratuity     # = GrossSalary + Bonus

        # ─────────────────────────────────────────────────────────────────
        # Excel: AA = ROUND(IF(GrossForPF>15000, 15000, GrossForPF), 0)
        #        AB = ROUND(IF(GrossForPF>15000, 1800, GrossForPF×12%), 0)
        # ─────────────────────────────────────────────────────────────────
        epf_wages    = _round_half_up(min(gross_for_pf, epf_ceiling))
        max_pf_contribution = _round_half_up(epf_ceiling * epf_employee_rate)
        if gross_for_pf > epf_ceiling:
            epf_employee = max_pf_contribution
        else:
            epf_employee = _round_half_up(gross_for_pf * epf_employee_rate)

        # ─────────────────────────────────────────────────────────────────
        # Excel: AD = ROUNDUP(IF(StdSal>21000, 0, ESIbase×0.75%), 0)
        # ─────────────────────────────────────────────────────────────────
        if std_sal > esi_exempt_threshold:
            esi_employee = 0
        else:
            esi_employee = _roundup(esi_base * esi_employee_rate)

        # ─────────────────────────────────────────────────────────────────
        # Excel: AK = IF(ESIbase≥20001,200, IF(ESIbase≥15001,150, 0))
        # ─────────────────────────────────────────────────────────────────
        profession_tax = _profession_tax(esi_base, ptax_slabs)

        # LWF (from config)
        lwf = int(lwf_amount)

        # ─────────────────────────────────────────────────────────────────
        # Excel: AM = PF12% + ESI075% + LWF
        #        AN = ROUND(FinalGross − (TDS + Others + Ins + ProfTax + AM), 0)
        # ─────────────────────────────────────────────────────────────────
        tds = 0
        others = 0
        insurance = 0
        pf_esi_lwf_total = epf_employee + esi_employee + lwf
        total_deductions  = pf_esi_lwf_total + profession_tax + tds + others + insurance
        net_salary = _round_half_up(final_gross - total_deductions)

        # ─────────────────────────────────────────────────────────────────
        # Employer contributions
        # Excel: AE = ROUND(PF12% / 12% × 8.33%, 0)   [Pension / EPS]
        #        AF = PF12% − AE                        [PF Employer]
        #        AG = IF(StdSal>21000,0, ESIbase×3.25%) [ESI Employer, unrounded]
        # ─────────────────────────────────────────────────────────────────
        pension      = _round_half_up(epf_employee / epf_employee_rate * epf_pension_rate)
        pf_employer  = epf_employee - pension
        if std_sal > esi_exempt_threshold:
            esi_employer = 0.0
        else:
            esi_employer = esi_base * esi_employer_rate   # NOT rounded (matches xlsx)
        total_employer = pension + pf_employer + esi_employer

        employees.append({
            # Identity
            "emp_id":   emp_id,
            "name":     name,
            "email":    email,
            "mobile":   mobile,
            "doj":      doj_str,
            "doe":      doe_str if is_resigned else "",
            "customer": customer,
            "project":  project,
            "location": location,
            "slab":     slab,
            "status":   status,
            # Attendance
            "present":      present,
            "wo":           wo,
            "leaves":       leaves,
            "hfl":          hfl,
            "holidays":     holidays,
            "ml":           ml,
            "ul":           ul,
            "total_days":   total_days,
            "lop":          lop,
            "payable_days": payable_days,
            # Leave balances
            "open_cl":  open_cl,  "open_sl":  open_sl,  "open_el": open_el,
            "close_cl": close_cl, "close_sl": close_sl, "close_el": close_el,
            "close_mg": close_mg, "close_extra": close_extra,
            # Salary components (matching xlsx columns)
            "standard_salary":   std_sal,
            "current_salary_raw":current_salary_raw,
            "basic":             basic,
            "hra":               hra,
            "gross_salary":      gross_salary,
            "bonus":             bonus,
            "gratuity":          gratuity,
            "completed_years":   completed_years,
            "final_gross":       final_gross,
            "gross_for_pf":      gross_for_pf,
            # Employee deductions
            "epf_wages":       epf_wages,
            "epf_employee":    epf_employee,
            "esi_employee":    esi_employee,
            "profession_tax":  profession_tax,
            "lwf":             lwf,
            "tds":             tds,
            "insurance":       insurance,
            "other":           others,
            "pf_esi_lwf_total": pf_esi_lwf_total,
            "total_deductions": total_deductions,
            # Net
            "net_salary": net_salary,
            # Employer
            "pension":        pension,
            "pf_employer":    pf_employer,
            "esi_employer":   round(esi_employer, 4),
            "total_employer": round(total_employer, 4),
        })

    # ── Aggregates ─────────────────────────────────────────────────────────
    summary = {
        "total_headcount":  len(employees),
        "active_count":     sum(1 for e in employees if e["status"] == "Active"),
        "resigned_count":   sum(1 for e in employees if e["status"] == "Resigned"),
        "maternity_count":  sum(1 for e in employees if e["status"] == "Maternity"),
        "long_leave_count": sum(1 for e in employees if e["status"] == "Long Leave"),
        "total_gross":      sum(e["final_gross"]       for e in employees),
        "total_net":        sum(e["net_salary"]        for e in employees),
        "total_bonus":      sum(e["bonus"]             for e in employees),
        "total_gratuity":   sum(e["gratuity"]          for e in employees),
        "total_epf_emp":    sum(e["epf_employee"]      for e in employees),
        "total_esi_emp":    sum(e["esi_employee"]      for e in employees),
        "total_deductions": sum(e["total_deductions"]  for e in employees),
        "total_employer":   round(sum(e["total_employer"] for e in employees), 2),
        "total_ctc":        round(sum(e["final_gross"] + e["total_employer"] for e in employees), 2),
    }

    return {"employees": employees, "summary": summary, "config": cfg}


# ── Export helpers ─────────────────────────────────────────────────────────
def generate_payroll_csv(employees: list) -> str:
    cols = [
        "emp_id", "email", "mobile", "doj", "doe", "customer", "project",
        "status", "slab",
        "present", "wo", "leaves", "hfl", "ml", "ul", "lop", "payable_days",
        "open_cl", "open_sl", "open_el", "close_cl", "close_sl", "close_el",
        "standard_salary", "basic", "hra", "gross_salary", "bonus", "gratuity",
        "final_gross", "gross_for_pf", "epf_wages",
        "epf_employee", "esi_employee", "profession_tax", "lwf", "tds",
        "insurance", "other",
        "pf_esi_lwf_total", "total_deductions", "net_salary",
        "pension", "pf_employer", "esi_employer", "total_employer",
        "completed_years",
    ]
    df = pd.DataFrame(employees)[cols]
    return df.to_csv(index=False)


def generate_leave_balance_csv(employees: list) -> str:
    rows = [
        {
            "S.NO": i + 1, "EMP ID": e["emp_id"], "Names": e["name"],
            "Last Year Carry Forward": 0,
            "CL": e["close_cl"], "SL": e["close_sl"], "EL": e["close_el"],
            "MG": e["close_mg"], "Extra EL Balance": e["close_extra"],
        }
        for i, e in enumerate(employees)
    ]
    return pd.DataFrame(rows).to_csv(index=False)
