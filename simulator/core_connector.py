"""
core_connector.py - Core Connector: Worker (CCW) simulation.

Mirrors the real tenant flow:
  Create Integration System (template: Core Connector: Worker)
    -> Configure Integration Services      (enable/disable section services)
    -> Configure Integration Attributes    (Version, Output Format, filename,
                                            Include Inactive Workers)
    -> Configure Integration Field Attributes (Include in Output per field)
    -> Launch Integration                  (Full File OR Changes Only)

Changes Only works like real CCW change detection: each run snapshots the
output rows; the next "Changes Only" run emits only new/changed workers.
"""

import hashlib
import json
import os
import re
from datetime import datetime

from flask import request, Response, redirect

import mock_workday_server as mws
from mock_workday_server import app
from workday_ui import layout, html_resp, persist, TENANT

SYS_FILE = "integration_systems.json"
OUT_DIR = "cc_output"

TEMPLATE = "Core Connector: Worker"
TPL_CCW = "Core Connector: Worker"
TPL_CCB = "Cloud Connect: Benefits"
TPL_DT = "Document Transformation"
TEMPLATES = [TPL_CCW, TPL_CCB, TPL_DT]

CCB_SERVICES = [
    "Benefits Connector ESB Service*",
    "Cloud Connect: Subscriber Data Section Fields",
    "Cloud Connect: Enrollment Data Section Fields",
    "Core Connector: Integration Maps - Benefits",
]
CCB_SECTIONS = {
    "Cloud Connect: Subscriber Data Section Fields":
        ["First_Name", "Last_Name"],
    "Cloud Connect: Enrollment Data Section Fields":
        ["Plan", "Coverage", "Employee_Cost"],
}
DEFAULT_DT_XSLT = open("dt_generic_csv.xsl").read() \
    if os.path.exists("dt_generic_csv.xsl") else ""


def tpl_of(sys):
    return sys.get("template", TPL_CCW)


def sections_for(sys):
    return CCB_SECTIONS if tpl_of(sys) == TPL_CCB else SECTIONS


SERVICES = [
    "Core Connector: Worker ESB Service*",
    "Core Connector: Date Launch Parameters",
    "Core Connector: Integration Maps - Worker",
    "Core Connector: Worker Integration Configuration",
    "Worker Personal Data Section Fields",
    "Worker Status Data Section Fields",
    "Worker Position Data Section Fields",
    "Worker Compensation Data Section Fields",
]

# Section service -> fields it can emit (Employee_ID is always the reference)
SECTIONS = {
    "Worker Personal Data Section Fields": ["First_Name", "Last_Name", "Email"],
    "Worker Status Data Section Fields": ["Active", "Hire_Date"],
    "Worker Position Data Section Fields": ["Org"],
    "Worker Compensation Data Section Fields": ["Bonus_Count", "Bonus_Total"],
}

DEFAULT_ATTRS = {"Version": "40.0", "Output_Filename": "",
                 "Output_Format": "XML", "Include_Inactive_Workers": False}

SNAPSHOTS = {}        # system_name -> {Employee_ID: row_hash}  (change detection)
CC_EVENTS = []        # process monitor


def load_systems():
    if os.path.exists(SYS_FILE):
        with open(SYS_FILE) as f:
            return {s["system_name"]: s for s in json.load(f)}
    return {}


SYSTEMS = load_systems()


def save_systems():
    persist(SYS_FILE, list(SYSTEMS.values()))


# ---------------------------------------------------------------------------
# Field-level security domains (real Workday secures worker data by domain).
# The launch needs Get on every domain whose data it actually emits.
# ---------------------------------------------------------------------------
BASE_DOMAIN = "Worker Data: Public Worker Reports"        # Employee_ID / key

SECTION_DOMAINS = {
    "Worker Personal Data Section Fields":     "Worker Data: Personal Information",
    "Worker Status Data Section Fields":       "Worker Data: Current Staffing Information",
    "Worker Position Data Section Fields":     "Worker Data: Organization Information",
    "Worker Compensation Data Section Fields": "Worker Data: Compensation by Organization",
}
# Field-level override: a field can need a tighter domain than its section.
FIELD_DOMAINS = {
    "Email": "Worker Data: Contact Information",
}
# Descriptions so these show up grantable in Maintain Domain Permissions.
WORKER_FIELD_DOMAINS = {
    BASE_DOMAIN: "Worker key/ID (Employee_ID) - needs Get",
    "Worker Data: Personal Information": "Name fields (First/Last Name) - needs Get",
    "Worker Data: Contact Information": "Email / phone - needs Get",
    "Worker Data: Current Staffing Information": "Active status, Hire Date - needs Get",
    "Worker Data: Organization Information": "Org / Position - needs Get",
    "Worker Data: Compensation by Organization": "Bonus / Compensation - needs Get",
}


def required_domains(sys):
    """Get domains this launch needs, computed from the data it will actually
    emit (section service ON + field ticked) - faithful to real Workday."""
    req = {BASE_DOMAIN}                       # Employee_ID is always emitted
    for sec, fields in SECTIONS.items():
        if not sys.get("services", {}).get(sec):
            continue
        for f in fields:
            if not sys.get("fields", {}).get(sec, {}).get(f):
                continue
            req.add(FIELD_DOMAINS.get(f, SECTION_DOMAINS.get(sec, BASE_DOMAIN)))
    return sorted(req)


def _enforce_on():
    """True if Require ISU authentication is switched on in security."""
    try:
        import security as _sec
        return bool(_sec.SEC.get("enforce"))
    except Exception:
        return False


def _isu_has_get(isu, domain):
    """Mirror security_gate: does any ISSG the ISU belongs to have ACTIVE
    Get access to this domain?"""
    try:
        import security as _sec
        for g in _sec.SEC.get("issgs", {}).values():
            if (isu in g.get("members", [])
                    and "Get" in g.get("active", {}).get(domain, [])):
                return True
    except Exception:
        pass
    return False


def enforcement_block(sys):
    """Return an error-banner HTML string if the launch must be BLOCKED by ISU
    domain security, else '' (allowed). Faithful to real Workday: enforcement
    only bites when Require ISU authentication is ON."""
    if not _enforce_on():
        return ""
    acct = sys.get("workday_account", "")
    if not acct:
        return ('<div class="err-banner"><b>Launch blocked.</b> Security '
                'enforcement (Require ISU authentication) is ON, but this '
                'integration has no <b>Workday Account</b>. Set one under '
                '<b>Edit Account</b> so it runs as an ISU.</div>')
    missing = [d for d in required_domains(sys) if not _isu_has_get(acct, d)]
    if missing:
        return ('<div class="err-banner"><b>Launch blocked - task not '
                'authorized.</b><br>ISU <b>%s</b> lacks <b>Get</b> access to: '
                '<b>%s</b>.<br><span style="font-size:12px;color:#555">Grant '
                'these in Maintain Domain Permissions for the ISU\'s security '
                'group, then run Activate Pending Security Policy Changes.'
                '</span></div>') % (acct, ", ".join(missing))
    return ""


