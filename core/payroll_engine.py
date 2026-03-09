"""
core/payroll_engine.py — Payroll Calculation Engine
=====================================================
Formulas exactly match SamplePaysheet.xlsx (Feb 2026 reference sheet).
All formula parameters are loaded from data/payroll_reference/formula_config.json.
Static per-employee deductions (TDS / Advance / Insurance) are stored in
data/payroll_reference/employee_db.json.

─────────────────────────────────────────────────────────────────
Excel Column → Python mapping (Anchors_Feb'26 sheet)
─────────────────────────────────────────────────────────────────
  O   Payable Days         = VLOOKUP(EMP_ID, Attendance!BB, …)  ← attendance col 53
  P   Standed Month Salary = fixed slab (12360 / 17000)
  Q   Current Month Salary = P / 28 * O           [unrounded raw float]
  R   Basic                = Q * basic_pct         [unrounded raw float]
  S   HRA                  = Q * hra_pct           [unrounded raw float]
  T   LTA                  = 0
  U   Special Allowances   = 0
  V   Gross Salary         = ROUND(R+S+T+U, 0)     ← first & only ROUND here
  W   One-Time Bonus       = StdSalary − V          (resigned only, threshold gate)
  X   Gratuity             = AR  (see below)
  Y   Final Gross          = V + W + X
  Z   Gross for PF         = ROUND(V − S, 0)        (excludes HRA)
  AA  EPF Wages            = ROUND(IF(Z>15000, 15000, Z), 0)
  AB  PF 12%               = ROUND(IF(Z>15000, 1800, Z×12%), 0)
  AD  ESI 0.75%            = ROUNDUP(IF(P>21000, 0, (Y−X)×0.75%), 0)
  AE  EPF 8.33%            = ROUND(AB/12%×8.33%, 0)
  AF  PF 3.67%             = AB − AE
  AG  ESI 3.25%            = IF(P>21000, 0, (Y−X)×3.25%)   [NOT rounded]
  AH  TDS                  = manual entry per employee (from employee_db.json)
  AI  Any Others / Advance = manual entry per employee
  AJ  Insurance Advance    = manual entry per employee
  AK  Profession Tax       = IF((Y−X)≥20001,200, IF((Y−X)≥15001,150, 0))
  AL  LWF                  = config value (default 0)
  AM  PF+ESI+LWF           = AB + AD + AL
  AN  Net Salary           = ROUND(Y − (AH+AI+AJ+AK+AM), 0)
  AP  Completed Years      = ROUND((DOE−DOJ)/365, 0)
  AQ  Last Drawn Basic     = P  (standard salary, NOT basic_pct×P)
  AR  Gratuity Amount      = ROUND(AQ×15/26×AP, 0)

─────────────────────────────────────────────────────────────────
Attendance CSV column positions (0-indexed, data starts row 3)
─────────────────────────────────────────────────────────────────
  1:emp_id   2:name   3:customer  4:project  5:sub_project
  6:location  7:mobile  8:email  9:doj  10:doe
  11-38: Day1..Day28 attendance tags
  39:present  40:wo  41:leaves  42:hfl  43:holidays
  44:mg_days  45:ml  46:ul  47:mc  48:bl  49:mdl  50:lop_att
  51:total_days  52:total_actual_days  53:payable_days  ← KEY (col BB)
  54:total_pct
  55:open_cf   56:open_cl  57:open_sl  58:open_el  59:open_mg  60:open_extra_el
  61:util_cf   62:util_cl  63:util_sl  64:util_el  65:util_mg  66:util_lop
  67:close_cf  68:close_cl 69:close_sl 70:close_el 71:close_mg 72:close_extra_el
  73:comments_feb  74:comments_jan
"""

import json
import math
import logging
from datetime import datetime, date
from pathlib import Path

import pandas as pd

logger = logging.getLogger("Sleuth.PayrollEngine")

