"""
security.py - ISU / ISSG security simulation.

The real Workday chain, reproduced:
  1. Create Integration System User (ISU)        - the service account
  2. Create Security Group (ISSG)                - constrained-less group, add the ISU
  3. Maintain Domain Permissions for the ISSG    - grant Get/Put on domains
     -> changes are PENDING until step 4 (the classic gotcha)
  4. Activate Pending Security Policy Changes    - with a comment, like real Workday
  5. Enforce Authentication toggle               - when ON, the API endpoints
     require HTTP Basic auth from an ISU whose ISSG has the right domain access

Domain -> endpoint mapping:
  Worker Data: Workers (Get)         -> Human_Resources SOAP (Get_Workers)
  Custom Report Web Services (Get)   -> RaaS report URLs
  One-Time Payments (Put)            -> Compensation web service (inbound EIB)

With enforcement ON, call like:
  curl -u my_isu:password "http://127.0.0.1:8443/ccx/service/customreport2/..."
"""

import json
import os
from datetime import datetime

from flask import request, Response

from mock_workday_server import app
from workday_ui import layout, html_resp, persist

SEC_FILE = "security_config.json"

DOMAINS = {
    "Worker Data: Workers": "Human_Resources SOAP (Get_Workers) - needs Get",
    "Custom Report Web Services": "RaaS report URLs - needs Get",
    "One-Time Payments": "Compensation web service (inbound EIB) - needs Put",
    "Worker Data: Benefits Elections": "Benefits_Administration service - needs Get",
    "Payroll Inputs and Results": "Payroll web service - needs Put",
}
ACCESS_TYPES = ["Get", "Put"]

# (path prefix, domain, required access)
ENDPOINT_POLICY = [
    ("/ccx/service/SUPER_TENANT/Human_Resources", "Worker Data: Workers", "Get"),
    ("/ccx/service/customreport2/", "Custom Report Web Services", "Get"),
    ("/ccx/service/SUPER_TENANT/Compensation", "One-Time Payments", "Put"),
    ("/ccx/service/SUPER_TENANT/Benefits_Administration",
     "Worker Data: Benefits Elections", "Get"),
    ("/ccx/service/SUPER_TENANT/Payroll", "Payroll Inputs and Results", "Put"),
]


def _default():
    return {"enforce": False, "isus": {}, "issgs": {}, "activations": []}


def load_sec():
    if os.path.exists(SEC_FILE):
        with open(SEC_FILE) as f:
            return json.load(f)
    return _default()


SEC = load_sec()


def save_sec():
    persist(SEC_FILE, SEC)


def soap_fault(message, status):
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body>
    <env:Fault>
      <faultcode>env:Client</faultcode>
      <faultstring>{message}</faultstring>
    </env:Fault>
  </env:Body>
</env:Envelope>"""
    return Response(xml, status=status, mimetype="text/xml")


# ---------------------------------------------------------------------------
# Enforcement gate (runs before every request)
# ---------------------------------------------------------------------------
@app.before_request
def security_gate():
    if not SEC["enforce"]:
        return None
    path = request.path
    for prefix, domain, access in ENDPOINT_POLICY:
        if not path.startswith(prefix):
            continue
        auth = request.authorization
        if (not auth or auth.username not in SEC["isus"]
                or SEC["isus"][auth.username]["password"] != auth.password):
            return soap_fault("invalid username or password", 401)
        # Does any ISSG containing this ISU have ACTIVE access on the domain?
        for g in SEC["issgs"].values():
            if (auth.username in g["members"]
                    and access in g["active"].get(domain, [])):
                return None
        return soap_fault(
            f"Processing error occurred. The task submitted is not authorized: "
            f"requires {access} access to domain '{domain}'. "
            f"(Did you Activate Pending Security Policy Changes?)", 403)
    return None


# ---------------------------------------------------------------------------
# Create Integration System User (ISU)
# ---------------------------------------------------------------------------
@app.route("/task/create-isu", methods=["GET", "POST"])
def create_isu():
    msg = ""
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        if not u or not p:
            msg = '<div class="err-banner">Validation error occurred. Username and password are required.</div>'
        elif u in SEC["isus"]:
            msg = f'<div class="err-banner">Validation error occurred. ISU \'{u}\' already exists.</div>'
        else:
            SEC["isus"][u] = {"password": p,
                              "session_timeout": request.form.get("timeout", "0"),
                              "exempt_from_password_expiration": True}
            save_sec()
            msg = (f'<div class="ok-banner">Created ISU <b>{u}</b>. Next: add it '
                   f'to a security group in <a href="/task/create-security-group" '
                   f'target="_blank">Create Security Group</a>.</div>')

    rows = "".join(f'<tr><td>{u}</td><td>{d["session_timeout"]} min</td></tr>'
                   for u, d in SEC["isus"].items()) or \
           '<tr><td colspan="2">No ISUs yet.</td></tr>'
    body = f"""{msg}
