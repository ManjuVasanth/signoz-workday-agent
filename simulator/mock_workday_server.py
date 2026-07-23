"""
Mock Workday Tenant - Local practice server
Simulates:
  1. Human_Resources SOAP web service (Get_Workers) with Response_Filter pagination
  2. RaaS custom report endpoint (XML and JSON)

Run:    python mock_workday_server.py
Server: http://127.0.0.1:8443

Endpoints:
  POST /ccx/service/SUPER_TENANT/Human_Resources/v42.0   (SOAP Get_Workers)
  GET  /ccx/service/customreport2/SUPER_TENANT/ISU_Demo/Worker_Report?format=xml
  GET  /ccx/service/customreport2/SUPER_TENANT/ISU_Demo/Worker_Report?format=json
"""

import json
import math
import re
from flask import Flask, request, Response

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Fake tenant data: 23 workers so pagination (page size 10) needs 3 pages
# ---------------------------------------------------------------------------
FIRST = ["Aarav", "Meera", "John", "Priya", "Carlos", "Wei", "Sofia", "Liam",
         "Anika", "David", "Fatima", "Kenji", "Olivia", "Ravi", "Emma",
         "Noah", "Isabella", "Arjun", "Grace", "Mateo", "Hana", "Lucas", "Divya"]
LAST  = ["Sharma", "Iyer", "Smith", "Patel", "Gomez", "Chen", "Rossi", "Brown",
         "Kapoor", "Miller", "Khan", "Tanaka", "Davis", "Menon", "Wilson",
         "Garcia", "Moore", "Nair", "Lee", "Lopez", "Sato", "Martin", "Reddy"]
ORGS  = ["Finance", "HR Operations", "IT Services", "Audit", "Legal"]

# Reference pools for richer, deterministic demo data
STREETS = ["100 Maple Ave", "221 Oak St", "45 Pine Rd", "987 Cedar Ln",
           "12 Birch Way", "656 Elm Dr", "78 Willow Ct", "330 Aspen Blvd",
           "510 Walnut St", "64 Spruce Ter"]
CITIES = [("Irving", "TX", "75039"), ("Plano", "TX", "75024"),
          ("Dallas", "TX", "75201"), ("Frisco", "TX", "75034"),
          ("Austin", "TX", "73301"), ("Richardson", "TX", "75080")]
SPOUSE_FIRST = ["Anita", "Rahul", "Sara", "Michael", "Lena", "Vikram",
                "Nina", "Carlos", "Deepa", "Tom", "Yuki", "Sam"]
CHILD_FIRST = ["Aria", "Dev", "Maya", "Leo", "Zoe", "Kabir", "Ivy",
               "Rohan", "Ella", "Arnav", "Mila", "Vivaan"]
PARENT_FIRST = ["Ramesh", "Sunita", "George", "Lucia", "Hiroshi", "Carmen"]
# Single-instance related object: Manager, keyed by organization
ORG_MANAGER = {
    "Finance":       ("Sandeep Rao",     "30001", "+1-972-555-0101", "+1-972-555-0102"),
    "HR Operations": ("Laura Bennett",   "30002", "+1-469-555-0111", "+1-469-555-0112"),
    "IT Services":   ("Daniel Okoro",    "30003", "+1-214-555-0121", "+1-214-555-0122"),
    "Audit":         ("Priscilla Vance", "30004", "+1-972-555-0131", "+1-972-555-0132"),
    "Legal":         ("Marco Bianchi",   "30005", "+1-469-555-0141", "+1-469-555-0142"),
}
JOB_PROFILES = ["Accountant", "HR Generalist", "Software Engineer",
                "Auditor", "Legal Counsel"]
COMPANIES = ["Super Tenant Inc", "Super Tenant LLC"]