# ── Config / DB paths ────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent.parent / "data" / "payroll_reference" / "formula_config.json"
EMP_DB_PATH = Path(__file__).parent.parent / "data" / "payroll_reference" / "employee_db.json"

# ── Attendance CSV column index map (0-based) ────────────────────────────────
ATT = {
    "emp_id": 1, "name": 2, "customer": 3, "project": 4,
    "sub_project": 5, "location": 6, "mobile": 7, "email": 8,
    "doj": 9, "doe": 10,
    # Summary attendance counts
    "present": 39, "wo": 40, "leaves": 41, "hfl": 42,
    "holidays": 43, "mg_days": 44, "ml": 45, "ul": 46,
    "mc": 47, "bl": 48, "mdl": 49, "lop_att": 50,
    # Totals
    "total_days": 51,       # AZ — Sum of all categories
    "total_actual": 52,     # BA — Working days (excl. WO/H)
    "payable_days": 53,     # BB — KEY: TotalDays − (UL + LOP_leavebal)
    # Opening leave balances (after Jan closing + accrual)
    "open_cf":  55, "open_cl": 56, "open_sl": 57,
    "open_el":  58, "open_mg": 59, "open_extra_el": 60,
    # Leave utilization
    "util_cf":  61, "util_cl": 62, "util_sl": 63,
    "util_el":  64, "util_mg": 65, "util_lop": 66,
    # Closing leave balances
    "close_cf":    67, "close_cl": 68, "close_sl": 69,
    "close_el":    70, "close_mg": 71, "close_extra_el": 72,
}


# ── Config helpers ────────────────────────────────────────────────────────────
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
            "asset":  {"label": "Asset",             "standard": 17000, "basic_pct": 0.9, "hra_pct": 0.1},
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


# ── Employee DB helpers ───────────────────────────────────────────────────────
def load_employee_db() -> dict:
    """
    Load per-employee static deductions from employee_db.json.
    Returns dict keyed by EMP ID:
        { "JAI-805": { "tds": 0, "advance": 0, "insurance": 5763 }, ... }
    """
    try:
        with open(EMP_DB_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_employee_db(db: dict) -> None:
    """Persist employee deduction overrides to disk."""
    EMP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EMP_DB_PATH, "w") as f:
        json.dump(db, f, indent=2)


def upsert_employee_db(updates: dict) -> dict:
    """Merge updates into the existing employee_db.json and save."""
    db = load_employee_db()
    for emp_id, fields in updates.items():
        if emp_id not in db:
            db[emp_id] = {"tds": 0, "advance": 0, "insurance": 0}
        db[emp_id].update(fields)
    save_employee_db(db)
    return db


# ── Math helpers ──────────────────────────────────────────────────────────────
def _round_half_up(x: float) -> int:
    """
    Excel ROUND(..., 0) — always rounds 0.5 upward.
    Python's built-in round() uses banker's rounding which differs at .5.
    """
    return math.floor(x + 0.5)


def _roundup(x: float) -> int:
    """Excel ROUNDUP(..., 0) — always rounds away from zero (ceiling)."""
    return math.ceil(x)


