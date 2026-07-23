# -*- coding: utf-8 -*-
"""
sup_org.py  --  Create Supervisory Organization: Extend screen -> synchronous
                orchestration -> Human_Resources SOAP web service.

Replicates the design:
  Custom Extend screen collects Sup Org details -> Submit -> a SYNCHRONOUS
  orchestration (CreateSupOrg, in orchestrate.py) which:
    1. receives input from the Extend screen
    2. validates required fields
    3. checks if the Sup Org code already exists  (GET .../exists)
    4. builds the SOAP Add_Update_Organization payload (Create Text Template)
    5. calls the Human_Resources web service           (POST .../human_resources)
    6. Add_Update_Organization
    7. captures Organization_Reference from the response
    8. returns success/error to the Extend screen (shown immediately)

This module provides the tenant side that the orchestration calls:
  - GET  /tenant/soap/human_resources/exists?code=...   (existence check)
  - POST /tenant/soap/human_resources                   (Add_Update_Organization)
  - the Extend screen + a "View Supervisory Organizations" list

INSTALL
-------
1. Drop next to workday_ui.py / orchestrate.py.
2. In workday_ui.py main block add:  import sup_org   # noqa: F401
3. Restart, Ctrl+F5. Open:  http://localhost:8443/extend/screen/create-sup-org
"""

import os
import re
import json
import hashlib
import datetime

from flask import request, Response

import workday_ui as wd
app = wd.app

STORE = "sup_org_store.json"

_NEW_TASKS = [
    {"name": "Create Supervisory Organization", "url": "/extend/screen/create-sup-org"},
    {"name": "View Supervisory Organizations", "url": "/tenant/sup-orgs"},
]
try:
    have = {t["url"] for t in wd.TASKS}
    for t in _NEW_TASKS:
        if t["url"] not in have:
            wd.TASKS.append(t)
except Exception:
    pass


def load():
    if not os.path.exists(STORE):
        save({"orgs": {}})
    try:
        with open(STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"orgs": {}}


def save(d):
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)