WORKERS = []
for i in range(23):
    eid = f"{21001 + i}"
    first, last = FIRST[i], LAST[i]
    org = ORGS[i % len(ORGS)]

    # Multi-instance related object: Payments (0-3 per worker)
    payments = []
    for p in range(i % 4):
        payments.append({
            "Type": "Spot Bonus" if p % 2 == 0 else "Referral Bonus",
            "Amount": str(250 * (p + 1)),
            "Date": f"2025-0{(p % 9) + 1}-10",
        })
    # Benefits enrollments (module: Benefits)
    benefits = [{"Plan": "Medical " + ("PPO" if i % 2 else "HMO"),
                 "Coverage": ["EE", "EE+1", "EE+Family"][i % 3],
                 "Employee_Cost": "120.00" if i % 2 else "95.00"}]
    if i % 3 == 0:
        benefits.append({"Plan": "Dental", "Coverage": "EE",
                         "Employee_Cost": "15.00"})
    if i % 4 == 0:
        benefits.append({"Plan": "401k", "Coverage": "EE",
                         "Employee_Cost": "200.00"})
    base_annual = 60000 + (i * 3700) % 90000
    bonus_total = sum(int(p["Amount"]) for p in payments)

    # Personal / contact data
    worker_age = 27 + (i * 5) % 33                       # 27..59
    dob = f"{2026 - worker_age}-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}"
    street = STREETS[i % len(STREETS)]
    city, state, zipc = CITIES[i % len(CITIES)]
    address = f"{street}, {city}, {state} {zipc}"
    email_primary = f"{first.lower()}.{last.lower()}@supertenant.demo"
    email_secondary = f"{first.lower()}{last.lower()}@gmail.demo"
    phone_home = f"+1-214-555-{1000 + i:04d}"
    phone_business = f"+1-469-555-{2000 + i:04d}"
    phone_work = f"+1-972-555-{3000 + i:04d}"

    # Multi-instance related object: Dependents (Spouse / Child / Parent)
    has_spouse = (i % 4 != 0)
    spouse_age = max(25, worker_age - (i % 7) - 1)
    spouse_name = f"{SPOUSE_FIRST[i % len(SPOUSE_FIRST)]} {last}"
    num_kids = i % 3                                     # 0, 1, 2
    dependents = []
    child_names, child_ages = [], []
    if has_spouse:
        s_dob = f"{2026 - spouse_age}-{((i + 3) % 12) + 1:02d}-{((i + 5) % 27) + 1:02d}"
        dependents.append({"Name": spouse_name, "Relationship": "Spouse",
                           "Age": str(spouse_age), "DOB": s_dob,
                           "Gender": "F" if i % 2 else "M"})
    for k in range(num_kids):
        cage = 3 + ((i + k * 6) % 16)                    # 3..18
        cname = f"{CHILD_FIRST[(i + k) % len(CHILD_FIRST)]} {last}"
        c_dob = f"{2026 - cage}-{((i + k) % 12) + 1:02d}-{((i + k * 2) % 27) + 1:02d}"
        dependents.append({"Name": cname, "Relationship": "Child",
                           "Age": str(cage), "DOB": c_dob,
                           "Gender": "M" if k % 2 else "F"})
        child_names.append(cname)
        child_ages.append(str(cage))
    if i % 5 == 0:                                       # some have a Parent
        page = 60 + (i % 20)
        pname = f"{PARENT_FIRST[i % len(PARENT_FIRST)]} {last}"
        dependents.append({"Name": pname, "Relationship": "Parent",
                           "Age": str(page), "DOB": f"{2026 - page}-04-12",
                           "Gender": "M" if i % 2 else "F"})

    # Emergency contact (with relationship)
    if has_spouse:
        ec_name, ec_rel = spouse_name, "Spouse"
    else:
        ec_name = f"{PARENT_FIRST[i % len(PARENT_FIRST)]} {last}"
        ec_rel = "Parent"
    ec_phone = f"+1-214-555-{7000 + i:04d}"

    # Single-instance related object: Manager
    mgr_name, mgr_eid, mgr_p1, mgr_p2 = ORG_MANAGER[org]
    mgr_email = mgr_name.lower().replace(" ", ".") + "@supertenant.demo"
    manager = {"Name": mgr_name, "Email": mgr_email,
               "Phone_Primary": mgr_p1, "Phone_Secondary": mgr_p2,
               # real Workday traversal field names (Supervisory Org -> Manager)
               "Employee_ID": mgr_eid,
               "Primary Work Email": mgr_email,
               "Primary Work Phone": mgr_p1,
               # Worker -> Manager -> Contact Info -> Email
               "Contact_Info": {"Email": mgr_email, "Phone": mgr_p1}}

    # Emergency Contacts (related object). Real path:
    # Worker -> Emergency Contacts -> Emergency Contact Person -> Name
    emergency_contacts = [{
        "Emergency_Contact_Person": {"Name": ec_name, "Relationship": ec_rel},
        "Relationship": ec_rel,
        "Phone": ec_phone,
        "Primary": "1",
    }]

    # Dependents -> Personal Info -> Date of Birth (nested path for ESI)
    for _d in dependents:
        _d["Personal_Info"] = {"Date_of_Birth": _d.get("DOB", "")}

    # --- Related objects from the Related Object Path cheat sheet ---
    job_profile = JOB_PROFILES[i % len(JOB_PROFILES)]
    level = ["I", "II", "III", "Senior", "Lead"][i % 5]
    business_title = f"{job_profile} {level}"
    worker_type = "Employee" if i % 6 else "Contingent Worker"
    employee_type = "Regular" if i % 5 else "Fixed Term"
    cost_center = f"CC-{1000 + (i % len(ORGS)) * 10}"
    company = COMPANIES[i % len(COMPANIES)]
    pay_group = "USA Biweekly" if i % 4 else "USA Monthly"
    comp_grade = f"Grade {(i % 8) + 1}"
    location = f"{city} Office"
    sup_org = f"{org} ({mgr_name})"
    time_type = "Full time" if i % 7 else "Part time"

    # Worker -> Position -> ... (single-instance related object)
    position = {
        "Supervisory_Organization": sup_org,
        "Location": location,
        "Job_Profile": job_profile,
        "Business_Title": business_title,
        "Job_Details": {"Time_Type": time_type},
        "Organization_Assignments": {"Cost_Center": cost_center,
                                     "Company": company},
    }
    # Worker -> Job/Position Details -> Worker Type / Employee Type
    job_position_details = {"Worker_Type": worker_type,
                            "Employee_Type": employee_type}
    # Worker -> Payroll/Pay Group Assignment -> Pay Group
    payroll_assignment = {"Pay_Group": pay_group}
    # Worker -> Compensation -> Grade / Compensation Package/Plan -> Amount
    compensation = {"Grade": comp_grade,
                    "Compensation_Package_Plan": {"Amount": str(base_annual)}}
    # Worker -> Contact Information -> Email / Phone
    contact_information = {"Email": email_primary, "Phone": phone_work}

    WORKERS.append({
        "Employee_ID": eid,
        "First_Name": first,
        "Last_Name": last,
        "Full_Name": f"{first} {last}",
        # Email (work kept as legacy "Email" + explicit primary/secondary)
        "Email": email_primary,
        "Email_Primary": email_primary,
        "Email_Secondary": email_secondary,
        # Address
        "Address": address,
        "Address_Line_1": street,
        "City": city, "State": state, "Postal_Code": zipc, "Country": "USA",
        # Phones
        "Phone_Home": phone_home,
        "Phone_Business": phone_business,
        "Phone_Work": phone_work,
        # Personal
        "Date_of_Birth": dob, "DOB": dob, "Age": str(worker_age),
        "Hire_Date": f"20{18 + (i % 7)}-0{1 + (i % 9)}-15",
        "Org": org, "Organization": org,
        "Active": "1" if i % 9 != 8 else "0",
        # Compensation module
        "Base_Salary": str(base_annual),
        "Total_Base_Pay_Annualized": str(base_annual),
        "Total_Compensation": str(base_annual + bonus_total),
        "Currency": "USD",
        "Comp_Plan": "Salary Plan",
        "Pay_Group": "USA Biweekly" if i % 4 else "USA Monthly",
        # Multi-instance related objects
        "Payments": payments,
        "Benefits": benefits,
        "Dependents": dependents,
        # Dependent roll-ups (Worker-level, single value)
        "Dependent_Count": str(len(dependents)),
        "Dependent_Names": ", ".join(d["Name"] for d in dependents),
        "Spouse_Name": spouse_name if has_spouse else "",
        "Spouse_Age": str(spouse_age) if has_spouse else "",
        "Child_Names": ", ".join(child_names),
        "Child_Ages": ", ".join(child_ages),
        # Emergency contact
        "Emergency_Contact_Name": ec_name,
        "Emergency_Contact_Relationship": ec_rel,
        "Emergency_Contact_Phone": ec_phone,
        "Emergency_Contact_Address": address,
        "Emergency_Contacts": emergency_contacts,
        # Single-instance related object: Manager
        "Manager": manager,
        "Manager_Name": mgr_name,
        "Manager_Email": mgr_email,
        "Manager_Phone_Primary": mgr_p1,
        "Manager_Phone_Secondary": mgr_p2,
        # Related objects (Related Object Path cheat sheet)
        "Position": position,
        "Job_Position_Details": job_position_details,
        "Payroll_Pay_Group_Assignment": payroll_assignment,
        "Compensation": compensation,
        "Contact_Information": contact_information,
    })