def _f(val, default: float = 0.0) -> float:
    """Safe float conversion from a CSV cell."""
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
    for fmt in ("%Y-%m-%d", "%d-%B-%Y", "%d-%b-%Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _completed_years(doj: date, doe: date) -> int:
    """
    Excel: =ROUND((DOE−DOJ)/365, 0)
    ≥ 6 months in a year counts as full year (Indian Gratuity Act).
    """
    return _round_half_up((doe - doj).days / 365)


def _detect_slab(customer: str, cfg: dict) -> str:
    """Map customer/department string to salary slab key."""
    c = str(customer).lower()
    amia_kw  = cfg.get("slab_detection", {}).get("amia_keywords",  ["aima", "amia"])
    asset_kw = cfg.get("slab_detection", {}).get("asset_keywords", ["bht", "asset"])
    if any(kw in c for kw in amia_kw):
        return "amia"
    if any(kw in c for kw in asset_kw):
        return "asset"
    return "anchor"


def _profession_tax(esi_base: float, slabs: list) -> int:
    """
    Excel: =IF((Y−X)≥20001, 200, IF((Y−X)≥15001, 150, 0))
    Slabs checked in descending order.
    """
    for slab in sorted(slabs, key=lambda s: s["from_amount"], reverse=True):
        if esi_base >= slab["from_amount"]:
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


# ── Core Engine ───────────────────────────────────────────────────────────────
def process_attendance_csv(
    file_path_or_buffer,
    cfg: dict | None = None,
) -> dict:
    """
    Parse the monthly Anchor-Attendance CSV and compute full payroll.
    Formulas exactly match SamplePaysheet.xlsx (Anchors_Feb'26 tab).

    Formula chain per employee:
        current_salary_raw = StdSalary / 28 * payable_days          [raw float]
        basic_raw          = current_salary_raw * basic_pct          [raw float]
        hra_raw            = current_salary_raw * hra_pct            [raw float]
        gross_salary       = ROUND(basic_raw + hra_raw + lta + sa)   [first & only ROUND]
        gross_for_pf       = ROUND(gross_salary - hra_raw)           [PF excludes HRA]
        bonus              = StdSalary - gross_salary                [resigned only, threshold gate]
        gratuity           = ROUND(StdSalary * 15/26 * completed_yrs)[≥5 yrs resigned]
        final_gross        = gross_salary + bonus + gratuity
        esi_base           = final_gross - gratuity      (= gross + bonus)
        epf_employee       = ROUND(IF(gross_for_pf>15k, 1800, gross_for_pf*12%))
        esi_employee       = ROUNDUP(IF(std_sal>21k, 0, esi_base*0.75%))
        profession_tax     = IF(esi_base≥20001,200, IF(esi_base≥15001,150, 0))
        net_salary         = ROUND(final_gross - (tds+advance+insurance+prof_tax+pf+esi+lwf))

    Args:
        file_path_or_buffer: Path or file-like object for the attendance CSV.
        cfg: Optional config dict; if None, loads from formula_config.json.

    Returns:
        { "employees": [...], "summary": {...}, "config": {...} }
    """
    if cfg is None:
        cfg = _load_config()

    month_days      = int(cfg.get("month_days", 28))
    bonus_threshold = int(cfg.get("bonus_threshold_days", 15))
    slabs_cfg       = cfg.get("salary_slabs", {})
    epf_cfg         = cfg.get("epf", {})
    esi_cfg         = cfg.get("esi", {})
    ptax_slabs      = cfg.get("profession_tax_slabs", [])
    lwf_amount      = float(cfg.get("lwf", 0))
    grat_cfg        = cfg.get("gratuity", {})

    epf_employee_rate    = float(epf_cfg.get("employee_rate", 0.12))
    epf_pension_rate     = float(epf_cfg.get("pension_rate", 0.0833))
    epf_ceiling          = float(epf_cfg.get("ceiling", 15000))
    esi_employee_rate    = float(esi_cfg.get("employee_rate", 0.0075))
    esi_employer_rate    = float(esi_cfg.get("employer_rate", 0.0325))
    esi_exempt_threshold = float(esi_cfg.get("exemption_threshold", 21000))
    grat_min_years       = int(grat_cfg.get("min_years", 5))
    grat_multiplier      = int(grat_cfg.get("multiplier", 15))
    grat_divisor         = int(grat_cfg.get("divisor", 26))

    # Load per-employee static deductions
    emp_db = load_employee_db()

    # Read raw CSV — no automatic header detection (complex multi-row structure)
    raw = pd.read_csv(
        file_path_or_buffer,
        header=None,
        dtype=str,
        keep_default_na=False,
        comment="#",        # skip ## metadata lines in reference CSVs
    )

    # Filter to valid EMP ID rows only — robust against any number of header rows.
    # Row 0 is typically the column-name header (S.NO, EMP ID, …) and any rows after
    # the data block (totals, blanks) are excluded by the regex automatically.
    mask = raw.iloc[:, ATT["emp_id"]].str.match(r"^JAI-\d+$", na=False)
    data = raw[mask].copy().reset_index(drop=True)


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
        present      = _f(row.iloc[ATT["present"]])
        wo           = _f(row.iloc[ATT["wo"]])
        leaves       = _f(row.iloc[ATT["leaves"]])
        hfl          = _f(row.iloc[ATT["hfl"]])
        holidays     = _f(row.iloc[ATT["holidays"]])
        mg_days      = _f(row.iloc[ATT["mg_days"]])
        ml           = _f(row.iloc[ATT["ml"]])
        ul           = _f(row.iloc[ATT["ul"]])
        total_days   = _f(row.iloc[ATT["total_days"]])
        util_lop     = _f(row.iloc[ATT["util_lop"]])   # leave-balance LOP (col BO)

        # KEY: Compute payable_days from raw columns (Excel: BB = AZ − AU − BO).
        # Do NOT read col 53 directly — some CSV exports round it to integers,
        # losing the 0.5-day precision that HFL (half-day leave) introduces.
        # Formula: TotalDays − UnpaidLeave − LOP(leave-balance section)
        payable_days = max(0.0, total_days - ul - util_lop)


        # Opening leave balances
        open_cl  = _f(row.iloc[ATT["open_cl"]])
        open_sl  = _f(row.iloc[ATT["open_sl"]])
        open_el  = _f(row.iloc[ATT["open_el"]])

        # Closing leave balances
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

        # ── Salary slab ───────────────────────────────────────────────────────
        slab     = _detect_slab(customer, cfg)
        slab_def = slabs_cfg.get(slab, slabs_cfg.get("anchor", {}))
        std_sal  = float(slab_def.get("standard", 12360))
        basic_pct= float(slab_def.get("basic_pct", 1.0))
        hra_pct  = float(slab_def.get("hra_pct", 0.0))

        # ── Q: Current Month Salary (raw float, NOT rounded yet) ──────────────
        # Excel: =P/$O$1*O  (where $O$1 = 28, O = payable_days)
        current_salary_raw = std_sal * payable_days / month_days

        # ── R: Basic / S: HRA (raw floats, NOT rounded yet) ──────────────────
        # Excel: R = Q*100%,  S = Q*10%  (for AMIA/Asset)
        basic_raw = current_salary_raw * basic_pct
        hra_raw   = current_salary_raw * hra_pct
        lta   = 0.0
        sa    = 0.0   # special allowances

        # ── V: Gross Salary = ROUND(R+S+T+U, 0)  ← FIRST & ONLY ROUND ───────
        gross_salary = _round_half_up(basic_raw + hra_raw + lta + sa)

        # ── Z: Gross for PF = ROUND(V − S, 0)  (excludes HRA) ───────────────
        # Excel: =ROUND(SUM(R:U)−S, 0)  where S=HRA
        # Since V is already rounded from the same sum, and HRA is hra_raw:
        # Z = ROUND(R+T+U, 0) = ROUND(basic_raw + lta + sa, 0)
        gross_for_pf = _round_half_up(basic_raw + lta + sa)

        # ── W: One-Time Bonus ──────────────────────────────────────────────────
        # Excel: =12360−V  [for resigned, top-up to full standard month salary]
        # Generalised: =StdSalary − GrossSalary
        # Gate: only if resigned AND total_days (calendar days up to DOE) ≥ threshold
        bonus = 0
        if is_resigned and total_days >= bonus_threshold:
            gap = std_sal - gross_salary
            if gap > 0:
                bonus = gap

        # ── X: Gratuity ───────────────────────────────────────────────────────
        # Excel: AQ = P (standard salary), AR = ROUND(AQ*15/26*AP, 0)
        # AQ = StdSalary (NOT basic_pct × StdSalary per formula AQ=PN)
        gratuity        = 0
        completed_years = 0
        last_drawn_basic = std_sal   # AQ = P (standard month salary column)
        if is_resigned and doj and doe:
            completed_years = _completed_years(doj, doe)
            if completed_years >= grat_min_years:
                gratuity = _round_half_up(
                    last_drawn_basic * grat_multiplier / grat_divisor * completed_years
                )

        # ── Y: Final Gross = V + W + X ────────────────────────────────────────
        final_gross = gross_salary + bonus + gratuity

        # ESI / Prof-tax base = Y − X = FinalGross − Gratuity = gross + bonus
        esi_base = final_gross - gratuity

        # ── AA: EPF Wages = ROUND(IF(Z>15000, 15000, Z), 0) ─────────────────
        epf_wages = _round_half_up(min(gross_for_pf, epf_ceiling))

        # ── AB: PF 12% = ROUND(IF(Z>15000, 1800, Z×12%), 0) ─────────────────
        if gross_for_pf > epf_ceiling:
            epf_employee = _round_half_up(epf_ceiling * epf_employee_rate)  # 1800
        else:
            epf_employee = _round_half_up(gross_for_pf * epf_employee_rate)

        # ── AD: ESI 0.75% = ROUNDUP(IF(P>21000, 0, (Y−X)×0.75%), 0) ─────────
        if std_sal > esi_exempt_threshold:
            esi_employee = 0
        else:
            esi_employee = _roundup(esi_base * esi_employee_rate)

        # ── AK: Profession Tax ────────────────────────────────────────────────
        # Excel: =IF((Y−X)≥20001, 200, IF((Y−X)≥15001, 150, 0))
        profession_tax = _profession_tax(esi_base, ptax_slabs)

        # ── AL: LWF (from config) ─────────────────────────────────────────────
        lwf = int(lwf_amount)

        # ── AM: PF+ESI+LWF ───────────────────────────────────────────────────
        pf_esi_lwf_total = epf_employee + esi_employee + lwf

        # ── AH/AI/AJ: Static deductions from employee_db.json ─────────────────
        emp_record  = emp_db.get(emp_id, {})
        tds         = float(emp_record.get("tds", 0))
        advance     = float(emp_record.get("advance", 0))
        insurance   = float(emp_record.get("insurance", 0))

        # ── AN: Net Salary ────────────────────────────────────────────────────
        # Excel: =SUM(ROUND(Y−(AH+AI+AJ+AK+AM),0),0)
        total_deductions = tds + advance + insurance + profession_tax + pf_esi_lwf_total
        net_salary = _round_half_up(final_gross - total_deductions)

        # ── Employer contributions ────────────────────────────────────────────
        # AE: EPF 8.33% = ROUND(AB/12%*8.33%, 0)
        pension      = _round_half_up(epf_employee / epf_employee_rate * epf_pension_rate)
        pf_employer  = epf_employee - pension
        # AG: ESI 3.25% — NOT rounded (matches xlsx)
        if std_sal > esi_exempt_threshold:
            esi_employer = 0.0
        else:
            esi_employer = esi_base * esi_employer_rate
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
            "mg_days":      mg_days,
            "ml":           ml,
            "ul":           ul,
            "total_days":   total_days,
            "util_lop":     util_lop,
            "payable_days": payable_days,
            # Leave balances
            "open_cl":  open_cl,  "open_sl":  open_sl,  "open_el":  open_el,
            "close_cl": close_cl, "close_sl": close_sl, "close_el": close_el,
            "close_mg": close_mg, "close_extra": close_extra,
            # Salary components (exact xlsx column mapping)
            "standard_salary":    std_sal,
            "current_salary_raw": current_salary_raw,
            "basic":              basic_raw,      # unrounded; rounded at gross_salary
            "hra":                hra_raw,
            "gross_salary":       gross_salary,   # V — ROUND(basic+hra+lta+sa)
            "bonus":              bonus,           # W — std_sal − gross_salary
            "gratuity":           gratuity,        # X — AR
            "completed_years":    completed_years, # AP
            "last_drawn_basic":   last_drawn_basic,# AQ — = std_sal
            "final_gross":        final_gross,     # Y
            "gross_for_pf":       gross_for_pf,    # Z
            # Employee deductions
            "epf_wages":       epf_wages,          # AA
            "epf_employee":    epf_employee,       # AB
            "esi_employee":    esi_employee,       # AD
            "profession_tax":  profession_tax,     # AK
            "lwf":             lwf,                # AL
            "tds":             tds,                # AH (from employee_db)
            "advance":         advance,            # AI (from employee_db)
            "insurance":       insurance,          # AJ (from employee_db)
            "pf_esi_lwf_total": pf_esi_lwf_total,  # AM
            "total_deductions": total_deductions,  # AH+AI+AJ+AK+AM
            # Net
            "net_salary":  net_salary,             # AN
            # Employer contributions
            "pension":        pension,             # AE
            "pf_employer":    pf_employer,         # AF
            "esi_employer":   round(esi_employer, 4),  # AG — unrounded
            "total_employer": round(total_employer, 4),
        })

    # ── Aggregates ─────────────────────────────────────────────────────────────
    summary = {
        "total_headcount":  len(employees),
        "active_count":     sum(1 for e in employees if e["status"] == "Active"),
        "resigned_count":   sum(1 for e in employees if e["status"] == "Resigned"),
        "maternity_count":  sum(1 for e in employees if e["status"] == "Maternity"),
        "long_leave_count": sum(1 for e in employees if e["status"] == "Long Leave"),
        "total_gross":      sum(e["final_gross"]        for e in employees),
        "total_net":        sum(e["net_salary"]         for e in employees),
        "total_bonus":      sum(e["bonus"]              for e in employees),
        "total_gratuity":   sum(e["gratuity"]           for e in employees),
        "total_epf_emp":    sum(e["epf_employee"]       for e in employees),
        "total_esi_emp":    sum(e["esi_employee"]       for e in employees),
        "total_deductions": sum(e["total_deductions"]   for e in employees),
        "total_employer":   round(sum(e["total_employer"] for e in employees), 2),
        "total_ctc":        round(sum(e["final_gross"] + e["total_employer"] for e in employees), 2),
    }

    return {"employees": employees, "summary": summary, "config": cfg}