def field_value(worker, field):
    if field == "Bonus_Count":
        return str(len(worker.get("Payments", [])))
    if field == "Bonus_Total":
        return str(sum(float(p["Amount"]) for p in worker.get("Payments", [])))
    return str(worker.get(field, ""))


# ---------------------------------------------------------------------------
# Create Integration System
# ---------------------------------------------------------------------------
@app.route("/task/create-integration-system", methods=["GET", "POST"])
def create_integration_system():
    msg = ""
    if request.method == "POST":
        name = request.form.get("system_name", "").strip()
        if not name:
            msg = '<div class="err-banner">Validation error occurred. System Name is required.</div>'
        elif name in SYSTEMS:
            msg = f'<div class="err-banner">Validation error occurred. Integration System \'{name}\' already exists.</div>'
        else:
            tpl = request.form.get("template", TPL_CCW)
            if tpl == TPL_DT:
                SYSTEMS[name] = {"system_name": name, "template": TPL_DT,
                                 "dt": {"source_system": "",
                                        "xslt": DEFAULT_DT_XSLT,
                                        "output_filename": ""}}
            else:
                svcs = CCB_SERVICES if tpl == TPL_CCB else SERVICES
                secs = CCB_SECTIONS if tpl == TPL_CCB else SECTIONS
                SYSTEMS[name] = {
                    "system_name": name,
                    "template": tpl,
                    "services": {s: True for s in svcs},
                    "attributes": dict(DEFAULT_ATTRS),
                    "fields": {sec: {f: True for f in flds}
                               for sec, flds in secs.items()},
                    "maps": {},
                    "workday_account": "",   # ISU this integration runs as
                }
            save_systems()
            return redirect(f"/task/view-integration-system?name={name}")

    body = f"""{msg}
<form method="post"><div class="card">
  <label>System Name <span class="req">*</span></label>
  <input type="text" name="system_name" placeholder="INT001 CCW Outbound">
  <label>New using Template <span class="req">*</span></label>
  <select name="template">{''.join(f'<option>{t}</option>' for t in TEMPLATES)}</select>
  <p style="font-size:12px;color:#888;margin-top:8px">The template pre-loads
  the integration services, attributes, and field sections you then configure.</p>
  <div class="btnrow">
    <button class="btn btn-ok" type="submit">OK</button>
    <a class="btn btn-cancel" href="/home">Cancel</a>
  </div>
</div></form>"""
    return html_resp(layout("Create Integration System",
                            "Template-based integration (no Studio required)",
                            body))


# ---------------------------------------------------------------------------
# View Integration System (hub page, like the related-actions menu)
# ---------------------------------------------------------------------------
@app.route("/task/view-integration-system")
def view_integration_system():
    name = request.args.get("name")
    if not name:
        rows = "".join(
            f'<tr><td><a href="/task/view-integration-system?name={s}">{s}</a></td>'
            f'<td>{d["template"]}</td></tr>' for s, d in SYSTEMS.items()) or \
            '<tr><td colspan="2">No integration systems yet. ' \
            '<a href="/task/create-integration-system">Create one</a>.</td></tr>'
        body = f"""<div class="card"><h2>Integration Systems</h2>
<table><tr><th>System Name</th><th>Template</th></tr>{rows}</table></div>"""
        return html_resp(layout("View Integration System", "All systems", body))

    sys = SYSTEMS.get(name)
    if not sys:
        return html_resp(layout("View Integration System", "",
                                '<div class="err-banner">System not found.</div>'))
    if tpl_of(sys) == TPL_DT:
        dt = sys["dt"]
        body = f"""
<div class="card"><h2>Actions</h2>
  <a class="btn btn-ok" href="/task/configure-document-transformation?sys={name}">Configure Document Transformation</a>
  <a class="btn btn-ok" href="/task/launch-integration?sys={name}" style="margin-left:8px">Launch Integration</a>
</div>
<div class="card"><h2>Document Transformation</h2>
<table><tr><th>Setting</th><th>Value</th></tr>
<tr><td>Source Integration System</td><td>{dt.get('source_system') or '(not set)'}</td></tr>
<tr><td>Output Filename</td><td>{dt.get('output_filename') or '(sequence generator)'}</td></tr>
<tr><td>XSLT</td><td>{len(dt.get('xslt',''))} bytes attached</td></tr></table>
<p style="font-size:12px;color:#888;margin-top:8px">A DT system has no data
services of its own: it consumes the XML output of its source connector and
applies the attached XSLT - the standard Core Connector -> DT chain.</p></div>"""
        return html_resp(layout("View Integration System",
                                f"{name} - Template: {TPL_DT}", body))
    svc_rows = "".join(
        f'<tr><td>{tpl_of(sys)} / {s}</td>'
        f'<td>{"Yes" if on else "No"}</td></tr>'
        for s, on in sys["services"].items())
    attrs = "".join(f"<tr><td>{k.replace('_', ' ')}</td><td>{v}</td></tr>"
                    for k, v in sys["attributes"].items())
    body = f"""
<div class="card"><h2>Actions (related actions menu)</h2>
  <a class="btn btn-ok" href="/task/configure-integration-services?sys={name}">Configure Integration Services</a>
  <a class="btn btn-ok" href="/task/configure-integration-attributes?sys={name}" style="margin-left:8px">Configure Integration Attributes</a>
  <a class="btn btn-ok" href="/task/configure-field-attributes?sys={name}" style="margin-left:8px">Configure Integration Field Attributes</a>
  <a class="btn btn-ok" href="/task/configure-integration-maps?sys={name}" style="margin-left:8px">Configure Integration Maps</a>
  <a class="btn btn-ok" href="/task/edit-integration-account?sys={name}" style="margin-left:8px">Edit Account (Workday Account / ISU)</a>
  <a class="btn btn-ok" href="/task/maintain-test-workers?sys={name}" style="margin-left:8px">Maintain Test Workers</a>
  <a class="btn btn-ok" href="/task/launch-integration?sys={name}" style="margin-left:8px">Launch Integration</a>
</div>
<div class="card"><h2>Workday Account</h2>
<table><tr><th>Setting</th><th>Value</th></tr>
<tr><td>Workday Account (ISU)</td><td>{sys.get('workday_account') or '(not set - runs as the default user)'}</td></tr>
<tr><td>Requires Get on domains</td><td>{', '.join(required_domains(sys))}</td></tr></table>
<p style="font-size:12px;color:#888;margin-top:8px">The integration runs as this
Integration System User. Set it under <b>Edit Account</b>. If security
enforcement is on, this ISU's ISSG must have Get access to the domains above.</p></div>
<div class="card"><h2>Integration Services</h2>
<table><tr><th>Integration Template Service</th><th>Enabled</th></tr>{svc_rows}</table></div>
<div class="card"><h2>Integration Attributes</h2>
<table><tr><th>Attribute</th><th>Value</th></tr>{attrs}</table></div>"""
    return html_resp(layout(f"View Integration System",
                            f"{name} - Template: {tpl_of(sys)}", body))