PAGE_SIZE_DEFAULT = 10
WD_NS = "urn:com.workday/bsvc"


def worker_xml(w):
    return f"""      <wd:Worker>
        <wd:Worker_Reference>
          <wd:ID wd:type="Employee_ID">{w['Employee_ID']}</wd:ID>
        </wd:Worker_Reference>
        <wd:Worker_Data>
          <wd:Worker_ID>{w['Employee_ID']}</wd:Worker_ID>
          <wd:Personal_Data>
            <wd:Name_Data>
              <wd:Legal_Name_Data>
                <wd:Name_Detail_Data>
                  <wd:First_Name>{w['First_Name']}</wd:First_Name>
                  <wd:Last_Name>{w['Last_Name']}</wd:Last_Name>
                </wd:Name_Detail_Data>
              </wd:Legal_Name_Data>
            </wd:Name_Data>
            <wd:Contact_Data>
              <wd:Email_Address_Data>
                <wd:Email_Address>{w['Email']}</wd:Email_Address>
              </wd:Email_Address_Data>
            </wd:Contact_Data>
          </wd:Personal_Data>
          <wd:Employment_Data>
            <wd:Worker_Status_Data>
              <wd:Active>{w['Active']}</wd:Active>
              <wd:Hire_Date>{w['Hire_Date']}</wd:Hire_Date>
            </wd:Worker_Status_Data>
          </wd:Employment_Data>
          <wd:Organization_Data>
            <wd:Organization_Name>{w['Org']}</wd:Organization_Name>
          </wd:Organization_Data>
        </wd:Worker_Data>
      </wd:Worker>"""


# ---------------------------------------------------------------------------
# 1) SOAP: Get_Workers with Response_Filter (Page / Count) pagination
# ---------------------------------------------------------------------------
@app.route("/ccx/service/SUPER_TENANT/Human_Resources/v42.0", methods=["POST"])
def human_resources():
    body = request.data.decode("utf-8", errors="ignore")

    if "Get_Workers_Request" not in body:
        fault = """<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body>
    <env:Fault>
      <faultcode>env:Client</faultcode>
      <faultstring>Validation error occurred. Invalid request: only Get_Workers_Request is supported by this mock.</faultstring>
    </env:Fault>
  </env:Body>
</env:Envelope>"""
        return Response(fault, status=500, mimetype="text/xml")

    # Parse Response_Filter (Page, Count) like real Workday
    page_m = re.search(r"<[\w]*:?Page>(\d+)</", body)
    count_m = re.search(r"<[\w]*:?Count>(\d+)</", body)
    page = int(page_m.group(1)) if page_m else 1
    count = int(count_m.group(1)) if count_m else PAGE_SIZE_DEFAULT
    count = max(1, min(count, 999))

    total = len(WORKERS)
    total_pages = math.ceil(total / count)
    page = max(1, min(page, total_pages))
    chunk = WORKERS[(page - 1) * count: page * count]

    workers_block = "\n".join(worker_xml(w) for w in chunk)
    envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body>
    <wd:Get_Workers_Response xmlns:wd="{WD_NS}" wd:version="v42.0">
      <wd:Response_Filter>
        <wd:Page>{page}</wd:Page>
        <wd:Count>{count}</wd:Count>
      </wd:Response_Filter>
      <wd:Response_Results>
        <wd:Total_Results>{total}</wd:Total_Results>
        <wd:Total_Pages>{total_pages}</wd:Total_Pages>
        <wd:Page_Results>{len(chunk)}</wd:Page_Results>
        <wd:Page>{page}</wd:Page>
      </wd:Response_Results>
      <wd:Response_Data>
{workers_block}
      </wd:Response_Data>
    </wd:Get_Workers_Response>
  </env:Body>