<form method="post"><div class="card">
  <label>User Name <span class="req">*</span></label>
  <input type="text" name="username" placeholder="ISU_CCW_Outbound">
  <label>Password <span class="req">*</span></label>
  <input type="text" name="password" placeholder="********">
  <label>Session Timeout Minutes <span style="font-weight:400;color:#888">
    (0 = no timeout, the usual ISU setting)</span></label>
  <input type="text" name="timeout" value="0" style="max-width:120px">
  <div class="btnrow"><button class="btn btn-ok">OK</button>
  <a class="btn btn-cancel" href="/home">Cancel</a></div>
</div></form>
<div class="card"><h2>Existing Integration System Users</h2>
<table><tr><th>User</th><th>Session Timeout</th></tr>{rows}</table></div>"""
    return html_resp(layout("Create Integration System User",
                            "Service account for integrations (ISU)", body))


# ---------------------------------------------------------------------------
# Create Security Group (ISSG)
# ---------------------------------------------------------------------------
@app.route("/task/create-security-group", methods=["GET", "POST"])
def create_security_group():
    msg = ""
    if request.method == "POST":
        name = request.form.get("group_name", "").strip()
        members = request.form.getlist("members")
        if not name:
            msg = '<div class="err-banner">Validation error occurred. Group name is required.</div>'
        elif name in SEC["issgs"]:
            msg = f'<div class="err-banner">Validation error occurred. Group \'{name}\' already exists.</div>'
        else:
            SEC["issgs"][name] = {"type": "Integration System Security Group "
                                          "(Unconstrained)",
                                  "members": members, "active": {}, "pending": {}}
            save_sec()
            msg = (f'<div class="ok-banner">Created ISSG <b>{name}</b> with '
                   f'{len(members)} member(s). Next: '
                   f'<a href="/task/maintain-domain-permissions?group={name}" '
                   f'target="_blank">Maintain Domain Permissions</a>.</div>')

    isu_checks = "".join(
        f'<label><input type="checkbox" name="members" value="{u}"> {u}</label>'
        for u in SEC["isus"]) or '<span style="color:#888">No ISUs yet - create one first.</span>'
    rows = "".join(
        f'<tr><td>{g}</td><td>{", ".join(d["members"]) or "-"}</td>'
        f'<td>{len(d["active"])} active / {len(d["pending"])} pending</td></tr>'
        for g, d in SEC["issgs"].items()) or \
        '<tr><td colspan="3">No security groups yet.</td></tr>'
    body = f"""{msg}
<form method="post"><div class="card">
  <label>Type of Tenanted Security Group</label>
  <select disabled><option>Integration System Security Group (Unconstrained)</option></select>
  <label>Name <span class="req">*</span></label>
  <input type="text" name="group_name" placeholder="ISSG_CCW_Outbound">
  <label>Integration System Users (members)</label>
  <div class="checks">{isu_checks}</div>
  <div class="btnrow"><button class="btn btn-ok">OK</button>
  <a class="btn btn-cancel" href="/home">Cancel</a></div>
</div></form>
<div class="card"><h2>Existing Security Groups</h2>
<table><tr><th>Group</th><th>Members</th><th>Domain Policies</th></tr>{rows}</table></div>"""
    return html_resp(layout("Create Security Group",
                            "Integration System Security Group (ISSG)", body))


# ---------------------------------------------------------------------------
# Maintain Domain Permissions (changes are PENDING until activated)
# ---------------------------------------------------------------------------
@app.route("/task/maintain-domain-permissions", methods=["GET", "POST"])
def maintain_domain_permissions():
    group = request.values.get("group") or next(iter(SEC["issgs"]), None)
    g = SEC["issgs"].get(group)
    if not g:
        return html_resp(layout("Maintain Domain Permissions", "",
                                '<div class="err-banner">No security groups yet. '
                                '<a href="/task/create-security-group">Create one</a>.</div>'))
    msg = ""
    if request.method == "POST":
        pending = {}
        for d in DOMAINS:
            grants = [a for a in ACCESS_TYPES
                      if request.form.get(f"{d}|{a}") == "on"]
            if grants:
                pending[d] = grants
        g["pending"] = pending
        save_sec()
        msg = ('<div class="err-banner"><b>Pending security policy changes '
               'saved - NOT yet in effect.</b> API calls will still be denied '
               'until you run <a href="/task/activate-security-changes" '
               'target="_blank">Activate Pending Security Policy Changes</a>.</div>')

    grp_opts = "".join(f'<option {"selected" if x == group else ""}>{x}</option>'
                       for x in SEC["issgs"])
    rows = ""
    for d, desc in DOMAINS.items():
        cells = ""
        for a in ACCESS_TYPES:
            pend = a in g["pending"].get(d, [])
            act = a in g["active"].get(d, [])
            mark = " (active)" if act else (" (pending)" if pend else "")
            cells += (f'<td><label><input type="checkbox" name="{d}|{a}" '
                      f'{"checked" if (pend or act) else ""}> {a}{mark}'
                      f'</label></td>')
        rows += f"<tr><td>{d}<br><span style='color:#888;font-size:12px'>{desc}</span></td>{cells}</tr>"
    body = f"""{msg}