# ---------------------------------------------------------------------------
# Edit Account for Integration System  (assign the Workday Account / ISU)
# ---------------------------------------------------------------------------
@app.route("/task/edit-integration-account", methods=["GET", "POST"])
def edit_integration_account():
    """Assign a Workday Account (ISU) to the integration system.
    The ISU list is dynamic: it is whatever you created in security.py
    (Create Integration System User). Nothing is hard-coded."""
    import security as _sec          # lazy: avoids import-order issues
    name = request.values.get("sys")
    sys = SYSTEMS.get(name)
    if not sys:
        return redirect("/task/view-integration-system")

    isus = list(_sec.SEC.get("isus", {}).keys())
    msg = ""
    if request.method == "POST":
        acct = request.form.get("workday_account", "").strip()
        sys["workday_account"] = acct
        save_systems()
        msg = (f'<div class="ok-banner">Workday Account set to '
               f'<b>{acct or "(none - default user)"}</b>. The integration '
               f'will run as this account.</div>')

    cur = sys.get("workday_account", "")
    if isus:
        opts = '<option value="">(none - run as the default user)</option>'
        opts += "".join(
            f'<option value="{u}"{" selected" if u == cur else ""}>{u}</option>'
            for u in isus)
        control = f'<select name="workday_account">{opts}</select>'
        hint = ("Pick the Integration System User this integration runs as. "
                "ISUs come from Create Integration System User in security.")
    else:
        control = ('<span style="color:#a00">No ISUs exist yet. '
                   '<a href="/task/create-isu">Create an Integration System '
                   'User</a> first, then come back.</span>')
        hint = ""

    body = f"""{msg}
<form method="post"><input type="hidden" name="sys" value="{name}">
<div class="card"><h2>Edit Account for Integration System - {name}</h2>
  <p style="font-size:13px;color:#666;margin-bottom:12px">{hint}</p>
  <label>Workday Account</label><br>
  {control}
  <div class="btnrow" style="margin-top:14px">
    <button class="btn btn-ok">OK</button>
    <a class="btn btn-cancel" href="/task/view-integration-system?name={name}">Cancel</a>
  </div>
</div></form>"""
    return html_resp(layout("Edit Account for Integration System", name, body))


# ---------------------------------------------------------------------------
# Configure Integration Services
# ---------------------------------------------------------------------------
@app.route("/task/configure-integration-services", methods=["GET", "POST"])
def configure_services():
    name = request.values.get("sys")
    sys = SYSTEMS.get(name)
    if not sys:
        return redirect("/task/view-integration-system")
    if tpl_of(sys) == TPL_DT:
        return redirect(f"/task/configure-document-transformation?sys={name}")
    msg = ""
    if request.method == "POST":
        on = set(request.form.getlist("svc"))
        for s in sys["services"]:
            if s.endswith("*"):
                sys["services"][s] = True        # initial service is mandatory
            else:
                sys["services"][s] = s in on
        save_systems()
        msg = '<div class="ok-banner">Integration services updated.</div>'

    checks = "".join(
        f'<tr><td>{tpl_of(sys)} / {s}</td>'
        f'<td><input type="checkbox" name="svc" value="{s}" '
        f'{"checked" if on else ""} {"disabled" if s.endswith("*") else ""}></td>'
        f'<td>{"Initial Service to Invoke" if s.endswith("*") else ""}</td></tr>'
        for s, on in sys["services"].items())
    body = f"""{msg}
<form method="post"><input type="hidden" name="sys" value="{name}">
<div class="card"><h2>Integration Template: {tpl_of(sys)}</h2>
<table><tr><th>Integration Template Service</th><th>Enabled</th><th></th></tr>
{checks}</table>
<p style="font-size:12px;color:#888;margin-top:10px">Disabling a Section
Fields service removes that whole section from the output, regardless of the
field attribute configuration.</p>
<div class="btnrow"><button class="btn btn-ok">OK</button>
<a class="btn btn-cancel" href="/task/view-integration-system?name={name}">Cancel</a></div>
</div></form>"""
    return html_resp(layout("Configure Integration Services", name, body))


# ---------------------------------------------------------------------------
# Configure Integration Attributes
# ---------------------------------------------------------------------------
@app.route("/task/configure-integration-attributes", methods=["GET", "POST"])
def configure_attributes():
    name = request.values.get("sys")
    sys = SYSTEMS.get(name)
    if not sys:
        return redirect("/task/view-integration-system")
    if tpl_of(sys) == TPL_DT:
        return redirect(f"/task/configure-document-transformation?sys={name}")
    msg = ""
    if request.method == "POST":
        a = sys["attributes"]
        a["Version"] = request.form.get("version", "40.0")
        a["Output_Filename"] = request.form.get("filename", "").strip()
        a["Output_Format"] = request.form.get("format", "XML")
        a["Include_Inactive_Workers"] = request.form.get("inactive") == "on"
        save_systems()
        msg = '<div class="ok-banner">Integration attributes updated.</div>'

    a = sys["attributes"]
    body = f"""{msg}
<form method="post"><input type="hidden" name="sys" value="{name}">
<div class="card"><h2>Integration Template: {tpl_of(sys)}</h2>
  <label>Version <span style="font-weight:400;color:#888">(Required for Launch -
    controls the version of the output file)</span></label>
  <select name="version">
    <option {"selected" if a["Version"] == "40.0" else ""}>40.0</option>
    <option {"selected" if a["Version"] == "39.0" else ""}>39.0</option>
    <option {"selected" if a["Version"] == "38.0" else ""}>38.0</option>
  </select>
  <label>Output Filename <span style="font-weight:400;color:#888">(leave empty
    to use the filename sequence generator)</span></label>
  <input type="text" name="filename" value="{a['Output_Filename']}"
         placeholder="ccw_workers.xml">
  <label>Output Format</label>
  <select name="format">
    <option {"selected" if a["Output_Format"] == "XML" else ""}>XML</option>
    <option {"selected" if a["Output_Format"] == "CSV" else ""}>CSV</option>
  </select>
  <label><input type="checkbox" name="inactive"
    {"checked" if a["Include_Inactive_Workers"] else ""}>
    Include Inactive Workers in Full File</label>
  <div class="btnrow"><button class="btn btn-ok">OK</button>
  <a class="btn btn-cancel" href="/task/view-integration-system?name={name}">Cancel</a></div>
</div></form>"""
    return html_resp(layout("Configure Integration Attributes", name, body))