# ── Export helpers ─────────────────────────────────────────────────────────────
def generate_payroll_csv(employees: list) -> str:
    cols = [
        "emp_id", "name", "email", "mobile", "doj", "doe", "customer", "project",
        "status", "slab",
        "present", "wo", "leaves", "hfl", "mg_days", "ml", "ul", "util_lop",
        "payable_days",
        "open_cl", "open_sl", "open_el", "close_cl", "close_sl", "close_el",
        "standard_salary", "basic", "hra", "gross_salary",
        "bonus", "gratuity", "completed_years", "last_drawn_basic",
        "final_gross", "gross_for_pf", "epf_wages",
        "epf_employee", "esi_employee", "profession_tax", "lwf",
        "tds", "advance", "insurance",
        "pf_esi_lwf_total", "total_deductions", "net_salary",
        "pension", "pf_employer", "esi_employer", "total_employer",
    ]
    df = pd.DataFrame(employees)
    # Ensure all expected cols exist (fill missing with 0)
    for c in cols:
        if c not in df.columns:
            df[c] = 0
    return df[cols].to_csv(index=False)


def generate_leave_balance_csv(employees: list) -> str:
    rows = [
        {
            "S.NO": i + 1,
            "EMP ID": e["emp_id"],
            "Names": e.get("name", ""),
            "Last Year Carry Forward": 0,
            "CL":  e["close_cl"],
            "SL":  e["close_sl"],
            "EL":  e["close_el"],
            "MG":  e["close_mg"],
            "Extra EL Balance": e["close_extra"],
        }
        for i, e in enumerate(employees)
    ]
    return pd.DataFrame(rows).to_csv(index=False)