</env:Envelope>"""
    return Response(envelope, mimetype="text/xml")


# ---------------------------------------------------------------------------
# 2) Calculated Fields engine + Custom Reports (RaaS)
#    - calculated_fields.json = "Create Calculated Field" definitions
#    - report_definitions.json = "Create Custom Report" definitions
#    - Only reports with enable_as_web_service=true are served via RaaS
# ---------------------------------------------------------------------------
import os
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE_DIR, "calculated_fields.json")) as f:
    CALC_FIELDS = json.load(f).get("Worker", [])
with open(os.path.join(BASE_DIR, "report_definitions.json")) as f:
    REPORTS = {r["report_name"]: r for r in json.load(f)}

BASE_ALIASES = {  # report column label -> worker key
    "Organization": "Org",
    "Total Compensation": "Total_Compensation",
    "Total Base Pay Annualized - Amount": "Total_Base_Pay_Annualized",
}


def _num(v):
    """Numeric coercion with clean string output."""
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return 0.0


def _fmt_num(f):
    return str(int(f)) if f == int(f) else f"{f:.2f}"


def _operand(op, ctx):
    """Operand is {'field': name} or {'value': literal} or {'text': literal}."""
    if isinstance(op, dict):
        if "field" in op:
            return ctx.get(op["field"], "")
        return op.get("value", op.get("text", ""))
    return op


def _parse_date(s):
    y, m, d = map(int, str(s).split("-"))
    return date(y, m, d)


def _get_path(obj, path):
    """Resolve a dotted relationship path on a related instance, e.g.
    'Emergency_Contact_Person.Name'. Returns '' if any hop is missing."""
    cur = obj
    for part in str(path).split("."):
        if isinstance(cur, dict):
            cur = cur.get(part, "")
        else:
            return ""
    return cur


def _ee_num(x):
    try:
        return float(str(x).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return None


def _ee_match(left, op, right):
    """Operator matcher for inline Evaluate Expression conditions."""
    s = "" if left is None else str(left)
    t = "" if right is None else str(right)
    if op == "is empty":
        return s == ""
    if op == "is not empty":
        return s != ""
    if op == "contains":
        return t.lower() in s.lower()
    ln, rn = _ee_num(s), _ee_num(t)
    if op == "greater than":
        return ln is not None and rn is not None and ln > rn
    if op == "greater than or equal to":
        return ln is not None and rn is not None and ln >= rn
    if op == "less than":
        return ln is not None and rn is not None and ln < rn
    if op == "less than or equal to":
        return ln is not None and rn is not None and ln <= rn
    if op == "not equal to":
        return (ln != rn) if (ln is not None and rn is not None) else (s.lower() != t.lower())
    return (ln == rn) if (ln is not None and rn is not None) else (s.lower() == t.lower())


def eval_calc_field(defn, ctx):
    """Calculated-field engine mirroring Workday functions.

    ctx = worker base fields + previously evaluated calc fields,
    so calc fields can chain (like real Workday)."""
    fn = defn["function"]

    # ----- Text functions -----
    if fn == "Text Constant":                      # TC
        return defn["value"]

    if fn == "Concatenate Text":                   # CT
        return "".join(str(_operand(p, ctx)) for p in defn["parts"])

    if fn == "Substring Text":                     # ST
        # source can be a base field or another calc field (text_field alias)
        src = str(ctx.get(defn.get("source", defn.get("text_field", "")), ""))
        stype = defn.get("substring_type")
        delim = defn.get("delimiter", " ")
        delim = " " if delim in ("Single Space", "single_space") else delim
        direction = defn.get("direction", "Forward")
        backward = str(direction).lower().startswith("b")

        def _trim(s):
            return s.strip() if defn.get("trim", True) else s

        if stype == "After a Delimiter":
            # Forward = text after FIRST delimiter; Backward = after LAST delimiter
            if delim in src:
                out = src.split(delim, 1)[1] if not backward \
                    else src.rsplit(delim, 1)[1]
            else:
                out = src
            return _trim(out)

        if stype == "Before a Delimiter":
            if delim in src:
                out = src.split(delim, 1)[0] if not backward \
                    else src.rsplit(delim, 1)[0]
            else:
                out = src
            return _trim(out)

        if stype == "Between two Delimiters":
            d1, d2 = delim, defn.get("delimiter2", delim)
            d2 = " " if d2 in ("Single Space", "single_space") else d2
            out = src
            if d1 in src:
                out = src.split(d1, 1)[1]
            if d2 in out:
                out = out.rsplit(d2, 1)[0] if backward else out.split(d2, 1)[0]
            return _trim(out)

        if stype == "Fixed Position":
            start = int(defn.get("start", 1)) - 1  # Workday is 1-based
            length = int(defn.get("length", len(src)))
            return _trim(src[start:start + length])

        # --- backward-compatible legacy schema ---
        if "after" in defn:
            return src.split(defn["after"], 1)[1] if defn["after"] in src else src
        start = defn.get("start", 1) - 1
        length = defn.get("length", len(src))
        return src[start:start + length]

    if fn == "Format Text":                        # FT
        out = defn["template"].format(**{k: v for k, v in ctx.items()
                                         if not isinstance(v, list)})
        case = defn.get("case")
        if case == "upper":
            return out.upper()
        if case == "lower":
            return out.lower()
        return out

    # ----- Lookup / condition functions -----
    # ----- Constants & conversions -----
    if fn == "Numeric Constant":                   # NC
        return _fmt_num(_num(defn["value"]))

    if fn == "Date Constant":                      # DC
        return date.today().isoformat() if defn.get("today") else defn["value"]

    if fn == "Text Length":                        # TL
        return str(len(str(ctx.get(defn["source"], ""))))

    if fn == "Convert Text to Number":             # CTN
        raw = re.sub(r"[^\d.\-]", "", str(ctx.get(defn["source"], "0")))
        return _fmt_num(_num(raw or 0))

    if fn == "Format Number":                      # FN
        v = _num(ctx.get(defn["source"], 0))
        dec = int(defn.get("decimals", 2))
        s = f"{v:,.{dec}f}" if defn.get("thousands", True) else f"{v:.{dec}f}"
        return defn.get("prefix", "") + s + defn.get("suffix", "")

    if fn == "Format Date":                        # FD
        d = _parse_date(ctx[defn["source"]])
        f = defn.get("format", "MM/dd/yyyy")
        f = (f.replace("yyyy", "%Y").replace("MMM", "%b")
              .replace("MM", "%m").replace("dd", "%d"))
        return d.strftime(f)

    if fn == "Convert Currency":                   # CC
        amt = _num(ctx.get(defn["source"], 0))
        rate = _num(defn.get("rates", {}).get(defn.get("to", ""), 1))
        return _fmt_num(round(amt * rate, 2))

    # ----- Lookup family additions -----
    if fn == "Lookup Range Band":                  # LRB
        v = _num(ctx.get(defn["source"], 0))
        for band in defn.get("bands", []):
            lo = _num(band.get("min", float("-inf")))
            hi = _num(band.get("max", float("inf")))
            if lo <= v <= hi:
                return band["value"]
        return defn.get("default", "")

    if fn == "Lookup Translated Value":            # LTV
        return defn.get("translations", {}).get(
            str(ctx.get(defn["source"], "")),
            str(ctx.get(defn["source"], "")))

    if fn == "Aggregate Related Instances":        # ARI
        items = ctx.get(defn["source"], [])
        vals = [str(it.get(defn["value_field"], "")) for it in items]
        return defn.get("delimiter", ", ").join(v for v in vals if v)

    if fn == "Lookup Related Value":               # LRV
        # Legacy value-map form (kept for older fields like P_Org_Code)
        if "lookup" in defn:
            return defn["lookup"].get(str(ctx.get(defn["source"], "")), "")
        # Workday form: look up a field on a SINGLE-INSTANCE related object.
        # `related` = single-instance related BO (e.g. Manager) or the result
        # of an Extract Single Instance; `return_field` = field to return.
        obj = ctx.get(defn.get("related", ""))
        if isinstance(obj, dict):
            return str(_get_path(obj, defn.get("return_field", "")))
        if isinstance(obj, list) and obj:            # tolerate a 1-item list
            return str(_get_path(obj[0], defn.get("return_field", "")))
        return ""

    if fn == "Evaluate Expression":                # EE (CASE / If-Then-Else)
        conds = defn.get("conditions")
        if conds is not None:
            def _ref(r):
                # a calc-field name resolves to its value; anything else is literal
                if r and any(c.get("field_name") == r for c in CALC_FIELDS):
                    return str(ctx.get(r, r))
                return r
            # Real Workday: evaluate condition rows in order, return the first
            # true row's value; if none true, return the default value.
            for c in conds:
                if c.get("op") and c.get("field"):          # inline comparison
                    ok = _ee_match(ctx.get(c["field"], ""), c["op"],
                                   c.get("value", ""))
                else:                                        # boolean CF reference
                    cv = str(ctx.get(c.get("condition", ""), "")).strip().lower()
                    ok = cv in ("true", "1", "yes", "y")
                if ok:
                    return _ref(c.get("return", ""))
            return _ref(defn.get("default", ""))
        # legacy single if/then/else
        cond = str(ctx.get(defn["condition_field"])) == str(defn["equals"])
        return defn["then"] if cond else defn["else"]

    if fn == "True/False Condition":               # TF
        left = ctx.get(defn["condition_field"], "")
        op = defn.get("operator", "equals")
        right = defn["value"]
        if op == "equals":
            result = str(left) == str(right)
        elif op == "not_equals":
            result = str(left) != str(right)
        elif op == "greater_than":
            result = _num(left) > _num(right)
        elif op == "less_than":
            result = _num(left) < _num(right)
        else:
            result = False
        return "true" if result else "false"

    # ----- Arithmetic -----
    if fn == "Arithmetic Calculation":             # AC
        vals = [_num(_operand(o, ctx)) for o in defn["operands"]]
        op = defn["operation"]
        out = vals[0]
        for v in vals[1:]:
            if op == "add":
                out += v
            elif op == "subtract":
                out -= v
            elif op == "multiply":
                out *= v
            elif op == "divide":
                out = out / v if v else 0
        return _fmt_num(out)

    # ----- Date functions -----
    if fn == "Date Difference":                    # DD
        start = _parse_date(ctx[defn["source"]])
        today = date.today()
        years = today.year - start.year - ((today.month, today.day) <
                                           (start.month, start.day))
        return str(years)

    if fn == "Increment or Decrement Date":        # IDD
        d = _parse_date(ctx[defn["source"]])
        inc = defn.get("increment", {})
        y = d.year + inc.get("years", 0)
        m = d.month + inc.get("months", 0)
        y += (m - 1) // 12
        m = (m - 1) % 12 + 1
        day = min(d.day, 28) if m == 2 else d.day
        d2 = date(y, m, day)
        days = inc.get("days", 0)
        if days:
            from datetime import timedelta
            d2 = d2 + timedelta(days=days)
        return d2.isoformat()

    if fn == "Build Date":                         # BD
        def part(spec):
            if isinstance(spec, dict):
                src = _parse_date(ctx[spec["from_field"]])
                return getattr(src, spec["part"])
            return spec
        return date(part(defn["year"]), part(defn["month"]),
                    part(defn["day"])).isoformat()

    # ----- Instance functions (multi-instance lists) -----
    if fn == "Count Related Instance":             # CRI
        return str(len(ctx.get(defn["source"], [])))

    if fn == "Sum Related Instance":               # SRI
        items = ctx.get(defn["source"], [])
        return _fmt_num(sum(_num(it.get(defn["value_field"], 0))
                            for it in items))

    if fn == "Extract Multi-Instance":             # EMI
        # Extracts MANY instances of a related BO matching a condition.
        # Returns 0/1/many instances; if return_field given, returns those
        # values clubbed together (what you display in a report column).
        items = ctx.get(defn["source"], [])
        cond = defn.get("where") or defn.get("condition")
        if cond:
            items = [it for it in items if _match(it, cond)]
        rf = defn.get("return_field")
        if rf:
            return defn.get("delimiter", ", ").join(
                str(_get_path(it, rf)) for it in items)
        return items                               # list -> usable by CRI/SRI/ARI

    if fn == "Extract Single Instance":            # ESI
        # Extracts ONE instance of a related BO (first/last, optionally after
        # a condition), then returns one field from it.
        items = ctx.get(defn["source"], [])
        cond = defn.get("where") or defn.get("condition")
        if cond:
            items = [it for it in items if _match(it, cond)]
        if not items:
            return ""
        if defn.get("sort_field"):
            items = sorted(items, key=lambda it: it.get(defn["sort_field"], ""))
        chosen = items[-1] if defn.get("select") == "last" else items[0]
        rf = defn.get("return_field") or defn.get("value_field")
        return str(_get_path(chosen, rf)) if rf else str(chosen)

    return ""


def _match(item, cond):
    """Condition matcher for EMI/ESI (mirrors a True/False Condition)."""
    left = item.get(cond.get("field", ""), "")
    op = cond.get("operator", "equals")
    right = cond.get("equals", cond.get("value", ""))
    if op == "not_equals":
        return str(left) != str(right)
    if op == "greater_than":
        return _num(left) > _num(right)
    if op == "less_than":
        return _num(left) < _num(right)
    if op == "is_true":
        return str(left).lower() in ("true", "1", "yes")
    return str(left) == str(right)               # equals (default)


def _render(v):
    """Render a value for report output. Multi-instance lists are summarized."""
    if isinstance(v, list):
        return "; ".join(" ".join(str(x) for x in it.values())
                         if isinstance(it, dict) else str(it) for it in v)
    return v


def worker_row(worker, columns):
    """Evaluate ALL calc fields in definition order (allows chaining),
    then project the requested report columns."""
    ctx = dict(worker)
    for defn in CALC_FIELDS:
        ctx[defn["field_name"]] = eval_calc_field(defn, ctx)
    row = {}
    for col in columns:
        row[col] = _render(ctx.get(BASE_ALIASES.get(col, col), ""))
    return row


# Related Business Objects: worker key + cardinality.
#   multi  = many instances per worker -> values club together in one row
#   single = one instance per worker  -> one value
RELATED_OBJECTS = {
    "Dependents": ("Dependents", "multi"),
    "Payments":   ("Payments",   "multi"),
    "Benefits":   ("Benefits",   "multi"),
    "Benefit Enrollment": ("Benefits", "multi"),
    "Manager":    ("Manager",    "single"),
    "Emergency Contacts": ("Emergency_Contacts", "multi"),
    "Position":   ("Position",   "single"),
    "Job/Position Details": ("Job_Position_Details", "single"),
    "Payroll/Pay Group Assignment": ("Payroll_Pay_Group_Assignment", "single"),
    "Compensation": ("Compensation", "single"),
    "Contact Information": ("Contact_Information", "single"),
}
MULTI_BOS = {k for k, (_, c) in RELATED_OBJECTS.items() if c == "multi"}


def worker_context(worker):
    """Worker fields + all evaluated calc fields (used for scalar columns,
    filters, sort, and prompts)."""
    ctx = dict(worker)
    for defn in CALC_FIELDS:
        ctx[defn["field_name"]] = eval_calc_field(defn, ctx)
    return ctx


def resolve_instances(worker, business_object, field):
    """Return the list of values for a (business object, field) column.

    Multi-instance related objects return one value per instance, so the
    caller can club them together in a single worker row. Worker and
    single-instance objects return a one-element list."""
    bo = business_object or "Worker"
    # A calculated field is defined on the Worker BO, so it is always a
    # worker-level scalar - even when the report groups it under a related
    # business object header. Resolve it as a scalar so related-object calc
    # fields (e.g. Count of Dependents, Aggregate of Dependent Names) show
    # their value instead of one blank per instance.
    if any(d["field_name"] == field for d in CALC_FIELDS):
        ctx = worker_context(worker)
        return [_render(ctx.get(field, ""))]
    if bo in RELATED_OBJECTS:
        key, card = RELATED_OBJECTS[bo]
        obj = worker.get(key)
        if card == "multi":
            return [str(_get_path(inst, field)) for inst in (obj or [])]
        if isinstance(obj, dict):                       # single, e.g. Manager
            return [str(_get_path(obj, field))]
        return [str(worker.get(f"{bo}_{field}", worker.get(field, "")))]
    # Primary Business Object (Worker): scalar, resolved against full context
    ctx = worker_context(worker)
    return [_render(ctx.get(BASE_ALIASES.get(field, field), ""))]


@app.route("/ccx/service/customreport2/SUPER_TENANT/ISU_Demo/<report_name>")
def raas_report(report_name):
    rpt = REPORTS.get(report_name)

    if rpt is None:
        return Response("invalid request: report not found", status=404,
                        mimetype="text/plain")

    # Realistic behavior: report exists but is NOT enabled as web service
    if not rpt.get("enable_as_web_service"):
        return Response(
            "invalid request: the report is not enabled as a web service. "
            "Edit the report > Advanced tab > check 'Enable As Web Service'.",
            status=403, mimetype="text/plain")

    # Report prompts: required prompts must arrive as URL parameters,
    # exactly like real RaaS (?Org=Finance&format=xml). Missing required
    # prompts abort the run - the reason Studio integrations need
    # launch parameters wired through to the report call.
    prompt_filters = []
    missing = []
    for pr in rpt.get("prompts", []):
        val = request.args.get(pr["name"])
        if val is None or val == "":
            if pr.get("required"):
                missing.append(pr["name"])
        else:
            prompt_filters.append((pr.get("field", pr["name"]), val))
    if missing:
        return Response(
            "invalid request: the report cannot run because values were "
            "not provided for required prompts: " + ", ".join(missing) +
            ". Pass them as URL parameters, e.g. ?" + missing[0] +
            "=<value>&format=xml.",
            status=500, mimetype="text/plain")

    # Build rows (apply calc fields), then apply report filter
    rows = [worker_row(w, rpt["columns"]) for w in WORKERS]
    flt = rpt.get("filter")
    if flt:
        rows = [r for r in rows if r.get(flt["field"]) == flt["equals"]]
    for f_field, f_val in prompt_filters:
        rows = [r for r in rows if str(r.get(f_field, "")) == f_val]

    fmt = request.args.get("format", "xml").lower()
    if fmt == "json":
        return Response(json.dumps({"Report_Entry": rows}, indent=2),
                        mimetype="application/json")

    ns = f"urn:com.workday.report/{report_name}"
    entries = "\n".join(
        "  <wd:Report_Entry>\n" +
        "\n".join(f"    <wd:{k}>{v}</wd:{k}>" for k, v in row.items()) +
        "\n  </wd:Report_Entry>"
        for row in rows)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<wd:Report_Data xmlns:wd="{ns}">
{entries}
</wd:Report_Data>"""
    return Response(xml, mimetype="text/xml")