# ---------------------------------------------------------------------------
# Configure Integration Field Attributes
# ---------------------------------------------------------------------------
@app.route("/task/configure-field-attributes", methods=["GET", "POST"])
def configure_field_attributes():
    name = request.values.get("sys")
    sys = SYSTEMS.get(name)
    if not sys:
        return redirect("/task/view-integration-system")
    if tpl_of(sys) == TPL_DT:
        return redirect(f"/task/configure-document-transformation?sys={name}")
    msg = ""
    if request.method == "POST":
        on = set(request.form.getlist("field"))
        for sec, flds in sys["fields"].items():
            for f in flds:
                flds[f] = f"{sec}|{f}" in on
        save_systems()
        msg = '<div class="ok-banner">Field attributes updated.</div>'

    sections = ""
    for sec, flds in sys["fields"].items():
        rows = "".join(
            f'<tr><td>{f.replace("_", " ")}</td>'
            f'<td><input type="checkbox" name="field" value="{sec}|{f}" '
            f'{"checked" if on else ""}></td></tr>'
            for f, on in flds.items())
        sections += f"""<div class="card"><h2>{sec}</h2>
<table><tr><th>Field(s)</th><th>Include in Output</th></tr>{rows}</table></div>"""

    body = f"""{msg}
<form method="post"><input type="hidden" name="sys" value="{name}">
<p style="font-size:13px;color:#666;margin-bottom:14px">Fields with a tick in
the "Include in Output" column will be included in the output file.
Employee ID is always emitted as the Worker Reference.</p>
{sections}
<div class="btnrow"><button class="btn btn-ok">OK</button>
<a class="btn btn-cancel" href="/task/view-integration-system?name={name}">Cancel</a></div>
</form>"""
    return html_resp(layout("Configure Integration Field Attributes", name, body))


# ---------------------------------------------------------------------------
# Launch Integration (Full File / Changes Only)
# ---------------------------------------------------------------------------
def _apply_map(maps, f, v):
    m = maps.get(f)
    if m:
        return m["entries"].get(v, m.get("default", v))
    return v


def build_rows(sys, only_workers=None, only_orgs=None):
    """Apply attributes + services + field config + integration maps.
    only_workers / only_orgs come from the Schedule an Integration launch
    parameters (Workers, Restrict Results By Orgs)."""
    include_inactive = sys["attributes"]["Include_Inactive_Workers"]
    maps = sys.get("maps", {})
    field_maps = sys.get("field_maps", {})   # internal field -> external name
    secs = sections_for(sys)
    rows = []

    if tpl_of(sys) == TPL_CCB:
        # Benefits carrier connector: one record per enrollment
        for w in mws.WORKERS:
            if only_workers and w["Employee_ID"] not in only_workers:
                continue
            if only_orgs and w.get("Org") not in only_orgs:
                continue
            if w["Active"] != "1" and not include_inactive:
                continue
            for b in w.get("Benefits", []):
                row = {"Employee_ID": w["Employee_ID"],
                       "_key": f"{w['Employee_ID']}|{b['Plan']}",
                       "_sections": {}}
                for sec, flds in secs.items():
                    if not sys["services"].get(sec):
                        continue
                    picked = {}
                    for f in flds:
                        if not sys["fields"][sec].get(f):
                            continue
                        raw = (str(b.get(f, "")) if f in b
                               else field_value(w, f))
                        out = field_maps.get(f, f)         # external field name
                        picked[out] = _apply_map(maps, f, raw)
                    if picked:
                        row["_sections"][sec] = picked
                rows.append(row)
        return rows

    for w in mws.WORKERS:
        if only_workers and w["Employee_ID"] not in only_workers:
            continue
        if only_orgs and w.get("Org") not in only_orgs:
            continue
        if w["Active"] != "1" and not include_inactive:
            continue
        row = {"Employee_ID": w["Employee_ID"],
               "_key": w["Employee_ID"], "_sections": {}}
        for sec, flds in secs.items():
            if not sys["services"].get(sec):
                continue
            picked = {}
            for f in flds:
                if not sys["fields"][sec].get(f):
                    continue
                out = field_maps.get(f, f)                 # external field name
                picked[out] = _apply_map(maps, f, field_value(w, f))
            if picked:
                row["_sections"][sec] = picked
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Configure Integration Maps (internal Workday field -> external field name)
# ---------------------------------------------------------------------------
@app.route("/task/configure-integration-maps", methods=["GET", "POST"])
def configure_integration_maps():
    name = request.values.get("sys") or next(iter(SYSTEMS), None)
    sys = SYSTEMS.get(name)
    if not sys:
        return redirect("/task/create-integration-system")
    sys.setdefault("maps", {})
    sys.setdefault("field_maps", {})
    msg = ""

    secs = sections_for(sys)
    # only fields actually enabled on an enabled service are worth mapping
    enabled_fields = []
    for sec, flds in secs.items():
        if not sys["services"].get(sec):
            continue
        for f in flds:
            if sys["fields"].get(sec, {}).get(f) and f not in enabled_fields:
                enabled_fields.append(f)
    if not enabled_fields:
        enabled_fields = [f for flds in secs.values() for f in flds]

    if request.method == "POST" and request.form.get("save") == "1":
        fm = {}
        for f in enabled_fields:
            ext = request.form.get("ext|" + f, "").strip()
            if ext and ext != f:
                fm[f] = ext
        sys["field_maps"] = fm
        save_systems()
        msg = (f'<div class="ok-banner">Field mapping saved: '
               f'<b>{len(fm)}</b> field(s) renamed. Launch the integration to '
               f'see the external field names in the output XML/CSV.</div>')

    fm = sys.get("field_maps", {})
    rows = "".join(
        f'<tr><td><b>{f}</b></td>'
        f'<td><span class="arrow">&#8594;</span></td>'
        f'<td><input type="text" name="ext|{f}" value="{fm.get(f, "")}" '
        f'placeholder="{f}" style="max-width:240px"></td></tr>'
        for f in enabled_fields)
    body = f"""{msg}
<form method="post">
  <input type="hidden" name="sys" value="{name}">
  <input type="hidden" name="save" value="1">
<div class="card"><h2>Integration Maps - {name}</h2>
  <p style="font-size:13px;color:#666;margin-bottom:12px">Map each
  <b>internal Workday field</b> to the <b>external field name</b> the partner
  expects (the XML tag / CSV header). This maps the <b>field</b>, not each value
  - e.g. <code>First_Name &rarr; First</code>. Leave blank to keep the internal
  name.</p>
  <table class="grid">
    <tr><th style="width:34%">Internal Field (Workday)</th><th style="width:6%"></th>
        <th>External Field Name</th></tr>
    {rows}
  </table>
  <div class="btnrow"><button class="btn btn-ok">OK</button>
  <a class="btn btn-cancel" href="/task/view-integration-system?name={name}">Cancel</a></div>
</div></form>
<style>.arrow{{color:#2E6DA4;font-weight:700;font-size:16px}}</style>"""
    return html_resp(layout("Configure Integration Maps", name, body))


