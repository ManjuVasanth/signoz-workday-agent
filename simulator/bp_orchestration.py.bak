# -*- coding: utf-8 -*-
"""
bp_orchestration.py  --  Tenant-side Business-Process-triggered orchestration flow.

Replicates the "Empowering Developers" episode's tenant half: connecting a
Workday Business Process to an Extend orchestration, then triggering it.

  - View Worker (Logan McNeil) -> Actions -> Change My Home Contact Information
  - View Business Process Definition (Home Contact Change) + steps grid
  - Related Actions -> Configure Orchestrations  /  Edit Definition
  - Configure Orchestration Service: pick orchestration, Run As User, Advance
  - Submit the contact change -> the bound orchestration FIRES (in-process via
    orchestrate.run_orchestration) -> the Log hit shows in Process Run Logs
    (wd_level / wd_message / wd_orch_id / wd_tenant_alias), like the real tenant.

INSTALL
-------
1. Drop this file next to workday_ui.py / orchestrate.py.
2. In workday_ui.py's `if __name__ == "__main__":` block, next to the other
   submodule imports, add:

       import bp_orchestration   # noqa: F401  (registers BP-triggered orchestration flow)

3. Restart, Ctrl+F5. Open:  http://localhost:8443/tenant/bp/home_contact_change
   (or type "Business Process Definition" / "Change My Home Contact" in search)

Self-contained: persists to bp_store.json; reads orchestrations from
orchestrate_store.json and runs them through orchestrate's engine.
"""

import os
import json
import datetime

from flask import request, Response

import workday_ui as wd
app = wd.app

BP_STORE = "bp_store.json"
TENANT_ALIAS = "hack116_wcpdev1"

# register tenant tasks in the search bar
_NEW_TASKS = [
    {"name": "View Worker", "url": "/tenant/worker/21001"},
    {"name": "Change My Home Contact Information", "url": "/tenant/task/change-home-contact/21001"},
    {"name": "View Business Process Definition", "url": "/tenant/bp/home_contact_change"},
    {"name": "Configure Orchestrations", "url": "/tenant/bp/home_contact_change"},
    {"name": "Business Process Run Logs", "url": "/tenant/bp/logs"},
]
try:
    have = {t["url"] for t in wd.TASKS}
    for t in _NEW_TASKS:
        if t["url"] not in have:
            wd.TASKS.append(t)
except Exception:
    pass


# ===========================================================================
# Store
# ===========================================================================
def seed():
    return {
        "bps": {
            "home_contact_change": {
                "id": "home_contact_change",
                "name": "Home Contact Change for Global Modern Services",
                "businessObject": "Global Modern Services",
                "effectiveDate": "02/24/2026",
                "timeZone": "GMT-08:00 Pacific Time (Los Angeles)",
                "dueDate": "1 Day",
                # the configured "Service: Orchestration Service" binding (None until set)
                "orchestration": None,
                "steps": [
                    {"order": "a", "iff": "", "type": "Initiation", "specify": "",
                     "optional": "No", "group": "", "runAs": "", "dueDate": ""},
                    {"order": "aa", "iff": "", "type": "Service", "specify": "Orchestration Service",
                     "optional": "No", "group": "", "runAs": "", "dueDate": "", "isOrch": True},
                    {"order": "b", "iff": "Worker is Employee?", "type": "Integration", "specify": "",
                     "optional": "No", "group": "", "runAs": "ISU Cloud Commute for Worker", "dueDate": ""},
                    {"order": "c", "iff": "Triggered from International Assignment (US)?", "type": "To Do",
                     "specify": "IA Worker Tax Elections", "optional": "No",
                     "group": "Payroll Partner", "runAs": "", "dueDate": "2 Days"},
                    {"order": "c", "iff": "Change in State / Ohio or Pennsylvania?", "type": "To Do",
                     "specify": "Complete State Withholding Elections (3rd Party Integration)",
                     "optional": "No", "group": "Employee As Self", "runAs": "", "dueDate": "2 Days"},
                    {"order": "c", "iff": "Not Triggered from Onboarding?", "type": "Action",
                     "specify": "Complete Province Tax Elections", "optional": "No",
                     "group": "Employee As Self", "runAs": "", "dueDate": "2 Days"},
                ],
            }
        },
        "logs": [],
    }