# ---------------------------------------------------------------------------
# 3) Inbound: Compensation web service - Request_One_Time_Payment
#    (the Deliver step target of an Inbound EIB)
# ---------------------------------------------------------------------------
VALID_IDS = {w["Employee_ID"] for w in WORKERS}
PAYMENT_LOG = []  # what the "tenant" has loaded


@app.route("/ccx/service/SUPER_TENANT/Compensation/v42.0", methods=["POST"])
def compensation():
    body = request.data.decode("utf-8", errors="ignore")

    if "Get_Compensation" in body:
        entries = "\n".join(
            f"""      <wd:Compensation_Data>
        <wd:Worker_Reference><wd:ID wd:type="Employee_ID">{w['Employee_ID']}</wd:ID></wd:Worker_Reference>
        <wd:Compensation_Plan>{w['Comp_Plan']}</wd:Compensation_Plan>
        <wd:Base_Salary>{w['Base_Salary']}</wd:Base_Salary>
        <wd:Currency>{w['Currency']}</wd:Currency>
        <wd:Pay_Group>{w['Pay_Group']}</wd:Pay_Group>
      </wd:Compensation_Data>""" for w in WORKERS)
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body>
    <wd:Get_Compensation_Response xmlns:wd="{WD_NS}" wd:version="v42.0">
      <wd:Response_Data>
{entries}
      </wd:Response_Data>
    </wd:Get_Compensation_Response>
  </env:Body>