def row_hash(row):
    return hashlib.md5(json.dumps(row, sort_keys=True).encode()).hexdigest()


def to_xml(rows, version, record_tag="Worker", root_tag="Workers"):
    parts = [f'<?xml version="1.0" encoding="UTF-8"?>',
             f'<wd:{root_tag} xmlns:wd="urn:com.workday/ccw" wd:version="{version}">']
    for r in rows:
        parts.append(f'  <wd:{record_tag}>\n    <wd:Worker_Reference>'
                     f'\n      <wd:ID wd:type="Employee_ID">{r["Employee_ID"]}</wd:ID>'
                     f'\n    </wd:Worker_Reference>')
        for sec, flds in r["_sections"].items():
            tag = re.sub(r"_+", "_",
                         re.sub(r"[^\w]", "_",
                                sec.replace(" Section Fields", ""))).strip("_")
            parts.append(f"    <wd:{tag}>")
            for f, v in flds.items():
                parts.append(f"      <wd:{f}>{v}</wd:{f}>")
            parts.append(f"    </wd:{tag}>")
        parts.append(f"  </wd:{record_tag}>")
    parts.append(f"</wd:{root_tag}>")
    return "\n".join(parts)


def to_csv(rows):
    cols = ["Employee_ID"]
    for sec, flds in SECTIONS.items():
        cols += [f for f in flds]
    seen = []
    for r in rows:
        flat = {"Employee_ID": r["Employee_ID"]}
        for sec in r["_sections"].values():
            flat.update(sec)
        seen.append(flat)
    used = [c for c in cols if any(c in s for s in seen)]
    out = [",".join(used)]
    out += [",".join(s.get(c, "") for c in used) for s in seen]
    return "\n".join(out)