def esc(t):
    return (str(t) if t is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def wid(code):
    h = hashlib.sha1(code.encode("utf-8")).hexdigest()[:16].upper()
    return "SUPORG_WID_" + h


def _soap_val(xml, tag):
    m = re.search(r"<wd:%s>(.*?)</wd:%s>" % (tag, tag), xml or "", re.S)
    return (m.group(1).strip() if m else "")


# ===========================================================================
# Human_Resources web service (mock)
# ===========================================================================
@app.route("/tenant/soap/human_resources/exists")
def hr_exists():
    code = (request.args.get("code") or "").strip()
    d = load()
    return Response(json.dumps({"code": code, "exists": code in d["orgs"]}),
                    mimetype="application/json")


@app.route("/tenant/soap/human_resources", methods=["POST"])
def hr_add_update_organization():
    """Add_Update_Organization. Accepts the SOAP XML body (or JSON), validates,
    de-dupes by Organization_Code, persists, returns the Organization_Reference."""
    raw = request.get_data(as_text=True) or ""
    if raw.strip()[:1] == "{":
        try:
            data = json.loads(raw)
            code = data.get("Organization_Code", "")
            name = data.get("Organization_Name", "")
            manager = data.get("Manager_Reference", "")
            subtype = data.get("Organization_Subtype_Reference", "")
            superior = data.get("Superior_Organization_Reference", "")
            staffing = data.get("Staffing_Model", "")
            location = data.get("Location_Reference", "")
        except Exception:
            code = name = manager = subtype = superior = staffing = location = ""
    else:
        code = _soap_val(raw, "Organization_Code")
        name = _soap_val(raw, "Organization_Name")
        manager = _soap_val(raw, "Manager_Reference")
        subtype = _soap_val(raw, "Organization_Subtype_Reference")
        superior = _soap_val(raw, "Superior_Organization_Reference")
        staffing = _soap_val(raw, "Staffing_Model")
        location = _soap_val(raw, "Location_Reference")

    def out(payload, status=200):
        return Response(json.dumps(payload), status=status, mimetype="application/json")

    # 2. validate required fields
    if not code or not name:
        return out({"status": "error", "Organization_Reference": None,
                    "message": "Validation error: Organization Code and Name are required."}, 400)

    d = load()
    # 3. de-dupe
    if code in d["orgs"]:
        return out({"status": "error", "Organization_Reference": d["orgs"][code]["wid"],
                    "Organization_Code": code,
                    "message": "Sup Org code '%s' already exists." % code}, 409)

    ref = wid(code)
    d["orgs"][code] = {
        "code": code, "name": name, "wid": ref, "manager": manager,
        "subtype": subtype, "superior": superior, "staffing": staffing,
        "location": location, "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    save(d)

    soap_response = (
        '<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/" xmlns:wd="urn:com.workday/bsvc">'
        '<env:Body><wd:Add_Update_Organization_Response>'
        '<wd:Organization_Reference><wd:ID wd:type="WID">%s</wd:ID>'
        '<wd:ID wd:type="Organization_Reference_ID">%s</wd:ID></wd:Organization_Reference>'
        '</wd:Add_Update_Organization_Response></env:Body></env:Envelope>' % (ref, esc(code)))
    msg = "Supervisory Organization '%s' (%s) created." % (name, code)
    if manager:
        msg += " Manager assigned: %s." % manager
    return out({"status": "success", "Organization_Reference": ref,
                "Organization_Code": code, "Organization_Name": name,
                "manager": manager, "message": msg, "soapResponse": soap_response})


# ===========================================================================
# Extend custom screen: Create Supervisory Organization
# ===========================================================================
FIELDS = [
    ("SupOrgName", "Sup Org Name", "Finance Operations Team", "text"),
    ("SupOrgCode", "Sup Org Code / Reference ID", "FIN_OPS_1001", "text"),
    ("EffectiveDate", "Effective Date", "07/01/2026", "text"),
    ("AvailabilityDate", "Availability Date", "07/01/2026", "text"),
    ("SuperiorOrg", "Superior Organization", "FINANCE_PARENT_ORG", "text"),
    ("OrgSubtype", "Organization Subtype", "Department", "text"),
    ("StaffingModel", "Staffing Model", "", "staffing"),
    ("PrimaryLocation", "Primary Location", "USA_DALLAS", "text"),
    ("Manager", "Manager / Leader", "John Smith", "text"),
    ("Comments", "Comments", "", "textarea"),
]


@app.route("/extend/screen/create-sup-org", methods=["GET", "POST"])
def create_sup_org_screen():
    if request.method == "POST":
        inputs = {k: (request.form.get(k, "") or "").strip() for k, _, _, _ in FIELDS}
        import orchestrate
        store = orchestrate.load()
        orch = None
        for a in store.get("apps", {}).values():
            if a.get("appId") == "7a1c0e9b2d4f46a8b3c5d7e9f1a2b3c4":
                orch = a["orchestrations"].get("CreateSupOrg")
                break
        if not orch:
            return wd.html_resp(wd.layout("Create Supervisory Organization", "",
                "<div class='card'>CreateSupOrg orchestration not found. Delete orchestrate_store.json and restart.</div>",
                banner=False))

        res = orchestrate.run_orchestration(orch, "Extend Submit", inputs=inputs)
        ctx = res.get("context", {})
        result = (ctx.get("Result") or {})
        call = (ctx.get("CallHumanResources") or {}).get("response", {})
        status = result.get("status") or call.get("status") or res.get("status")
        org_ref = result.get("orgRef") or call.get("Organization_Reference")
        message = result.get("message") or call.get("message", "")
        soap_req = (ctx.get("BuildSoapPayload") or {}).get("message", "")
        soap_resp = call.get("soapResponse", "")

        ok = (status == "success") and bool(org_ref)
        banner_color = "#e8f5e9" if ok else "#fdecea"
        banner_border = "#b6dcb9" if ok else "#f3b9b3"
        head = ("&#10003; Success" if ok else "&#9888; Error")
        ref_html = ("<div style='margin-top:8px'>Organization_Reference: <b>%s</b></div>" % esc(org_ref)) if org_ref else ""

        steprows = ""
        for e in res.get("trace", []):
            badge = "#2f9e44" if e.get("status") == "Completed" else (
                "#e5484d" if e.get("status") == "Error" else "#888")
            steprows += ("<tr><td>%s</td><td><span style='background:%s;color:#fff;padding:2px 8px;"
                         "border-radius:4px;font-size:11px'>%s</span></td><td>%s</td></tr>" % (
                             esc(e.get("step", "")), badge, esc(e.get("status", "")), esc(e.get("message", ""))))

        body = """
        <div class="card">
          <div style="background:%s;border:1px solid %s;border-radius:8px;padding:14px 18px;margin-bottom:18px">
            <div style="font-size:16px;font-weight:700">%s</div>
            <div style="margin-top:4px">%s</div>%s
          </div>
          <h3>Orchestration trace (synchronous)</h3>
          <div class="wd-grid"><table>
            <tr><th>Step</th><th>Status</th><th>Message</th></tr>%s
          </table></div>
          <details style="margin-top:16px"><summary style="cursor:pointer;font-weight:600">SOAP request (Add_Update_Organization)</summary>
            <pre style="background:#0f1623;color:#cdd9f5;padding:14px;border-radius:8px;overflow:auto;font-size:12px">%s</pre></details>
          <details style="margin-top:10px"><summary style="cursor:pointer;font-weight:600">SOAP response</summary>
            <pre style="background:#0f1623;color:#cdd9f5;padding:14px;border-radius:8px;overflow:auto;font-size:12px">%s</pre></details>
          <div style="margin-top:18px;display:flex;gap:10px">
            <a class="btn" href="/extend/screen/create-sup-org">Create another</a>
            <a class="btn" href="/tenant/sup-orgs">View Supervisory Organizations &#8594;</a>
          </div>
        </div>""" % (banner_color, banner_border, head, esc(message), ref_html, steprows,
                     esc(soap_req), esc(soap_resp))
        return wd.html_resp(wd.layout("Create Supervisory Organization", "Result", body, banner=False))

    # GET -> the form
    rows = ""
    for key, label, ph, kind in FIELDS:
        rows += "<label style='display:block;font-weight:600;margin:14px 0 6px'>%s</label>" % esc(label)
        if kind == "textarea":
            rows += ("<textarea name='%s' placeholder='%s' style='width:100%%;padding:10px;"
                     "border:1px solid #c4ccd6;border-radius:8px;min-height:70px'></textarea>" % (key, esc(ph)))
        elif kind == "staffing":
            rows += ("<select name='%s' style='width:100%%;padding:10px;border:1px solid #c4ccd6;border-radius:8px'>"
                     "<option>Job Management</option><option>Position Management</option></select>" % key)
        else:
            rows += ("<input name='%s' value='%s' style='width:100%%;padding:10px;"
                     "border:1px solid #c4ccd6;border-radius:8px'>" % (key, esc(ph)))
    body = """
    <div class="card" style="max-width:620px">
      <h2 style="margin-bottom:6px">Create Supervisory Organization</h2>
      <p style="color:#666;font-size:13px;margin-bottom:8px">Submitting runs the synchronous
        <b>CreateSupOrg</b> orchestration, which calls the Human_Resources
        <b>Add_Update_Organization</b> web service and returns the result immediately.</p>
      <form method="POST">%s
        <div style="margin-top:22px"><button class="btn pri" type="submit">Submit</button></div>
      </form>
    </div>""" % rows
    return wd.html_resp(wd.layout("Create Supervisory Organization", "Workday Extend", body, banner=False))


# ===========================================================================
# View Supervisory Organizations
# ===========================================================================
@app.route("/tenant/sup-orgs")
def view_sup_orgs():
    d = load()
    rows = ""
    for o in d["orgs"].values():
        rows += ("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            esc(o["code"]), esc(o["name"]), esc(o["wid"]), esc(o.get("manager", "")),
            esc(o.get("superior", "")), esc(o.get("created", ""))))
    if not rows:
        rows = ("<tr><td colspan='6' style='padding:30px;text-align:center;color:#888'>No Sup Orgs yet. "
                "<a href='/extend/screen/create-sup-org'>Create one</a>.</td></tr>")
    body = """
    <div class="card">
      <h2>Supervisory Organizations <span style="color:#888;font-weight:400">%d</span></h2>
      <div class="wd-grid"><table>
        <tr><th>Code</th><th>Name</th><th>Organization_Reference</th><th>Manager</th><th>Superior</th><th>Created</th></tr>
        %s
      </table></div>
      <a class="btn pri" style="margin-top:16px" href="/extend/screen/create-sup-org">+ Create Supervisory Organization</a>
    </div>""" % (len(d["orgs"]), rows)
    return wd.html_resp(wd.layout("Supervisory Organizations", "Worker / Organization", body, banner=False))