</env:Envelope>"""
        return Response(xml, mimetype="text/xml")

    if "Request_Compensation_Change" in body:
        emp_m = re.search(r'wd:type="Employee_ID">(\d+)<', body)
        sal_m = re.search(r"<[\w]*:?(?:New_Base_Salary|Amount)>([\d.]+)</", body)
        emp_id = emp_m.group(1) if emp_m else None
        w = next((x for x in WORKERS if x["Employee_ID"] == emp_id), None)
        if not w or not sal_m:
            fault = f"""<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body><env:Fault><faultcode>env:Client</faultcode>
    <faultstring>Validation error occurred. Invalid ID value. '{emp_id}' is not a valid ID value for type = 'Employee_ID'</faultstring>
  </env:Fault></env:Body>
</env:Envelope>"""
            return Response(fault, status=500, mimetype="text/xml")
        old_sal = w["Base_Salary"]
        w["Base_Salary"] = sal_m.group(1)
        COMP_CHANGE_LOG.append({"Employee_ID": emp_id, "Old": old_sal,
                                "New": w["Base_Salary"]})
        ok = f"""<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body>
    <wd:Request_Compensation_Change_Response xmlns:wd="{WD_NS}">
      <wd:Event_Reference><wd:ID wd:type="WID">COMP_CHANGE-{len(COMP_CHANGE_LOG)}</wd:ID></wd:Event_Reference>
    </wd:Request_Compensation_Change_Response>
  </env:Body>