@app.route("/task/launch-integration", methods=["GET", "POST"])
def launch_integration():
    name = request.values.get("sys") or next(iter(SYSTEMS), None)
    sys = SYSTEMS.get(name)
    if not sys:
        return redirect("/task/create-integration-system")

    msg = ""
    if request.method == "POST" and request.form.get("simulate") == "1":
        # Demo helper: mutate one worker in a field that is actually in the
        # output, so Changes Only (delta) can detect it.
        w = mws.WORKERS[4]
        enabled = [s for s in SECTIONS if sys["services"].get(s)]
        if not enabled:
            msg = ('<div class="err-banner">No data section is enabled, so there '
                   'are no field values to change (output would be Employee_ID '
                   'only). Enable a section in <a href="/task/configure-'
                   f'integration-services?sys={name}">Configure Integration '
                   'Services</a> first.</div>')
        else:
            if sys["services"].get("Worker Position Data Section Fields"):
                orgs = ["Finance", "HR Operations", "IT Services", "Audit", "Legal"]
                cur = w.get("Org") if w.get("Org") in orgs else orgs[0]
                w["Org"] = orgs[(orgs.index(cur) + 1) % len(orgs)]
                what = f'Org -&gt; <b>{w["Org"]}</b>'
            elif sys["services"].get("Worker Personal Data Section Fields"):
                w["Email"] = f'changed.{datetime.now().strftime("%H%M%S")}@example.com'
                what = f'Email -&gt; <b>{w["Email"]}</b>'
            elif sys["services"].get("Worker Compensation Data Section Fields"):
                w.setdefault("Payments", []).append({"Amount": "100"})
                what = "added a payment (Bonus_Count / Bonus_Total change)"
            else:   # Worker Status Data Section Fields
                w["Hire_Date"] = "2000-01-01"
                what = f'Hire_Date -&gt; <b>{w["Hire_Date"]}</b>'
            msg = (f'<div class="ok-banner">Simulated change on worker '
                   f'<b>{w["Employee_ID"]}</b>: {what}.<br><b>Now uncheck Full '
                   f'File and click OK</b> to get the delta (just this worker). '
                   f'<i>Run Full File once first to set the baseline.</i></div>')

    elif request.method == "POST" and tpl_of(sys) == TPL_DT:
        msg = run_document_transformation(sys)

    elif request.method == "POST" and (_blk := enforcement_block(sys)):
        msg = _blk
        CC_EVENTS.append({"sys": name,
                          "time": datetime.now().strftime("%Y%m%d_%H%M%S"),
                          "mode": "Completed with Errors (not authorized)",
                          "rows": 0, "file": "",
                          "ran_as": sys.get("workday_account") or "(none)"})

    elif request.method == "POST":
        # --- Schedule an Integration: read the launch parameters ---
        full_file = request.form.get("full_file") == "on"   # Full File checkbox
        only_workers = [x.strip() for x in
                        request.form.get("workers", "").split(",") if x.strip()]
        only_orgs = [x.strip() for x in
                     request.form.get("restrict_orgs", "").split(",") if x.strip()]
        aoem = request.form.get("as_of_entry_moment", "")
        eff = request.form.get("effective_date", "")

        rows = build_rows(sys, only_workers or None, only_orgs or None)
        current = {r["_key"]: row_hash(r) for r in rows}

        # Full File unchecked = incremental (Changes Only) since the last
        # successful run - real Workday uses the Last Successful watermark.
        baseline_note = ""
        if not full_file:
            prev = SNAPSHOTS.get(name, {})
            if not prev:
                baseline_note = (" (no prior baseline, so this run set it and "
                                 "output all rows - simulate a change, then run "
                                 "Changes Only again for a true delta)")
            rows = [r for r in rows
                    if prev.get(r["_key"]) != current[r["_key"]]]
        SNAPSHOTS[name] = current

        ccb = tpl_of(sys) == TPL_CCB
        a = sys["attributes"]
        os.makedirs(OUT_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = "xml" if a["Output_Format"] == "XML" else "csv"
        fname = a["Output_Filename"] or f"{name.replace(' ', '_')}_{stamp}.{ext}"
        content = (to_xml(rows, a["Version"],
                          record_tag="Enrollment_Record" if ccb else "Worker",
                          root_tag="Benefit_Enrollments" if ccb else "Workers")
                   if ext == "xml" else to_csv(rows))
        with open(os.path.join(OUT_DIR, fname), "w") as f:
            f.write(content)

        # Workday auto-fills Last Successful * from the prior successful run.
        sys["last_successful"] = {"as_of_entry_moment": aoem, "effective_date": eff}
        save_systems()

        mode_label = "Full File" if full_file else "Changes Only"
        scope = []
        if only_workers:
            scope.append(f"Workers={', '.join(only_workers)}")
        if only_orgs:
            scope.append(f"Orgs={', '.join(only_orgs)}")
        scope_txt = (" (" + "; ".join(scope) + ")") if scope else ""

        CC_EVENTS.append({"sys": name, "time": stamp,
                          "mode": mode_label + scope_txt,
                          "rows": len(rows), "file": fname,
                          "ran_as": sys.get("workday_account") or "(default user)"})
        msg = (f'<div class="ok-banner"><b>{name}</b> completed - '
               f'{mode_label}: {len(rows)} worker(s) in output.{baseline_note}{scope_txt} '
               f'Ran as <b>{sys.get("workday_account") or "default user"}</b>. '
               f'<a href="/cc-output/{fname}" target="_blank">View {fname}</a></div>')

    _ev = []
    for e in reversed(CC_EVENTS):
        f_cell = (f'<a href="/cc-output/{e["file"]}" target="_blank">{e["file"]}</a>'
                  if e.get("file") else "(no output)")
        _ev.append(
            f'<tr><td>{e["time"]}</td><td>{e["sys"]}</td><td>{e["mode"]}</td>'
            f'<td>{e["rows"]}</td><td>{e.get("ran_as", "")}</td>'
            f'<td>{f_cell}</td></tr>')
    events = "".join(_ev) or '<tr><td colspan="6">No runs yet.</td></tr>'

    if tpl_of(sys) == TPL_DT:
        body = f"""{msg}
<form method="post"><input type="hidden" name="sys" value="{name}">
<div class="card"><h2>Launch {name} (Document Transformation)</h2>
<p style="font-size:13px;color:#666">Runs the source connector (Full File),
then applies the attached XSLT to its XML output - the standard
Core Connector -&gt; DT integration process chain.</p>
<div class="btnrow"><button class="btn btn-ok">OK</button></div></div></form>
<div class="card"><h2>Process Monitor</h2>
<table><tr><th>Time</th><th>System</th><th>Mode</th><th>Rows</th><th>Ran As</th><th>Output</th></tr>
{events}</table></div>"""
        return html_resp(layout("Launch Integration",
                                f"{name} - Template: {TPL_DT}", body))

    # --- Schedule an Integration: defaults + faithful launch-parameter grid ---
    _now = datetime.now()
    aoem_def = _now.strftime("%Y-%m-%dT%H:%M")          # As Of Entry Moment
    eff_def = _now.strftime("%Y-%m-%d")                 # Effective Date
    _ls = sys.get("last_successful", {})
    ls_aoem = _ls.get("as_of_entry_moment", "")
    ls_eff = _ls.get("effective_date", "")
    data_secs_on = [s for s in SECTIONS if sys["services"].get(s)]
    hint = ""
    if not data_secs_on:
        hint = ('<div class="err-banner">No Worker data section services are '
                'enabled, so the output will contain only <b>Employee_ID</b>. '
                'Enable them in <a href="/task/configure-integration-services'
                f'?sys={name}">Configure Integration Services</a> (Personal / '
                'Status / Position / Compensation), then launch again.</div>')

    crit = f"""
<tr><td>Data Initialization Service - Exception Log</td><td></td><td></td><td></td><td></td></tr>
<tr><td>DIS - Performance Log</td><td></td><td></td><td></td><td></td></tr>
<tr><td>Effective Stack - Performance Log</td><td></td><td></td><td></td><td></td></tr>
<tr><td rowspan="4">Core Connector Date Launch Parameters</td>
    <td>As Of Entry Moment</td><td></td><td>Specify Value</td>
    <td><input type="datetime-local" name="as_of_entry_moment" value="{aoem_def}"></td></tr>
<tr><td>Effective Date</td><td></td><td>Specify Value</td>
    <td><input type="date" name="effective_date" value="{eff_def}"></td></tr>
<tr><td>Last Successful As Of Entry Moment</td><td></td><td>Specify Value</td>
    <td><input type="datetime-local" name="ls_aoem" value="{ls_aoem}"></td></tr>
<tr><td>Last Successful Effective Date</td><td></td><td>Specify Value</td>
    <td><input type="date" name="ls_eff" value="{ls_eff}"></td></tr>
<tr><td rowspan="3">Core Connector: Worker Integration Configuration</td>
    <td>Workers</td><td>Extracts only the specified Worker(s).</td><td>Specify Value</td>
    <td><input type="text" name="workers" placeholder="e.g. 21001, 21002"></td></tr>
<tr><td>Restrict Results By Orgs</td>
    <td>Extracts Workers for only the specified Organizations and all subordinates.</td>
    <td>Specify Value</td>
    <td><input type="text" name="restrict_orgs" placeholder="e.g. Finance, Audit"></td></tr>
<tr><td>Full File</td>
    <td>Extracts Workers as of the As Of Entry Moment and Effective Date,
        regardless of whether or not they have changed.</td>
    <td>Boolean</td>
    <td><input type="checkbox" name="full_file" checked></td></tr>"""

    body = f"""{msg}{hint}
<form method="post"><input type="hidden" name="sys" value="{name}">
<div class="card"><h2>Schedule an Integration - {name}</h2>
  <p><b>Request Name</b> <span style="color:#c00">*</span>&nbsp;
     <input type="text" name="request_name" value="{name}" style="width:320px"></p>
  <p><b>Integration System</b> &nbsp; {name}</p>
  <p><b>Run Frequency</b> &nbsp; Run Now</p>
</div>
<div class="card">
  <h2>Integration Criteria <span style="font-weight:normal;color:#888">5 items</span></h2>
  <table>
    <tr><th>Provider</th><th>Field</th><th>Description</th><th>Value Type</th><th>Value</th></tr>
    {crit}
  </table>
  <p style="font-size:12px;color:#888;margin-top:8px"><b>Full File</b> checked =
  full extract. Unchecked = Changes Only (delta since the last successful run).</p>
  <div class="btnrow">
    <button class="btn btn-ok">OK</button>
    <button class="btn btn-cancel" name="simulate" value="1">Simulate a data change</button>
    <a class="btn btn-ok" href="/task/maintain-test-workers?sys={name}" style="margin-left:8px">Maintain Test Workers</a>
  </div>
</div></form>
<div class="card"><h2>Process Monitor</h2>
<table><tr><th>Time</th><th>System</th><th>Mode</th><th>Rows</th><th>Ran As</th><th>Output</th></tr>
{events}</table></div>"""
    return html_resp(layout("Schedule an Integration",
                            f"{name} - Template: {TEMPLATE}", body))


def run_document_transformation(sys):
    dt = sys["dt"]
    src_name = dt.get("source_system")
    source = SYSTEMS.get(src_name)
    if not source or tpl_of(source) == TPL_DT:
        return ('<div class="err-banner">Validation error occurred. Set a '
                'valid (non-DT) Source Integration System in Configure '
                'Document Transformation.</div>')
    # 1. Run the source connector (Full File) - first event in the chain
    rows = build_rows(source)
    SNAPSHOTS[src_name] = {r["_key"]: row_hash(r) for r in rows}
    ccb = tpl_of(source) == TPL_CCB
    a = source["attributes"]
    xml = to_xml(rows, a["Version"],
                 record_tag="Enrollment_Record" if ccb else "Worker",
                 root_tag="Benefit_Enrollments" if ccb else "Workers")
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    src_file = f"{src_name.replace(' ', '_')}_{stamp}.xml"
    with open(os.path.join(OUT_DIR, src_file), "w") as f:
        f.write(xml)
    CC_EVENTS.append({"sys": src_name, "time": stamp, "mode": "Full File "
                      "(chained)", "rows": len(rows), "file": src_file})
    # 2. Apply the attached XSLT - second event
    try:
        from lxml import etree
        xslt = etree.XSLT(etree.fromstring(dt["xslt"].encode()))
        out = str(xslt(etree.fromstring(xml.encode())))
    except Exception as e:
        return (f'<div class="err-banner">Document Transformation failed: '
                f'{type(e).__name__}: {e}</div>')
    dt_file = dt.get("output_filename") or \
        f"{sys['system_name'].replace(' ', '_')}_{stamp}.txt"
    with open(os.path.join(OUT_DIR, os.path.basename(dt_file)), "w") as f:
        f.write(out)
    CC_EVENTS.append({"sys": sys["system_name"], "time": stamp,
                      "mode": "Document Transformation",
                      "rows": len(rows), "file": os.path.basename(dt_file)})
    return (f'<div class="ok-banner">Chain completed: <b>{src_name}</b> '
            f'({len(rows)} records) -&gt; XSLT -&gt; '
            f'<a href="/cc-output/{os.path.basename(dt_file)}" target="_blank">'
            f'{os.path.basename(dt_file)}</a></div>')


@app.route("/task/configure-document-transformation", methods=["GET", "POST"])
def configure_document_transformation():
    name = request.values.get("sys")
    sys = SYSTEMS.get(name)
    if not sys or tpl_of(sys) != TPL_DT:
        return redirect("/task/view-integration-system")
    msg = ""
    if request.method == "POST":
        sys["dt"]["source_system"] = request.form.get("source_system", "")
        sys["dt"]["xslt"] = request.form.get("xslt", DEFAULT_DT_XSLT)
        sys["dt"]["output_filename"] = request.form.get("output_filename",
                                                        "").strip()
        save_systems()
        msg = '<div class="ok-banner">Document Transformation configured.</div>'
    sources = [s for s, d in SYSTEMS.items() if tpl_of(d) != TPL_DT]
    opts = "".join(f'<option {"selected" if s == sys["dt"].get("source_system") else ""}>{s}</option>'
                   for s in sources)
    body = f"""{msg}
<form method="post"><input type="hidden" name="sys" value="{name}">
<div class="card"><h2>Document Transformation - {name}</h2>
  <label>Source Integration System (connector whose output this transforms)</label>
  <select name="source_system">{opts}</select>
  <label>Attached XSLT</label>
  <textarea name="xslt" rows="14">{sys["dt"].get("xslt","")}</textarea>
  <label>Output Filename (blank = sequence generator)</label>
  <input type="text" name="output_filename"
         value="{sys["dt"].get("output_filename","")}"
         placeholder="carrier_file.csv">
  <div class="btnrow"><button class="btn btn-ok">OK</button>
  <a class="btn btn-cancel" href="/task/view-integration-system?name={name}">Cancel</a></div>
</div></form>"""
    return html_resp(layout("Configure Document Transformation", name, body))


@app.route("/cc-output/<path:fname>")
def cc_output(fname):
    path = os.path.join(OUT_DIR, os.path.basename(fname))
    if not os.path.exists(path):
        return Response("Output not found", status=404)
    mt = "text/xml" if fname.endswith(".xml") else "text/plain"
    with open(path) as f:
        return Response(f.read(), mimetype=mt)


# ---------------------------------------------------------------------------
# Maintain Test Workers  (add / edit / terminate / delete the source roster)
# ---------------------------------------------------------------------------
@app.route("/task/maintain-test-workers", methods=["GET", "POST"])
def maintain_test_workers():
    """Add, edit, terminate or delete the source Workers so you can practice
    Full File and Changes Only (delta). Edits the in-memory roster
    (mws.WORKERS); like the delta baseline, it resets on server restart."""
    import copy
    sysname = request.values.get("sys", "")
    back = (f"/task/launch-integration?sys={sysname}" if sysname
            else "/task/launch-integration")
    msg = ""

    if request.method == "POST":
        action = request.form.get("action")
        eid = request.form.get("eid", "").strip()

        if action == "delete":
            before = len(mws.WORKERS)
            mws.WORKERS[:] = [w for w in mws.WORKERS if w["Employee_ID"] != eid]
            if hasattr(mws, "VALID_IDS"):
                mws.VALID_IDS.discard(eid)
            msg = (f'<div class="ok-banner">Deleted worker <b>{eid}</b>. It will '
                   f'no longer appear in any extract.</div>'
                   if len(mws.WORKERS) < before
                   else f'<div class="err-banner">No worker {eid} found.</div>')

        elif action == "terminate":
            w = next((x for x in mws.WORKERS if x["Employee_ID"] == eid), None)
            if w:
                w["Active"] = "0"
                msg = (f'<div class="ok-banner">Terminated worker <b>{eid}</b> '
                       f'(Active = 0). It drops from the extract unless Include '
                       f'Inactive Workers is on.</div>')

        elif action in ("add", "edit"):
            first = request.form.get("first", "").strip()
            last = request.form.get("last", "").strip()
            email = request.form.get("email", "").strip()
            org = request.form.get("org", "").strip()
            active = "1" if request.form.get("active") == "on" else "0"
            hire = request.form.get("hire", "").strip()
            bonus = request.form.get("bonus", "").strip()
            payments = ([{"Type": "Spot Bonus", "Amount": bonus,
                          "Date": datetime.now().strftime("%Y-%m-%d")}]
                        if bonus else [])
            existing = next((x for x in mws.WORKERS
                             if x["Employee_ID"] == eid), None)

            if not eid:
                msg = '<div class="err-banner">Employee_ID is required.</div>'
            elif action == "add" and existing:
                msg = (f'<div class="err-banner">Employee_ID {eid} already '
                       f'exists. Use Save Edit instead.</div>')
            else:
                if action == "add":
                    w = copy.deepcopy(mws.WORKERS[0]) if mws.WORKERS else {}
                    w["Benefits"] = []
                    w["Dependents"] = []
                    mws.WORKERS.append(w)
                    if hasattr(mws, "VALID_IDS"):
                        mws.VALID_IDS.add(eid)
                else:
                    w = existing or {}
                w.update({
                    "Employee_ID": eid, "First_Name": first, "Last_Name": last,
                    "Full_Name": f"{first} {last}".strip(),
                    "Email": email, "Email_Primary": email,
                    "Org": org, "Organization": org,
                    "Active": active, "Hire_Date": hire, "Payments": payments,
                })
                msg = (f'<div class="ok-banner">'
                       f'{"Added" if action == "add" else "Updated"} worker '
                       f'<b>{eid}</b>. Run <b>Changes Only</b> to see it in the '
                       f'delta.</div>')

    # ----- pre-fill the form when editing an existing worker -----
    ew = None
    edit_eid = request.args.get("edit", "")
    if edit_eid:
        ew = next((x for x in mws.WORKERS if x["Employee_ID"] == edit_eid), None)

    def g(k, d=""):
        return ew.get(k, d) if ew else d
    f_bonus = ""
    if ew and ew.get("Payments"):
        f_bonus = str(sum(float(p.get("Amount", 0)) for p in ew["Payments"]))
    active_chk = "checked" if (not ew or ew.get("Active") == "1") else ""
    eid_ro = "readonly" if ew else ""

    roster = ""
    for w in mws.WORKERS:
        roster += (
            f'<tr><td>{w["Employee_ID"]}</td>'
            f'<td>{w.get("First_Name", "")} {w.get("Last_Name", "")}</td>'
            f'<td>{w.get("Email", "")}</td>'
            f'<td>{w.get("Active", "")}</td>'
            f'<td>{w.get("Hire_Date", "")}</td>'
            f'<td>{w.get("Org", "")}</td>'
            f'<td><a class="btn btn-ok" '
            f'href="/task/maintain-test-workers?sys={sysname}&edit={w["Employee_ID"]}">Edit</a> '
            f'<form method="post" style="display:inline">'
            f'<input type="hidden" name="sys" value="{sysname}">'
            f'<input type="hidden" name="eid" value="{w["Employee_ID"]}">'
            f'<button class="btn btn-cancel" name="action" value="terminate">Terminate</button> '
            f'<button class="btn btn-cancel" name="action" value="delete">Delete</button>'
            f'</form></td></tr>')

    body = f"""{msg}
<div class="card"><h2>Maintain Test Workers</h2>
<p style="font-size:13px;color:#666">Add / edit / terminate / delete the source
Workers, then run the integration. <b>Adds and edits</b> appear in Changes Only
(delta). <b>Delete</b> removes the worker entirely. <b>Terminate</b> sets Active=0
(drops from the extract unless Include Inactive Workers is on). This edits the
in-memory roster and resets on server restart.</p>
<table>
<tr><th>Employee_ID</th><th>Name</th><th>Email</th><th>Active</th><th>Hire Date</th><th>Org</th><th>Actions</th></tr>
{roster}
</table>
<div class="btnrow"><a class="btn btn-ok" href="{back}">Back to Launch</a></div>
</div>

<div class="card"><h2>{"Edit Worker " + edit_eid if ew else "Add a Worker"}</h2>
<form method="post">
<input type="hidden" name="sys" value="{sysname}">
<p><label>Employee_ID</label>
   <input type="text" name="eid" value="{g('Employee_ID')}" placeholder="e.g. 21024" {eid_ro}></p>
<p><label>First Name</label> <input type="text" name="first" value="{g('First_Name')}"></p>
<p><label>Last Name</label> <input type="text" name="last" value="{g('Last_Name')}"></p>
<p><label>Email</label> <input type="text" name="email" value="{g('Email')}"></p>
<p><label>Org</label> <input type="text" name="org" value="{g('Org')}"
   placeholder="Finance / HR Operations / IT Services / Audit / Legal"></p>
<p><label>Hire Date</label> <input type="date" name="hire" value="{g('Hire_Date')}"></p>
<p><label>Bonus amount (optional)</label>
   <input type="text" name="bonus" value="{f_bonus}" placeholder="e.g. 500"></p>
<p><label><input type="checkbox" name="active" {active_chk}> Active</label></p>
<div class="btnrow">
  <button class="btn btn-ok" name="action" value="{'edit' if ew else 'add'}">
    {"Save Edit" if ew else "Add Worker"}</button>
  <a class="btn btn-cancel" href="/task/maintain-test-workers?sys={sysname}"
     style="margin-left:8px">Clear</a>
</div>
</form></div>"""
    return html_resp(layout("Maintain Test Workers", "", body))


# ---------------------------------------------------------------------------
# Register the field-level Worker domains into security's grantable catalog
# so they appear automatically in Maintain Domain Permissions. This runs at
# import; placing it at the end keeps route-registration order unchanged.
# ---------------------------------------------------------------------------
try:
    import security as _sec_catalog
    for _d, _desc in WORKER_FIELD_DOMAINS.items():
        _sec_catalog.DOMAINS.setdefault(_d, _desc)
except Exception:
    pass