def load():
    if not os.path.exists(BP_STORE):
        save(seed())
    try:
        with open(BP_STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return seed()


def save(d):
    with open(BP_STORE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)


# ===========================================================================
# Orchestration helpers (read + run via orchestrate.py)
# ===========================================================================
def all_orchestrations():
    """List every orchestration across orchestrate apps as pickable options."""
    out = []
    try:
        import orchestrate
        store = orchestrate.load()
        for a in store.get("apps", {}).values():
            for name, o in a.get("orchestrations", {}).items():
                out.append({"appId": a.get("appId", ""), "refId": a.get("refId", ""),
                            "name": name, "type": o.get("type", ""),
                            "startType": o.get("startType", "")})
    except Exception:
        pass
    return out


def run_orchestration(app_id, name):
    """Fire an orchestration through orchestrate's engine and return its trace."""
    import orchestrate
    store = orchestrate.load()
    for a in store.get("apps", {}).values():
        if a.get("appId") == app_id and name in a.get("orchestrations", {}):
            return orchestrate.run_orchestration(a["orchestrations"][name], "Business Process")
    return {"status": "Error", "trace": [{"step": name, "status": "Error",
            "message": "orchestration not found"}], "durationMs": 0}


def worker(emp_id):
    for w in getattr(wd.mws, "WORKERS", []):
        if str(w.get("Employee_ID")) == str(emp_id):
            return w
    return {"Employee_ID": emp_id, "Worker": "Unknown Worker", "Manager": ""}


# ===========================================================================
# Shared bits
# ===========================================================================
BANNER = ("<div style='background:linear-gradient(90deg,#005cb9,#0a6fd0);color:#fff;"
          "padding:18px 26px;border-radius:10px;display:flex;align-items:center;gap:14px;"
          "margin-bottom:22px'><div style='font-size:22px;font-weight:700'>%s</div>"
          "<div style='opacity:.9'>%s</div></div>")


def esc(t):
    return (str(t) if t is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ===========================================================================
# View Worker  (Actions -> Change Home Contact)
# ===========================================================================
@app.route("/tenant/worker/<emp_id>")
def view_worker(emp_id):
    w = worker(emp_id)
    name = w.get("Worker", "Worker")
    body = """
    <div class="card">
      <div style="display:flex;gap:24px;flex-wrap:wrap">
        <div style="min-width:230px">
          <div style="width:120px;height:120px;border-radius:14px;background:#005cb9;color:#fff;
            display:flex;align-items:center;justify-content:center;font-size:40px;font-weight:700">%s</div>
          <h2 style="margin:14px 0 2px">%s</h2>
          <div style="color:#666">%s</div>
          <div style="margin-top:14px;display:flex;gap:10px">
            <a class="btn" href="/tenant/task/change-home-contact/%s">Actions &#9662;</a>
          </div>
          <div style="margin-top:10px;font-size:13px;color:#888">Actions &#8250; Personal Data &#8250;
            <a href="/tenant/task/change-home-contact/%s"><b>Change My Home Contact Information</b></a></div>
        </div>
        <div style="flex:1;min-width:320px">
          <h3>Job Details</h3>
          <table style="font-size:14px;line-height:2">
            <tr><td style="color:#666;padding-right:24px">Employee ID</td><td>%s</td></tr>
            <tr><td style="color:#666">Manager</td><td>%s</td></tr>
            <tr><td style="color:#666">Business Title</td><td>%s</td></tr>
            <tr><td style="color:#666">Location</td><td>%s</td></tr>
          </table>
          <p style="margin-top:18px;font-size:13px;color:#888">Related Business Process:
            <a href="/tenant/bp/home_contact_change"><b>Home Contact Change</b></a></p>
        </div>
      </div>
    </div>""" % (
        esc(name[:1]), esc(name), esc(w.get("Position", w.get("Business_Title", "Worker"))),
        esc(emp_id), esc(emp_id), esc(emp_id), esc(w.get("Manager", "")),
        esc(w.get("Business_Title", w.get("Position", "Chef"))), esc(w.get("Location", "San Francisco")))
    return wd.html_resp(wd.layout("View Worker - %s" % name, "Worker", body, banner=False))


# ===========================================================================
# View Business Process Definition  (+ Related Actions menu)
# ===========================================================================
@app.route("/tenant/bp/<bp_id>")
def view_bp(bp_id):
    d = load()
    bp = d["bps"].get(bp_id)
    if not bp:
        return wd.html_resp(wd.layout("Not found", "", "<div class='card'>Business process not found.</div>"))
    rows = ""
    for s in bp["steps"]:
        specify = esc(s.get("specify", ""))
        if s.get("isOrch") and bp.get("orchestration"):
            o = bp["orchestration"]
            specify = ("Orchestration Service &nbsp;<span style='color:#2557d6'>&#8594; "
                       "%s (%s)</span>" % (esc(o["name"]), esc(o["refId"])))
        rows += ("<tr><td>&#128269;</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                 "<td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                     esc(s.get("order", "")), esc(s.get("iff", "")), esc(s.get("type", "")),
                     specify, esc(s.get("optional", "")), esc(s.get("group", "")),
                     esc(s.get("runAs", "")), esc(s.get("dueDate", ""))))
    configured = bp.get("orchestration")
    cfg_note = ("<div style='background:#e8f5e9;border:1px solid #b6dcb9;border-radius:8px;"
                "padding:10px 14px;margin-bottom:16px;font-size:13px'>&#10003; Orchestration Service "
                "configured: <b>%s</b> (Run As: %s, Advance: %s)</div>" % (
                    esc(configured["name"]), esc(configured.get("runAs", "Default")),
                    "Yes" if configured.get("advance") else "No")) if configured else (
        "<div style='background:#fff3cd;border:1px solid #ffe69c;border-radius:8px;"
        "padding:10px 14px;margin-bottom:16px;font-size:13px'>&#9888; No Orchestration Service configured yet. "
        "Use <b>Related Actions &#8250; Configure Orchestrations</b>.</div>")
    body = BANNER % ("View Business Process Definition", esc(bp["name"])) + """
    <div class="card">
      <div style="display:flex;gap:14px;align-items:center;margin-bottom:16px">
        <details style="position:relative">
          <summary style="cursor:pointer;list-style:none;border:1px solid #c4ccd6;border-radius:20px;
            padding:7px 16px;font-weight:600">Related Actions &#8943;</summary>
          <div style="position:absolute;z-index:20;background:#fff;border:1px solid #d6dde6;border-radius:10px;
            box-shadow:0 8px 28px rgba(0,0,0,.14);min-width:240px;padding:8px 0;margin-top:6px">
            <div style="padding:8px 16px;font-weight:700;color:#888;font-size:12px">Business Process</div>
            <a style="display:block;padding:9px 16px" href="/tenant/bp/%s/configure-orchestration">Configure Orchestrations</a>
            <a style="display:block;padding:9px 16px" href="/tenant/bp/%s/edit">Edit Definition</a>
            <a style="display:block;padding:9px 16px" href="/tenant/task/change-home-contact/21001">Run (Change Home Contact)</a>
          </div>
        </details>
      </div>
      %s
      <table style="font-size:13px;line-height:1.6">
        <tr><td style="color:#666;padding-right:30px">Effective Date</td><td>%s</td></tr>
        <tr><td style="color:#666">Time Zone</td><td>%s</td></tr>
        <tr><td style="color:#666">Business Object</td><td><a>%s</a></td></tr>
        <tr><td style="color:#666">Due Date</td><td>%s</td></tr>
      </table>
      <h3 style="margin-top:22px">Business Process Steps <span style="color:#888;font-weight:400">%d items</span></h3>
      <div class="wd-grid"><table>
        <tr><th>Step</th><th>Order</th><th>If</th><th>Type</th><th>Specify</th><th>Optional</th>
            <th>Group</th><th>Run As User</th><th>Due Date</th></tr>
        %s
      </table></div>
    </div>""" % (bp_id, bp_id, cfg_note, esc(bp["effectiveDate"]), esc(bp["timeZone"]),
                 esc(bp["businessObject"]), esc(bp["dueDate"]), len(bp["steps"]), rows)
    return wd.html_resp(wd.layout("View Business Process Definition", "", body, banner=False))


# ===========================================================================
# Configure Orchestration Service
# ===========================================================================
@app.route("/tenant/bp/<bp_id>/configure-orchestration", methods=["GET", "POST"])
def configure_orchestration(bp_id):
    d = load()
    bp = d["bps"].get(bp_id)
    if not bp:
        return wd.html_resp(wd.layout("Not found", "", "<div class='card'>Not found.</div>"))
    if request.method == "POST":
        sel = request.form.get("orchestration", "")   # "appId|refId|name"
        if sel:
            app_id, ref_id, name = (sel.split("|", 2) + ["", "", ""])[:3]
            bp["orchestration"] = {"appId": app_id, "refId": ref_id, "name": name,
                                   "runAs": request.form.get("runAs", "Default"),
                                   "advance": request.form.get("advance") == "on"}
            save(d)
        return Response("", status=302, headers={"Location": "/tenant/bp/%s" % bp_id})

    opts = ""
    cur = bp.get("orchestration") or {}
    for o in all_orchestrations():
        val = "%s|%s|%s" % (o["appId"], o["refId"], o["name"])
        selected = " selected" if (cur.get("name") == o["name"] and cur.get("appId") == o["appId"]) else ""
        bptag = "  [BP-trigger]" if o.get("startType") == "business-process" else ""
        opts += "<option value='%s'%s>%s (%s)%s</option>" % (
            esc(val), selected, esc(o["name"]), esc(o["refId"]), bptag)
    runas = cur.get("runAs", "Default")
    body = BANNER % ("Configure Orchestration Service",
                     esc(bp["name"]) + " step aa - Service [Orchestration Service]") + """
    <form method="POST" class="card" style="max-width:760px">
      <h3>Configuration</h3>
      <label style="display:block;font-weight:600;margin:14px 0 6px">Orchestration <span style="color:#d33">*</span></label>
      <select name="orchestration" style="width:100%%;padding:10px;border:1px solid #c4ccd6;border-radius:8px">%s</select>
      <label style="display:flex;align-items:center;gap:10px;margin-top:18px;font-weight:600">
        <input type="checkbox" name="advance" %s> Advance business process step when orchestration completes</label>
      <h3 style="margin-top:26px">Run As User</h3>
      <label style="display:flex;align-items:center;gap:10px;margin:8px 0"><input type="radio" name="runAs" value="User" %s> User</label>
      <label style="display:flex;align-items:center;gap:10px;margin:8px 0"><input type="radio" name="runAs" value="User from Field" %s> User from Field</label>
      <label style="display:flex;align-items:center;gap:10px;margin:8px 0"><input type="radio" name="runAs" value="Default" %s> Default (processing user from previous step)</label>
      <div style="margin-top:24px;display:flex;gap:10px">
        <button class="btn pri" type="submit">OK</button>
        <a class="btn" href="/tenant/bp/%s">Cancel</a>
      </div>
    </form>""" % (opts, "checked" if cur.get("advance", True) else "",
                  "checked" if runas == "User" else "",
                  "checked" if runas == "User from Field" else "",
                  "checked" if runas == "Default" else "", bp_id)
    return wd.html_resp(wd.layout("Configure Orchestration Service", "", body, banner=False))


# ===========================================================================
# Edit Business Process Definition (lightweight - add an Orchestration Service step)
# ===========================================================================
@app.route("/tenant/bp/<bp_id>/edit", methods=["GET", "POST"])
def edit_bp(bp_id):
    d = load()
    bp = d["bps"].get(bp_id)
    if not bp:
        return wd.html_resp(wd.layout("Not found", "", "<div class='card'>Not found.</div>"))
    if request.method == "POST":
        bp["effectiveDate"] = request.form.get("effectiveDate", bp["effectiveDate"])
        bp["timeZone"] = request.form.get("timeZone", bp["timeZone"])
        save(d)
        return Response("", status=302, headers={"Location": "/tenant/bp/%s" % bp_id})
    body = BANNER % ("Edit Business Process Definition", esc(bp["name"])) + """
    <form method="POST" class="card" style="max-width:640px">
      <label style="display:block;font-weight:600;margin-bottom:6px">Effective Date <span style="color:#d33">*</span></label>
      <input name="effectiveDate" value="%s" style="width:100%%;padding:10px;border:1px solid #c4ccd6;border-radius:8px">
      <label style="display:block;font-weight:600;margin:16px 0 6px">Time Zone <span style="color:#d33">*</span></label>
      <input name="timeZone" value="%s" style="width:100%%;padding:10px;border:1px solid #c4ccd6;border-radius:8px">
      <p style="color:#888;font-size:13px;margin-top:14px">To bind an orchestration to the
        <b>Service</b> step, use <b>Configure Orchestrations</b> on the BP page.</p>
      <div style="margin-top:20px;display:flex;gap:10px">
        <button class="btn pri" type="submit">OK</button>
        <a class="btn" href="/tenant/bp/%s">Cancel</a>
      </div>
    </form>""" % (esc(bp["effectiveDate"]), esc(bp["timeZone"]), bp_id)
    return wd.html_resp(wd.layout("Edit Business Process Definition", "", body, banner=False))


# ===========================================================================
# Change My Home Contact Information  (triggers the BP -> orchestration fires)
# ===========================================================================
@app.route("/tenant/task/change-home-contact/<emp_id>", methods=["GET", "POST"])
def change_home_contact(emp_id):
    w = worker(emp_id)
    d = load()
    bp = d["bps"]["home_contact_change"]

    if request.method == "POST":
        result_html = ""
        cur = bp.get("orchestration")
        if not cur:
            result_html = ("<div style='background:#fff3cd;border:1px solid #ffe69c;border-radius:8px;"
                           "padding:12px 16px'>Contact change submitted. No Orchestration Service is "
                           "configured on this BP, so nothing fired. Configure one via "
                           "<a href='/tenant/bp/home_contact_change/configure-orchestration'>Configure Orchestrations</a>.</div>")
        else:
            res = run_orchestration(cur["appId"], cur["name"])
            now = datetime.datetime.now()
            lines = ""
            for e in res.get("trace", []):
                level = "INFO" if e.get("status") == "Completed" else "ERROR"
                d["logs"].insert(0, {
                    "date": now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
                    "level": level, "message": e.get("message", ""),
                    "orchId": cur["name"], "tenantAlias": TENANT_ALIAS,
                    "bp": bp["name"], "ref": e.get("step", "")})
                lines += ("<tr><td>%s</td><td><span style='background:#1e6fd6;color:#fff;"
                          "padding:2px 8px;border-radius:4px;font-size:11px'>%s</span></td>"
                          "<td>&lt;LogStep&gt; %s</td></tr>" % (
                              e.get("step", ""), level, esc(e.get("message", ""))))
            save(d)
            result_html = ("<div style='background:#e8f5e9;border:1px solid #b6dcb9;border-radius:8px;"
                           "padding:12px 16px;margin-bottom:16px'>&#10003; Contact change submitted. "
                           "Business process fired <b>%s</b> (%s).</div>"
                           "<div class='wd-grid'><table><tr><th>Step</th><th>Level</th><th>Message</th></tr>"
                           "%s</table></div>"
                           "<p style='margin-top:14px'><a class='btn' href='/tenant/bp/logs'>View Process Run Logs &#8594;</a></p>"
                           % (esc(cur["name"]), esc(res.get("status", "")), lines))
        body = BANNER % ("Change My Home Contact Information", esc(w.get("Worker", ""))) + \
            "<div class='card'>" + result_html + "</div>"
        return wd.html_resp(wd.layout("Change Home Contact", "", body, banner=False))

    cur = bp.get("orchestration")
    note = ("<p style='color:#666;font-size:13px'>Submitting fires the bound BP orchestration: "
            "<b>%s</b>.</p>" % esc(cur["name"])) if cur else (
        "<p style='color:#b8860b;font-size:13px'>No orchestration bound yet. "
        "<a href='/tenant/bp/home_contact_change/configure-orchestration'>Configure one</a> to see it fire.</p>")
    body = BANNER % ("Change My Home Contact Information", esc(w.get("Worker", ""))) + """
    <form method="POST" class="card" style="max-width:640px">
      <h3>Phone</h3>
      <label style="display:block;margin:8px 0 4px">Phone Type</label>
      <select style="padding:9px;border:1px solid #c4ccd6;border-radius:8px"><option>Mobile</option><option>Landline</option></select>
      <label style="display:block;margin:12px 0 4px">Phone Number</label>
      <input value="+1 415-333-4567" style="width:100%%;padding:9px;border:1px solid #c4ccd6;border-radius:8px">
      <label style="display:flex;align-items:center;gap:8px;margin:12px 0"><input type="checkbox" checked> Primary</label>
      <h3 style="margin-top:20px">Visibility</h3>
      <select style="padding:9px;border:1px solid #c4ccd6;border-radius:8px"><option>Private</option><option>Public</option></select>
      %s
      <div style="margin-top:22px;display:flex;gap:10px">
        <button class="btn pri" type="submit">Submit</button>
        <a class="btn" href="/tenant/bp/home_contact_change">Cancel</a>
      </div>
    </form>""" % note
    return wd.html_resp(wd.layout("Change Home Contact", "", body, banner=False))


# ===========================================================================
# Process Run Logs  (wd_level / wd_message / wd_orch_id / wd_tenant_alias)
# ===========================================================================
@app.route("/tenant/bp/logs")
def bp_logs():
    d = load()
    logs = d.get("logs", [])
    rows = ""
    for L in logs[:50]:
        badge = "#1e6fd6" if L["level"] == "INFO" else "#d33"
        rows += ("<tr><td style='white-space:nowrap'>%s</td>"
                 "<td><span style='background:%s;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px'>%s</span></td>"
                 "<td>&lt;LogStep&gt; <b>%s</b> [tenant-alias=%s] [orchId=%s]</td>"
                 "<td>%s</td><td>%s</td></tr>" % (
                     esc(L["date"]), badge, esc(L["level"]), esc(L["message"]),
                     esc(L["tenantAlias"]), esc(L["orchId"]), esc(L["orchId"]), esc(L["tenantAlias"])))
    if not rows:
        rows = ("<tr><td colspan='5' style='padding:30px;text-align:center;color:#888'>No run logs yet. "
                "Trigger a BP via <a href='/tenant/task/change-home-contact/21001'>Change My Home Contact</a>.</td></tr>")
    body = BANNER % ("Business Process Run Logs", "%d entries" % len(logs)) + """
    <div class="card">
      <div style="display:flex;align-items:center;gap:14px;margin-bottom:12px">
        <input placeholder="Search" style="flex:1;padding:9px;border:1px solid #c4ccd6;border-radius:8px">
        <span style="color:#666;font-size:13px">Auto-Refresh</span>
        <a class="btn" href="/tenant/bp/logs">&#8635; Refresh</a>
      </div>
      <div class="wd-grid"><table>
        <tr><th>Date</th><th>wd_level</th><th>wd_message</th><th>wd_orch_id</th><th>wd_tenant_alias</th></tr>
        %s
      </table></div>
    </div>""" % rows
    return wd.html_resp(wd.layout("Business Process Run Logs", "", body, banner=False))