</env:Envelope>"""
        return Response(ok, mimetype="text/xml")

    if "Request_One_Time_Payment" not in body:
        fault = """<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body>
    <env:Fault>
      <faultcode>env:Client</faultcode>
      <faultstring>Validation error occurred. Invalid request: supported operations are Get_Compensation, Request_Compensation_Change, Request_One_Time_Payment.</faultstring>
    </env:Fault>
  </env:Body>
</env:Envelope>"""
        return Response(fault, status=500, mimetype="text/xml")

    emp_m = re.search(r'wd:type="Employee_ID">(\d+)<', body)
    amt_m = re.search(r"<[\w]*:?Amount>([\d.]+)</", body)
    emp_id = emp_m.group(1) if emp_m else None
    amount = amt_m.group(1) if amt_m else None

    # Workday-style validation fault for unknown worker
    if emp_id not in VALID_IDS:
        fault = f"""<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body>
    <env:Fault>
      <faultcode>env:Client</faultcode>
      <faultstring>Validation error occurred. Invalid ID value. '{emp_id}' is not a valid ID value for type = 'Employee_ID'</faultstring>
    </env:Fault>
  </env:Body>
</env:Envelope>"""
        return Response(fault, status=500, mimetype="text/xml")

    PAYMENT_LOG.append({"Employee_ID": emp_id, "Amount": amount})
    event_id = f"ONE_TIME_PAYMENT_EVENT-{1000 + len(PAYMENT_LOG)}"
    ok = f"""<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body>
    <wd:Request_One_Time_Payment_Response xmlns:wd="{WD_NS}" wd:version="v42.0">
      <wd:Event_Reference>
        <wd:ID wd:type="WID">{event_id}</wd:ID>
      </wd:Event_Reference>
    </wd:Request_One_Time_Payment_Response>
  </env:Body>
</env:Envelope>"""
    return Response(ok, mimetype="text/xml")


@app.route("/loaded_payments")
def loaded_payments():
    """Inspect what the inbound EIB actually loaded into the 'tenant'."""
    return Response(json.dumps(PAYMENT_LOG, indent=2), mimetype="application/json")


COMP_CHANGE_LOG = []
PAYROLL_INPUTS = []


# ---------------------------------------------------------------------------
# 4) Benefits module: Get_Benefit_Enrollments
# ---------------------------------------------------------------------------
@app.route("/ccx/service/SUPER_TENANT/Benefits_Administration/v42.0",
           methods=["POST"])
def benefits_admin():
    body = request.data.decode("utf-8", errors="ignore")
    if "Get_Benefit_Enrollments" not in body:
        fault = """<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body><env:Fault><faultcode>env:Client</faultcode>
    <faultstring>Validation error occurred. Invalid request: only Get_Benefit_Enrollments is supported by this mock.</faultstring>
  </env:Fault></env:Body>
</env:Envelope>"""
        return Response(fault, status=500, mimetype="text/xml")
    blocks = []
    for w in WORKERS:
        if w["Active"] != "1":
            continue
        plans = "\n".join(
            f"""        <wd:Enrollment>
          <wd:Benefit_Plan>{b['Plan']}</wd:Benefit_Plan>
          <wd:Coverage_Level>{b['Coverage']}</wd:Coverage_Level>
          <wd:Employee_Cost>{b['Employee_Cost']}</wd:Employee_Cost>
        </wd:Enrollment>""" for b in w["Benefits"])
        blocks.append(f"""      <wd:Worker_Benefit_Data>
        <wd:Worker_Reference><wd:ID wd:type="Employee_ID">{w['Employee_ID']}</wd:ID></wd:Worker_Reference>
        <wd:Last_Name>{w['Last_Name']}</wd:Last_Name>
        <wd:First_Name>{w['First_Name']}</wd:First_Name>
{plans}
      </wd:Worker_Benefit_Data>""")
    xml = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
           "<env:Envelope xmlns:env=\"http://schemas.xmlsoap.org/soap/envelope/\">\n"
           "  <env:Body>\n"
           f"    <wd:Get_Benefit_Enrollments_Response xmlns:wd=\"{WD_NS}\">\n"
           "      <wd:Response_Data>\n" + "\n".join(blocks) +
           "\n      </wd:Response_Data>\n"
           "    </wd:Get_Benefit_Enrollments_Response>\n"
           "  </env:Body>\n</env:Envelope>")
    return Response(xml, mimetype="text/xml")


# ---------------------------------------------------------------------------
# 5) Payroll module: Import_Payroll_Input (bulk), Submit_Payroll_Input
#    (single), Get_Payroll_Results. Put_Payroll_Input -> deprecation fault.
# ---------------------------------------------------------------------------
@app.route("/ccx/service/SUPER_TENANT/Payroll/v42.0", methods=["POST"])
def payroll():
    body = request.data.decode("utf-8", errors="ignore")
    valid_ids = {w["Employee_ID"] for w in WORKERS}

    if "Put_Payroll_Input" in body:
        fault = """<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body><env:Fault><faultcode>env:Client</faultcode>
    <faultstring>Processing error occurred. Put_Payroll_Input is deprecated. Use Import_Payroll_Input (bulk, asynchronous) or Submit_Payroll_Input (single, synchronous).</faultstring>
  </env:Fault></env:Body>