<form method="get"><div class="card">
  <label>Security Group</label>
  <select name="group" onchange="this.form.submit()">{grp_opts}</select>
</div></form>
<form method="post"><input type="hidden" name="group" value="{group}">
<div class="card"><h2>Domain Security Policies for {group}</h2>
<table><tr><th>Domain</th><th>Get/View</th><th>Put/Modify</th></tr>{rows}</table>
<div class="btnrow"><button class="btn btn-ok">OK</button>
<a class="btn btn-cancel" href="/home">Cancel</a></div>
</div></form>"""
    return html_resp(layout("Maintain Domain Permissions", group, body))


# ---------------------------------------------------------------------------
# Activate Pending Security Policy Changes
# ---------------------------------------------------------------------------
@app.route("/task/activate-security-changes", methods=["GET", "POST"])
def activate_security_changes():
    msg = ""
    if request.method == "POST":
        comment = request.form.get("comment", "").strip()
        if not comment:
            msg = ('<div class="err-banner">Validation error occurred. '
                   'Comment is required (just like the real task).</div>')
        else:
            n = 0
            for g in SEC["issgs"].values():
                for d, grants in g["pending"].items():
                    g["active"][d] = grants
                    n += 1
                g["pending"] = {}
            SEC["activations"].append(
                {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "comment": comment, "policies": n})
            save_sec()
            msg = (f'<div class="ok-banner">Activated {n} pending domain '
                   f'polic{"y" if n == 1 else "ies"}. Security changes are now '
                   f'in effect.</div>')

    hist = "".join(f'<tr><td>{a["time"]}</td><td>{a["policies"]}</td>'
                   f'<td>{a["comment"]}</td></tr>'
                   for a in reversed(SEC["activations"])) or \
           '<tr><td colspan="3">No activations yet.</td></tr>'
    pending_n = sum(len(g["pending"]) for g in SEC["issgs"].values())
    body = f"""{msg}
<form method="post"><div class="card">
  <h2>{pending_n} pending polic{"y" if pending_n == 1 else "ies"} awaiting activation</h2>
  <label>Comment <span class="req">*</span></label>
  <input type="text" name="comment"
         placeholder="e.g. Granting CCW outbound ISU access to Worker Data">
  <div class="btnrow"><button class="btn btn-ok">OK</button>
  <a class="btn btn-cancel" href="/home">Cancel</a></div>
</div></form>
<div class="card"><h2>Activation History</h2>
<table><tr><th>Time</th><th>Policies</th><th>Comment</th></tr>{hist}</table></div>"""
    return html_resp(layout("Activate Pending Security Policy Changes",
                            "Security edits do nothing until activated", body))


# ---------------------------------------------------------------------------
# Security Overview + enforcement toggle
# ---------------------------------------------------------------------------
@app.route("/task/security-overview", methods=["GET", "POST"])
def security_overview():
    msg = ""
    if request.method == "POST":
        SEC["enforce"] = request.form.get("enforce") == "on"
        save_sec()
        state = "ON - API calls now require ISU Basic auth" if SEC["enforce"] \
            else "OFF - endpoints are open (practice mode)"
        msg = f'<div class="ok-banner">Authentication enforcement: <b>{state}</b></div>'

    groups = ""
    for gname, g in SEC["issgs"].items():
        doms = "".join(
            f"<tr><td>{d}</td><td>{', '.join(v)}</td><td>Active</td></tr>"
            for d, v in g["active"].items()) + "".join(
            f"<tr><td>{d}</td><td>{', '.join(v)}</td>"
            f"<td style='color:#a32018'>Pending</td></tr>"
            for d, v in g["pending"].items())
        groups += f"""<div class="card"><h2>{gname}
<span style="font-weight:400;font-size:13px;color:#888"> - members:
{", ".join(g["members"]) or "none"}</span></h2>
<table><tr><th>Domain</th><th>Access</th><th>Status</th></tr>
{doms or '<tr><td colspan="3">No domain policies.</td></tr>'}</table></div>"""

    curl = ('curl -u ISU_USER:PASSWORD "http://127.0.0.1:8443/ccx/service/'
            'customreport2/SUPER_TENANT/ISU_Demo/Worker_Report?format=json"')
    body = f"""{msg}
<form method="post"><div class="card"><h2>Authentication Enforcement</h2>
  <label><input type="checkbox" name="enforce"
    {"checked" if SEC["enforce"] else ""}> Require ISU authentication on
    SOAP / RaaS / Compensation endpoints</label>
  <p style="font-size:13px;color:#666;margin-top:10px">When ON, call the APIs
  with HTTP Basic auth:<br><code>{curl}</code></p>
  <div class="btnrow"><button class="btn btn-ok">OK</button></div>
</div></form>
{groups or '<div class="card">No security groups configured yet.</div>'}"""
    return html_resp(layout("Security Overview",
                            f"Enforcement: {'ON' if SEC['enforce'] else 'OFF'} - "
                            f"{len(SEC['isus'])} ISU(s), {len(SEC['issgs'])} ISSG(s)",
                            body))