</env:Envelope>"""
        return Response(fault, status=500, mimetype="text/xml")

    if "Import_Payroll_Input" in body or "Submit_Payroll_Input" in body:
        bulk = "Import_Payroll_Input" in body
        entries = re.findall(
            r'wd:type="Employee_ID">(\d+)<.*?<[\w]*:?Pay_Component>([^<]*)<'
            r".*?<[\w]*:?Amount>([\d.]+)<", body, re.S)
        loaded, errors = 0, []
        for emp, comp, amt in entries:
            if emp not in valid_ids:
                errors.append(f"'{emp}' is not a valid Employee_ID")
                continue
            PAYROLL_INPUTS.append({"Employee_ID": emp, "Pay_Component": comp,
                                   "Amount": amt})
            loaded += 1
        if not bulk and errors:        # Submit = synchronous, fail the call
            fault = f"""<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body><env:Fault><faultcode>env:Client</faultcode>
    <faultstring>Validation error occurred. Invalid ID value. {errors[0]}</faultstring>
  </env:Fault></env:Body>
</env:Envelope>"""
            return Response(fault, status=500, mimetype="text/xml")
        op = "Import_Payroll_Input" if bulk else "Submit_Payroll_Input"
        err_xml = "\n".join(f"      <wd:Error>{e}</wd:Error>" for e in errors)
        ok = f"""<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body>
    <wd:{op}_Response xmlns:wd="{WD_NS}">
      <wd:Request_Reference><wd:ID wd:type="WID">PAYROLL_INPUT_REQUEST-{len(PAYROLL_INPUTS)}</wd:ID></wd:Request_Reference>
      <wd:Loaded>{loaded}</wd:Loaded>
      <wd:Failed>{len(errors)}</wd:Failed>
{err_xml}
    </wd:{op}_Response>
  </env:Body>
</env:Envelope>"""
        return Response(ok, mimetype="text/xml")

    if "Get_Payroll_Results" in body:
        blocks = []
        for w in WORKERS:
            if w["Active"] != "1":
                continue
            periods = 26 if w["Pay_Group"] == "USA Biweekly" else 12
            gross = float(w["Base_Salary"]) / periods
            ben = sum(float(b["Employee_Cost"]) for b in w["Benefits"])
            extra = sum(float(p["Amount"]) for p in PAYROLL_INPUTS
                        if p["Employee_ID"] == w["Employee_ID"])
            net = gross + extra - ben
            blocks.append(f"""      <wd:Payroll_Result>
        <wd:Worker_Reference><wd:ID wd:type="Employee_ID">{w['Employee_ID']}</wd:ID></wd:Worker_Reference>
        <wd:Pay_Group>{w['Pay_Group']}</wd:Pay_Group>
        <wd:Gross_Amount>{gross:.2f}</wd:Gross_Amount>
        <wd:Additional_Earnings>{extra:.2f}</wd:Additional_Earnings>
        <wd:Benefit_Deductions>{ben:.2f}</wd:Benefit_Deductions>
        <wd:Net_Amount>{net:.2f}</wd:Net_Amount>
      </wd:Payroll_Result>""")
        xml = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
               "<env:Envelope xmlns:env=\"http://schemas.xmlsoap.org/soap/envelope/\">\n"
               "  <env:Body>\n"
               f"    <wd:Get_Payroll_Results_Response xmlns:wd=\"{WD_NS}\">\n"
               "      <wd:Response_Data>\n" + "\n".join(blocks) +
               "\n      </wd:Response_Data>\n"
               "    </wd:Get_Payroll_Results_Response>\n"
               "  </env:Body>\n</env:Envelope>")
        return Response(xml, mimetype="text/xml")

    fault = """<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body><env:Fault><faultcode>env:Client</faultcode>
    <faultstring>Validation error occurred. Supported: Import_Payroll_Input, Submit_Payroll_Input, Get_Payroll_Results.</faultstring>
  </env:Fault></env:Body>
</env:Envelope>"""
    return Response(fault, status=500, mimetype="text/xml")


UNSTABLE_CALLS = {"n": 0}


@app.route("/ccx/service/SUPER_TENANT/Unstable_Service/v1.0", methods=["POST"])
def unstable_service():
    """Fails twice, succeeds on every 3rd call - for practicing retry patterns."""
    UNSTABLE_CALLS["n"] += 1
    if UNSTABLE_CALLS["n"] % 3 != 0:
        fault = """<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body>
    <env:Fault>
      <faultcode>env:Server</faultcode>
      <faultstring>The service is temporarily unavailable. Please retry.</faultstring>
    </env:Fault>
  </env:Body>
</env:Envelope>"""
        return Response(fault, status=503, mimetype="text/xml")
    ok = f"""<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body>
    <wd:Unstable_Service_Response xmlns:wd="{WD_NS}">
      <wd:Status>SUCCESS after {UNSTABLE_CALLS['n']} total call(s)</wd:Status>
    </wd:Unstable_Service_Response>
  </env:Body>
</env:Envelope>"""
    return Response(ok, mimetype="text/xml")


@app.route("/")
def index():
    return Response(
        "Mock Workday tenant is running.\n"
        "SOAP : POST /ccx/service/SUPER_TENANT/Human_Resources/v42.0\n"
        "RaaS : GET  /ccx/service/customreport2/SUPER_TENANT/ISU_Demo/Worker_Report?format=xml|json\n",
        mimetype="text/plain")


if __name__ == "__main__":
    print("Mock Workday tenant -> http://127.0.0.1:8443")
    app.run(host="0.0.0.0", port=8443)
