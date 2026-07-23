"""
workday_ui.py - Workday-style UI on top of the mock tenant.

Run THIS instead of mock_workday_server.py (it includes all the API routes):
    python workday_ui.py
Open: http://127.0.0.1:8443

Type a task in the search bar (e.g. "create calc") -> pick the task ->
it opens in a new tab, like the real tenant:
  - Create Calculated Field   (saves to calculated_fields.json)
  - Create Custom Report      (saves to report_definitions.json, Enable As Web Service)
  - Create EIB                (inbound: upload CSV -> Request_One_Time_Payment load)
  - View Custom Report        (run any report as a table)
  - Integration Events        (what the inbound loads have written)
"""

import io
import csv
import json
import os
import re

EIB_SCHEDULES = []

from flask import request, Response, redirect

import mock_workday_server as mws
from mock_workday_server import app

TENANT = "SUPER_TENANT"

TASKS = [
    {"name": "Workday Studio",          "url": "/task/workday-studio"},
    {"name": "Create Calculated Field", "url": "/task/create-calculated-field"},
    {"name": "Create Custom Report",    "url": "/task/create-custom-report"},
    {"name": "Create EIB",              "url": "/task/create-eib"},
    {"name": "Create Integration System", "url": "/task/create-integration-system"},
    {"name": "View Integration System",   "url": "/task/view-integration-system"},
    {"name": "Launch Integration",        "url": "/task/launch-integration"},
    {"name": "Configure Integration Maps",  "url": "/task/configure-integration-maps"},
    {"name": "Create Integration System User", "url": "/task/create-isu"},
    {"name": "Create Security Group",       "url": "/task/create-security-group"},
    {"name": "Maintain Domain Permissions", "url": "/task/maintain-domain-permissions"},
    {"name": "Activate Pending Security Policy Changes", "url": "/task/activate-security-changes"},
    {"name": "Security Overview",           "url": "/task/security-overview"},
    {"name": "View Custom Report",      "url": "/task/view-report"},
    {"name": "View Calculated Field",   "url": "/task/view-calculated-field"},
    {"name": "Integration Events",      "url": "/task/integration-events"},
    {"name": "All Workers",             "url": "/task/all-workers"},
]

BASE_FIELDS = ["Employee_ID", "First_Name", "Last_Name", "Email",
               "Hire_Date", "Org", "Active"]

# Workday-style interactive report grid (clickable headers: sort + filter)
GRID_CSS = """<style>
.wd-grid table{border-collapse:collapse;width:100%;font-size:13px}
.wd-grid th{background:#fff;border-bottom:2px solid #2E6DA4;text-align:left;
  padding:8px 10px;color:#2E6DA4;font-weight:700;white-space:nowrap;
  cursor:pointer;position:relative;user-select:none}
.wd-grid th:hover{background:#F0F6FC}
.wd-grid td{border-bottom:1px solid #E6E8EB;padding:7px 10px;white-space:nowrap}
.wd-grid tr:nth-child(even) td{background:#FAFBFC}
.wd-grid .thsort{margin-left:4px;font-size:11px}
.wd-grid .thcaret{color:#9AA7B4;font-size:10px;margin-left:6px}
.wd-grid .thfilt{color:#0a7d0a;margin-left:4px;font-size:11px}
.wd-count{font-size:13px;color:#666;margin:4px 0 8px}
.thmenu{position:absolute;z-index:1000;background:#fff;border:1px solid #B9C2CC;
  border-radius:6px;box-shadow:0 8px 22px rgba(0,0,0,.20);min-width:240px;
  padding:6px 0;font-size:13px}
.thmenu .mi{padding:9px 14px;cursor:pointer;display:flex;align-items:center;gap:8px}
.thmenu .mi:hover{background:#EAF3FB}
.thmenu .sep{border-top:1px solid #E6E8EB;margin:6px 0}
.thmenu .flt{padding:4px 14px}
.thmenu .flt b{color:#555;font-size:12px}
.thmenu select{width:100%;padding:6px;margin-top:5px;border:1px solid #C7CDD4;
  border-radius:4px;background:#fff}
.thmenu .fbtn{margin:8px 14px 6px;display:block;width:calc(100% - 28px);
  background:#F0A01E;color:#fff;border:none;border-radius:16px;padding:8px;
  font-weight:700;cursor:pointer}
.wd-grid th.grp{text-align:center;background:#F0F6FC;border-bottom:1px solid #B9C2CC;
  color:#2E6DA4;cursor:default}
.wd-grid th.grp:hover{background:#F0F6FC}
.wd-grid th.grpblank{background:#fff;border-bottom:none;cursor:default;padding:0}
.wd-grid th.grpblank:hover{background:#fff}
.wd-grid td{vertical-align:top}
.wd-grid td br+*{margin-top:2px}
</style>"""

GRID_JS = """<script>
function initWdGrid(tid){
  const tbl=document.getElementById(tid);
  const cnt=document.getElementById(tid+'-count');
  const ths=tbl.tHead.rows[tbl.tHead.rows.length-1].cells;
  const filters={}; let menu=null;
  const allRows=()=>Array.from(tbl.tBodies[0].rows);
  const num=v=>v.replace(/[$,%\\s]/g,'');
  function vis(){return allRows().filter(r=>r.style.display!=='none').length;}
  function updCount(){if(cnt)cnt.textContent=vis()+' items';}
  function applyFilters(){
    allRows().forEach(r=>{
      let show=true;
      for(const c in filters){
        if(((r.cells[c].textContent||'').trim())!==filters[c]){show=false;break;}
      }
      r.style.display=show?'':'none';
    });
    updCount();
  }
  function sortBy(ci,dir){
    const body=tbl.tBodies[0], rs=allRows();
    const isNum=rs.every(r=>{const t=num((r.cells[ci].textContent||'').trim());return t===''||!isNaN(Number(t));});
    rs.sort((a,b)=>{
      let x=(a.cells[ci].textContent||'').trim(), y=(b.cells[ci].textContent||'').trim();
      if(isNum){return (dir==='asc'?1:-1)*((Number(num(x))||0)-(Number(num(y))||0));}
      return (dir==='asc'?1:-1)*x.localeCompare(y);
    });
    rs.forEach(r=>body.appendChild(r));
    for(const t of ths){const s=t.querySelector('.thsort');if(s)s.textContent='';}
    ths[ci].querySelector('.thsort').textContent=dir==='asc'?'\\u25B2':'\\u25BC';
  }
  function distinct(ci){
    const s=new Set();allRows().forEach(r=>s.add((r.cells[ci].textContent||'').trim()));
    return Array.from(s).sort();
  }
  function closeMenu(){if(menu){menu.remove();menu=null;}}
  function openMenu(ci,th){
    closeMenu();
    const opts=distinct(ci).map(v=>'<option>'+v.replace(/</g,'&lt;').replace(/"/g,'&quot;')+'</option>').join('');
    menu=document.createElement('div');menu.className='thmenu';
    menu.innerHTML=
      '<div class="mi" data-a="asc">\\u2191 Sort Ascending</div>'+
      '<div class="mi" data-a="desc">\\u2193 Sort Descending</div>'+
      '<div class="mi" data-a="rsort">\\u2715 Remove Sort</div>'+
      '<div class="sep"></div>'+
      '<div class="flt"><b>Filter</b><select id="fltsel">'+
        '<option value="">select one</option>'+opts+'</select></div>'+
      '<button class="fbtn" data-a="filter">Filter</button>'+
      '<div class="mi" data-a="clear">\\u2715 Clear Filter</div>';
    document.body.appendChild(menu);
    const r=th.getBoundingClientRect();
    menu.style.left=(window.scrollX+r.left)+'px';
    menu.style.top=(window.scrollY+r.bottom+2)+'px';
    if(filters[ci]!==undefined){const sel=menu.querySelector('#fltsel');sel.value=filters[ci];}
    menu.addEventListener('click',e=>{
      e.stopPropagation();
      const a=e.target.closest('[data-a]'); if(!a) return;
      const act=a.dataset.a;
      if(act==='asc')sortBy(ci,'asc');
      else if(act==='desc')sortBy(ci,'desc');
      else if(act==='rsort'){const s=ths[ci].querySelector('.thsort');if(s)s.textContent='';}
      else if(act==='filter'){
        const v=menu.querySelector('#fltsel').value;
        if(v){filters[ci]=v;}else{delete filters[ci];}
        applyFilters();
        ths[ci].querySelector('.thfilt').textContent=filters[ci]!==undefined?'\\u25BC':'';
      } else if(act==='clear'){
        delete filters[ci];applyFilters();
        ths[ci].querySelector('.thfilt').textContent='';
      }
      closeMenu();
    });
  }
  Array.from(ths).forEach((th,ci)=>th.addEventListener('click',e=>{e.stopPropagation();openMenu(ci,th);}));
  document.addEventListener('click',closeMenu);
  updCount();
}
</script>"""


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
STYLE = """
<style>
  * { box-sizing: border-box; margin: 0; }
  body { font-family: 'Segoe UI', Roboto, Arial, sans-serif; background:#f4f5f7; color:#333; }
  .topbar { background:#fff; display:flex; align-items:center; gap:18px;
            padding:10px 22px; border-bottom:1px solid #e3e3e3; }
  .wlogo { width:36px; height:36px; border-radius:50%; background:#fff;
           border:3px solid #f5a623; color:#0b6fd6; font-weight:700;
           display:flex; align-items:center; justify-content:center; font-size:20px; }
  .searchwrap { position:relative; flex:1; max-width:640px; }
  .search { width:100%; padding:10px 14px 10px 38px; border:1px solid #c9c9c9;
            border-radius:22px; font-size:15px; outline:none; }
  .search:focus { border-color:#0b6fd6; }
  .mag { position:absolute; left:13px; top:9px; color:#888; }
  .results { position:absolute; top:44px; left:0; right:0; background:#fff;
             border:1px solid #d5d5d5; border-radius:8px; box-shadow:0 4px 14px rgba(0,0,0,.12);
             display:none; z-index:10; overflow:hidden; }
  .results a { display:block; padding:11px 16px; text-decoration:none; color:#222; font-size:14px; }
  .results a:hover { background:#eaf2fc; }
  .results .hint { padding:6px 16px; font-size:11px; color:#999; border-top:1px solid #eee; }
  .banner { background:#0b6fd6; color:#fff; padding:34px 48px; }
  .banner h1 { font-weight:600; font-size:30px; }
  .banner .sub { opacity:.85; margin-top:6px; font-size:14px; }
  .page { padding:30px 48px; max-width:1080px; }
  .card { background:#fff; border:1px solid #e4e4e4; border-radius:10px;
          padding:26px 30px; margin-bottom:22px; }
  .card h2 { font-size:17px; font-weight:600; color:#444; margin-bottom:18px; }
  label { display:block; font-size:13px; font-weight:600; color:#555; margin:14px 0 5px; }
  label .req { color:#d40e0e; }
  input[type=text], select, textarea {
      width:100%; max-width:520px; padding:9px 12px; border:1px solid #c9c9c9;
      border-radius:6px; font-size:14px; font-family:inherit; }
  textarea { font-family:Consolas, monospace; font-size:13px; max-width:680px; }
  .btn { display:inline-block; border:none; cursor:pointer; font-size:15px;
         font-weight:600; padding:11px 34px; border-radius:24px; text-decoration:none; }
  .btn-ok { background:#f5a623; color:#fff; }
  .btn-ok:hover { background:#e2961a; }
  .btn-cancel { background:#fff; color:#444; border:1px solid #c9c9c9; margin-left:10px; }
  .btnrow { margin-top:26px; }
  table { border-collapse:collapse; width:100%; font-size:13px; }
  th { background:#0b6fd6; color:#fff; text-align:left; padding:8px 10px; }
  td { border-bottom:1px solid #e8e8e8; padding:7px 10px; }
  tr:nth-child(even) td { background:#f8fafc; }
  .ok-banner { background:#e6f4e6; border:1px solid #9fd49f; color:#256d25;
               padding:12px 16px; border-radius:8px; margin-bottom:18px; font-size:14px; }
  .err-banner { background:#fdebea; border:1px solid #f0a9a4; color:#a32018;
                padding:12px 16px; border-radius:8px; margin-bottom:18px; font-size:14px; }
  .apps { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:14px; }
  .app { background:#fff; border:1px solid #e4e4e4; border-radius:10px; padding:18px;
         text-align:center; text-decoration:none; color:#333; font-size:13px; }
  .app:hover { border-color:#0b6fd6; }
  .app .ic { font-size:26px; margin-bottom:8px; }
  code { background:#f1f3f5; padding:2px 6px; border-radius:4px; font-size:12px; }
  .checks label { display:inline-block; font-weight:400; margin:4px 14px 4px 0; }
</style>
"""

SEARCH_JS = """
<script>
const TASKS = %s;
const inp = document.getElementById('q');
const box = document.getElementById('results');
inp.addEventListener('input', () => {
  const q = inp.value.trim().toLowerCase();
  if (!q) { box.style.display = 'none'; return; }
  const hits = TASKS.filter(t => t.name.toLowerCase().includes(q));
  if (!hits.length) { box.style.display = 'none'; return; }
  box.innerHTML = hits.map(t =>
      `<a href="${t.url}" target="_blank">${t.name}</a>`).join('') +
      `<div class="hint">Opens in a new tab - like the real tenant</div>`;
  box.style.display = 'block';
});
document.addEventListener('click', e => {
  if (!e.target.closest('.searchwrap')) box.style.display = 'none';
});
</script>
""" % json.dumps(TASKS)


def layout(title, banner_sub, body, banner=True):
    head = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - Workday Mock</title>{STYLE}</head><body>
<div class="topbar">
  <div class="wlogo">W</div>
  <div class="searchwrap">
    <span class="mag">&#128269;</span>
    <input id="q" class="search" placeholder="Search for a task, e.g. create calculated field" autocomplete="off">
    <div id="results" class="results"></div>
  </div>
</div>"""
    ban = f"""<div class="banner"><h1>{title}</h1>
<div class="sub">{banner_sub}</div></div>""" if banner else ""
    return head + ban + f'<div class="page">{body}</div>' + SEARCH_JS + "</body></html>"


def html_resp(s):
    return Response(s, mimetype="text/html")


def persist(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------
@app.route("/home")
def home():
    apps = "".join(
        f'<a class="app" href="{t["url"]}" target="_blank">'
        f'<div class="ic">{ic}</div>{t["name"]}</a>'
        for t, ic in zip(TASKS, (["&#129518;", "&#128202;", "&#128260;",
                                  "&#128279;", "&#128269;", "&#128640;",
                                  "&#128196;", "&#128203;", "&#128101;",
                                  "&#128272;", "&#128737;", "&#9989;",
                                  "&#128065;"] * 2)))
    body = f"""
<div class="card"><h2>Welcome, Vasanth</h2>
<p style="font-size:14px;color:#666">This is your local mock tenant
(<code>{TENANT}</code>). Type a task in the search bar above - try
<b>create calc</b> or <b>create eib</b> - and pick a result to open it in a
new tab.</p></div>
<div class="card"><h2>Applications</h2><div class="apps">{apps}</div></div>"""
    return html_resp(layout("Home", f"Mock tenant: {TENANT}", body, banner=False))


@app.route("/api/tasks")
def api_tasks():
    q = request.args.get("q", "").lower()
    return Response(json.dumps([t for t in TASKS if q in t["name"].lower()]),
                    mimetype="application/json")


# ---------------------------------------------------------------------------
# Create Calculated Field
# ---------------------------------------------------------------------------
FUNCTION_TEMPLATES = {
    "Text Constant": {"value": "MY_CONSTANT"},
    "Concatenate Text": {"parts": [{"field": "First_Name"}, {"text": " "},
                                   {"field": "Last_Name"}]},
    "Substring Text": {"source": "Employee_ID", "start": 3, "length": 3},
    "Format Text": {"template": "{Last_Name}, {First_Name}", "case": "upper"},
    "Lookup Related Value": {"related": "Manager", "return_field": "Name"},
    "Evaluate Expression": {"field_type": "Text", "default": "N",
                            "conditions": [
                                {"field": "Active", "op": "equal to",
                                 "value": "1", "return": "A"}]},
    "True/False Condition": {"condition_field": "Org", "operator": "equals",
                             "value": "Finance"},
    "Arithmetic Calculation": {"operation": "multiply",
                               "operands": [{"field": "P_Tenure_Years"},
                                            {"value": 100}]},
    "Date Difference": {"source": "Hire_Date", "unit": "years"},
    "Increment or Decrement Date": {"source": "Hire_Date",
                                    "increment": {"years": 1}},
    "Build Date": {"year": {"from_field": "Hire_Date", "part": "year"},
                   "month": 1, "day": 1},
    "Count Related Instance": {"source": "Dependents"},
    "Sum Related Instance": {"source": "Payments", "value_field": "Amount"},
    "Extract Multi-Instance": {"source": "Dependents", "operation_type": "Subset",
                               "where": {"field": "Relationship",
                                         "operator": "equals", "equals": "Child"},
                               "return_field": "Name", "delimiter": ", "},
    "Extract Single Instance": {"source": "Dependents",
                                "operation_type": "Subset",
                                "where": {"field": "Relationship",
                                          "operator": "equals",
                                          "equals": "Spouse"},
                                "return_field": "Name"},
    "Numeric Constant": {"value": 100},
    "Date Constant": {"value": "2026-12-31"},
    "Text Length": {"source": "Last_Name"},
    "Convert Text to Number": {"source": "Base_Salary"},
    "Format Number": {"source": "Base_Salary", "decimals": 2,
                      "thousands": True, "prefix": "$"},
    "Format Date": {"source": "Hire_Date", "format": "MM/dd/yyyy"},
    "Convert Currency": {"source": "Base_Salary", "to": "INR",
                         "rates": {"INR": 83.2, "EUR": 0.92}},
    "Lookup Range Band": {"source": "P_Tenure_Years",
                          "bands": [{"min": 0, "max": 2, "value": "0-2"},
                                    {"min": 3, "max": 5, "value": "3-5"},
                                    {"min": 6, "max": 99, "value": "6+"}],
                          "default": "Unknown"},
    "Lookup Translated Value": {"source": "Org",
                                "translations": {"Finance": "Finanzas"}},
    "Aggregate Related Instances": {"source": "Dependents",
                                    "value_field": "Name", "delimiter": ", "},
}


RELATED_BO = {"Payments": "Payment", "Benefits": "Benefit Enrollment",
              "Dependents": "Dependent", "Manager": "Manager",
              "Emergency_Contacts": "Emergency Contact",
              "Position": "Position", "Compensation": "Compensation",
              "Contact_Information": "Contact Information",
              "Job_Position_Details": "Job/Position Details",
              "Payroll_Pay_Group_Assignment": "Pay Group Assignment"}


@app.route("/task/create-calculated-field", methods=["GET", "POST"])
def create_calc_field():
    msg = ""
    if request.method == "POST":
        name = request.form.get("field_name", "").strip()
        fn = request.form.get("function", "")
        try:
            params = json.loads(request.form.get("params", "{}"))
            if not name:
                raise ValueError("Field Name is required.")
            if any(c["field_name"] == name for c in mws.CALC_FIELDS):
                raise ValueError(f"Field '{name}' already exists.")
            defn = {"field_name": name, "function": fn, **params}
            mws.CALC_FIELDS.append(defn)
            persist("calculated_fields.json", {"Worker": mws.CALC_FIELDS})
            rel_bo = RELATED_BO.get(params.get("source", ""), "")
            rel_html = (f"<br>Related Field: <b>{params.get('source')}</b>"
                        f" &nbsp;|&nbsp; Related Business Object: "
                        f"<b>{rel_bo}</b>" if rel_bo else "")
            msg = (f'<div class="ok-banner">Created calculated field '
                   f'<b>{name}</b> ({fn}).<br>Business Object: <b>Worker</b>'
                   f'{rel_html}<br>Add it to a report in '
                   f'<a href="/task/create-custom-report" target="_blank">'
                   f'Create Custom Report</a>.</div>')
        except (ValueError, json.JSONDecodeError) as e:
            msg = f'<div class="err-banner">Validation error occurred. {e}</div>'

    opts = "".join(f'<option value="{f}">{f}</option>' for f in FUNCTION_TEMPLATES)
    existing = ", ".join(c["field_name"] for c in mws.CALC_FIELDS) or "(none)"
    cf_names = [c["field_name"] for c in mws.CALC_FIELDS]
    cf_datalist = "".join(f'<option value="{n}">' for n in cf_names + list(BASE_FIELDS))
    body = f"""{msg}
<form method="post" id="cfform"><div class="card">
  <label>Field Name <span class="req">*</span></label>
  <input type="text" name="field_name" placeholder="P_My_Field">
  <label>Business Object <span class="req">*</span></label>
  <input type="text" value="Worker" disabled>
  <label>Function <span class="req">*</span></label>
  <select name="function" id="fn">{opts}</select>
  <div id="relbo" style="font-size:13px;color:#555;margin:6px 0;
       padding:6px 10px;background:#f0f6fc;border-radius:4px;display:none">
  </div>
  <div id="jsonEditor">
  <label>Function Parameters (JSON)</label>
  <textarea name="params" id="params" rows="7"></textarea>
  <p style="font-size:12px;color:#888;margin-top:6px">Tip: parameters
  pre-fill when you pick a function. Edit values to suit. Existing fields
  you can reference: {existing}</p>
  </div>

  <div id="eeBuilder" style="display:none">
    <p style="font-size:13px;color:#666;margin:0 0 10px">Evaluates a series of
      conditions and returns the value associated with the first condition that
      is true. If no conditions are true, returns the default value.</p>
    <label>Field Type <span class="req">*</span></label><br>
    <select id="ee_ftype" style="max-width:240px">
      <option>Text</option><option>Date</option><option>Date Time</option>
      <option>DateTimeZone</option><option>Time</option><option>Numeric</option>
      <option>Currency</option><option>Boolean</option></select>
    <label>Default Value <span class="req">*</span></label><br>
    <input id="ee_default" list="cfsugg" style="max-width:340px"
      placeholder="a calc field (e.g. PS_Text constant -N) or a literal">
    <div style="margin:12px 0 6px">
      <button type="button" class="addbtn" onclick="addEE()">+</button>
      <span style="margin-left:8px;color:#666;font-size:13px">
        <span id="eecount">0</span> items</span>
    </div>
    <table class="colgrid"><thead><tr>
      <th style="width:64px"></th><th style="width:64px">Order</th>
      <th>*Condition</th><th style="width:230px">Comparison Value?</th>
      <th>*Return Value If Condition is True</th></tr></thead>
      <tbody id="eebody"></tbody></table>
    <p style="font-size:12px;color:#888;margin-top:8px"><b>Condition</b>:
      reference a True/False calc field. Or tick <b>Comparison Value?</b> to
      compare a field inline (pick an Operator + value). <b>Return Value</b>:
      a calc field (e.g. a Text Constant) or a literal.</p>
  </div>
  <datalist id="cfsugg">{cf_datalist}</datalist>
  <div class="btnrow">
    <button class="btn btn-ok" type="submit">OK</button>
    <a class="btn btn-cancel" href="/home">Cancel</a>
  </div>
</div></form>
<script>
const T = {json.dumps(FUNCTION_TEMPLATES)};
const RB = {json.dumps(RELATED_BO)};
const OPS_EE = {json.dumps(REPORT_OPERATORS)};
const fn = document.getElementById('fn'), pa = document.getElementById('params');
const rb = document.getElementById('relbo');
const jsonEd = document.getElementById('jsonEditor');
const eeB = document.getElementById('eeBuilder');
function esc(s){{return String(s==null?'':s).replace(/"/g,'&quot;');}}
function showRelBo() {{
  let src = ""; try {{ const o = JSON.parse(pa.value); src = o.source || o.related || ""; }} catch(e) {{}}
  if (RB[src]) {{
    rb.style.display = 'block';
    rb.innerHTML = 'Related Field: <b>' + src + '</b> &nbsp;|&nbsp; ' +
      'Related Business Object: <b>' + RB[src] + '</b>' +
      ' <span style="color:#999">(multi-instance - traversed from Worker)</span>';
  }} else if (src) {{
    rb.style.display = 'block';
    rb.innerHTML = 'Source: <b>' + src +
      '</b> &nbsp;|&nbsp; Business Object: <b>Worker</b> (primary - no traversal)';
  }} else {{ rb.style.display = 'none'; }}
}}
function eeOp(v){{return '<select class="ee_op">'+OPS_EE.map(o=>'<option '+(o===v?'selected':'')+'>'+o+'</option>').join('')+'</select>';}}
function eeRow(d){{
  d=d||{{}}; const inline=!!(d.op&&d.field); const tr=document.createElement('tr');
  tr.innerHTML=
   '<td style="white-space:nowrap">'+
     '<button type="button" class="addbtn" onclick="addEEAfter(this)">+</button> '+
     '<button type="button" class="rowbtn" onclick="delEE(this)">&#8722;</button></td>'+
   '<td style="white-space:nowrap">'+
     '<button type="button" class="ordbtn" onclick="eeMove(this,-1)">&#9650;</button>'+
     '<button type="button" class="ordbtn" onclick="eeMove(this,1)">&#9660;</button></td>'+
   '<td><input class="ee_cond" list="cfsugg" value="'+esc(inline?(d.field||''):(d.condition||''))+'" placeholder="True/False calc field (or field if comparing)"></td>'+
   '<td style="text-align:center"><input type="checkbox" class="ee_cv" '+(inline?'checked':'')+' onchange="eeToggle(this)"> '+
     '<span class="ee_cmp" style="display:'+(inline?'inline':'none')+'">'+eeOp(d.op)+' <input class="ee_val" value="'+esc(d.value||'')+'" placeholder="value" style="width:70px"></span></td>'+
   '<td><input class="ee_ret" list="cfsugg" value="'+esc(d.return||'')+'" placeholder="calc field or literal"></td>';
  return tr;
}}
function addEEAfter(btn){{btn.closest('tr').after(eeRow({{}}));eeCount();}}
function delEE(btn){{btn.closest('tr').remove();eeCount();}}
function eeToggle(cb){{cb.parentNode.querySelector('.ee_cmp').style.display=cb.checked?'inline':'none';}}
function eeMove(btn,dir){{const tr=btn.closest('tr');if(dir<0&&tr.previousElementSibling)tr.parentNode.insertBefore(tr,tr.previousElementSibling);if(dir>0&&tr.nextElementSibling)tr.parentNode.insertBefore(tr.nextElementSibling,tr);}}
function eeCount(){{const el=document.getElementById('eecount');if(el)el.textContent=document.querySelectorAll('#eebody tr').length;}}
function addEE(){{document.getElementById('eebody').appendChild(eeRow({{}}));eeCount();}}
function eeSeed(t){{
  const b=document.getElementById('eebody'); b.innerHTML='';
  document.getElementById('ee_ftype').value=t.field_type||'Text';
  document.getElementById('ee_default').value=t.default||'';
  (t.conditions||[]).forEach(d=>b.appendChild(eeRow(d)));
  if(!b.children.length) b.appendChild(eeRow({{}}));
  eeCount();
}}
function eeSerialize(){{
  const conds=[];
  document.querySelectorAll('#eebody tr').forEach(tr=>{{
    const cond=tr.querySelector('.ee_cond').value.trim();
    const cv=tr.querySelector('.ee_cv').checked;
    const ret=tr.querySelector('.ee_ret').value.trim();
    if(!cond&&!ret) return;
    if(cv){{conds.push({{"field":cond,"op":tr.querySelector('.ee_op').value,"value":tr.querySelector('.ee_val').value.trim(),"return":ret}});}}
    else {{conds.push({{"condition":cond,"return":ret}});}}
  }});
  return {{"field_type":document.getElementById('ee_ftype').value,
          "default":document.getElementById('ee_default').value.trim(),
          "conditions":conds}};
}}
function isEE(){{return fn.value==='Evaluate Expression';}}
function fill() {{
  if(isEE()){{ jsonEd.style.display='none'; eeB.style.display='block'; rb.style.display='none'; eeSeed(T[fn.value]||{{}}); }}
  else {{ jsonEd.style.display='block'; eeB.style.display='none'; pa.value=JSON.stringify(T[fn.value],null,2); showRelBo(); }}
}}
fn.addEventListener('change', fill);
pa.addEventListener('input', showRelBo);
document.getElementById('cfform').addEventListener('submit', function(){{ if(isEE()) pa.value=JSON.stringify(eeSerialize()); }});
fill();
</script>"""
    return html_resp(layout("Create Calculated Field",
                            "Business Object: Worker", body))


@app.route("/task/view-calculated-field")
def view_calculated_field():
    """List all report calculated fields, each with View source / Edit."""
    rows = "".join(
        f'<tr><td><b>{c["field_name"]}</b></td><td>{c.get("function","")}</td>'
        f'<td>Worker</td>'
        f'<td><a href="/task/edit-calculated-field?name={c["field_name"]}">'
        f'&#9998; Edit</a></td></tr>'
        for c in mws.CALC_FIELDS)
    body = f"""<div class="card"><h2>Calculated Fields - {len(mws.CALC_FIELDS)} items</h2>
<p style="font-size:13px;color:#666;margin-bottom:10px">Business Object: Worker.
Click Edit to change the function or its parameters.</p>
<table><tr><th>Field Name</th><th>Function</th><th>Business Object</th>
<th>Actions</th></tr>{rows}</table>
<p style="margin-top:12px"><a class="btn btn-ok"
   href="/task/create-calculated-field">+ Create Calculated Field</a></p>
</div>"""
    return html_resp(layout("View Calculated Field",
                            "All report calculated fields", body))


@app.route("/task/edit-calculated-field", methods=["GET", "POST"])
def edit_calculated_field():
    name = request.values.get("name", "")
    idx = next((i for i, c in enumerate(mws.CALC_FIELDS)
                if c["field_name"] == name), None)
    if idx is None:
        return html_resp(layout("Edit Calculated Field", "",
                                '<div class="err-banner">Calculated field not '
                                'found.</div>'))
    cf = mws.CALC_FIELDS[idx]
    msg = ""
    if request.method == "POST":
        fn = request.form.get("function", cf["function"])
        try:
            params = json.loads(request.form.get("params", "{}"))
            mws.CALC_FIELDS[idx] = {"field_name": name, "function": fn, **params}
            persist("calculated_fields.json", {"Worker": mws.CALC_FIELDS})
            cf = mws.CALC_FIELDS[idx]
            msg = (f'<div class="ok-banner">Saved changes to <b>{name}</b> '
                   f'({fn}).</div>')
        except (ValueError, json.JSONDecodeError) as e:
            msg = f'<div class="err-banner">Validation error occurred. {e}</div>'

    cur_params = {k: v for k, v in cf.items()
                  if k not in ("field_name", "function")}
    opts = "".join(
        f'<option value="{f}" {"selected" if f==cf["function"] else ""}>{f}</option>'
        for f in FUNCTION_TEMPLATES)
    body = f"""{msg}
<form method="post"><div class="card">
  <input type="hidden" name="name" value="{name}">
  <label>Field Name</label>
  <input type="text" value="{name}" disabled>
  <label>Business Object</label>
  <input type="text" value="Worker" disabled>
  <label>Function <span class="req">*</span></label>
  <select name="function" id="fn">{opts}</select>
  <label>Function Parameters (JSON)</label>
  <textarea name="params" id="params" rows="9">{json.dumps(cur_params, indent=2)}</textarea>
  <p style="font-size:12px;color:#888;margin-top:6px">Changing the Function
  reloads its default parameters; edit values then press OK.</p>
  <div class="btnrow">
    <button class="btn btn-ok" type="submit">OK</button>
    <a class="btn btn-cancel" href="/task/view-calculated-field">Cancel</a>
  </div>
</div></form>
<script>
const T = {json.dumps(FUNCTION_TEMPLATES)};
const fn = document.getElementById('fn'), pa = document.getElementById('params');
let firstFn = fn.value;
fn.addEventListener('change', () => {{
  // only reset params when the function actually changes from the saved one
  if (fn.value !== firstFn) {{ pa.value = JSON.stringify(T[fn.value], null, 2); }}
}});
</script>"""
    return html_resp(layout(f"Edit Calculated Field - {name}",
                            "Business Object: Worker", body))


# ---------------------------------------------------------------------------
# Create Custom Report
# ---------------------------------------------------------------------------
def _report_form_fields(rpt=None):
    """Build the shared report form body (Create + Edit) - Workday-style tabs."""
    rpt = rpt or {}
    calc_names = [c["field_name"] for c in mws.CALC_FIELDS]
    worker_fields = BASE_FIELDS + ["Full_Name", "Total_Compensation",
                                   "Total_Base_Pay_Annualized", "Base_Salary",
                                   "Pay_Group", "Comp_Plan", "Currency",
                                   "Organization", "Date_of_Birth", "DOB", "Age",
                                   "Email_Primary", "Email_Secondary",
                                   "Address", "City", "State", "Postal_Code",
                                   "Phone_Home", "Phone_Business", "Phone_Work",
                                   "Spouse_Name", "Spouse_Age", "Child_Names",
                                   "Child_Ages", "Dependent_Count",
                                   "Dependent_Names", "Manager_Name",
                                   "Manager_Email", "Manager_Phone_Primary",
                                   "Manager_Phone_Secondary",
                                   "Emergency_Contact_Name",
                                   "Emergency_Contact_Relationship",
                                   "Emergency_Contact_Phone",
                                   "Emergency_Contact_Address"]
    related_fields = ["Name", "Relationship", "Age", "Date_of_Birth", "Gender",
                      "DOB", "Amount", "Type", "Date", "Plan", "Coverage",
                      "Employee_Cost", "Email", "Phone_Primary",
                      "Phone_Secondary", "Primary Work Email",
                      "Primary Work Phone", "Employee_ID",
                      "Emergency_Contact_Person.Name"]
    suggestions = sorted(set(worker_fields + calc_names + related_fields))
    datalist = "".join(f'<option value="{f}">' for f in suggestions)
    bos = ["Worker", "Manager", "Dependents", "Payments", "Benefits",
           "Emergency Contacts", "Position", "Compensation",
           "Contact Information", "Benefit Enrollment",
           "Job/Position Details", "Payroll/Pay Group Assignment"]

    # seed column rows: rich column_defs if present, else plain column list
    defs = rpt.get("column_defs")
    if not defs:
        defs = [{"field": c, "business_object": "Worker"}
                for c in rpt.get("columns", [])]
    if not defs:
        defs = [{"field": "Employee_ID", "business_object": "Worker"},
                {"field": "First_Name", "business_object": "Worker"},
                {"field": "Last_Name", "business_object": "Worker"}]

    flt = rpt.get("filter") or {}
    sub = rpt.get("subfilter") or {}
    srt = rpt.get("sort") or {}
    rtype = rpt.get("report_type", "Advanced")
    types = ["Simple", "Advanced", "Matrix", "Composite", "nBox",
             "Search", "Transposed", "Trending"]
    topts = "".join(f'<option {"selected" if t==rtype else ""}>{t}</option>'
                    for t in types)
    ds = rpt.get("data_source", "All Workers")
    ws_checked = "checked" if rpt.get("enable_as_web_service") else ""

    # 3 prompt slots
    all_cols = worker_fields + calc_names
    prompts = rpt.get("prompts", [])
    prompt_rows = ""
    for n in range(3):
        pr = prompts[n] if n < len(prompts) else {}
        pf = pr.get("field", "")
        sel_opts = '<option value=""></option>' + "".join(
            f'<option value="{f}" {"selected" if f==pf else ""}>{f}</option>'
            for f in all_cols)
        req = "checked" if pr.get("required") else ""
        prompt_rows += (
            f'<tr><td>Prompt {n+1}</td>'
            f'<td><select name="prompt_field_{n}">{sel_opts}</select></td>'
            f'<td style="text-align:center"><input type="checkbox" '
            f'name="prompt_req_{n}" {req}></td></tr>')

    sort_opts = '<option value=""></option>' + "".join(
        f'<option {"selected" if f==srt.get("field") else ""}>{f}</option>'
        for f in all_cols)
    dir_a = "selected" if srt.get("dir") == "asc" else ""
    dir_d = "selected" if srt.get("dir") == "desc" else ""

    rel_bos = ["Dependents", "Payments", "Benefits", "Manager",
               "Emergency Contacts", "Position", "Compensation",
               "Contact Information", "Benefit Enrollment",
               "Job/Position Details", "Payroll/Pay Group Assignment"]
    cur_sub_bo = sub.get("business_object", "")
    sub_bo_opts = '<option value=""></option>' + "".join(
        f'<option {"selected" if b == cur_sub_bo else ""}>{b}</option>'
        for b in rel_bos)

    return f"""{_REPORT_CSS}
  <label>Report Type <span class="req">*</span></label>
  <select name="report_type" id="rtype">{topts}</select>
  <label>Data Source <span class="req">*</span></label>
  <input type="text" name="data_source" value="{ds}">
  <p style="margin-top:8px;font-size:13px;color:#555"><b>Primary Business
   Object:</b> Worker &nbsp;<span style="color:#888">(per column you can also
   pick a related business object: Manager, Dependents, Payments, Benefits)</span></p>

  <h3 style="margin-top:14px">Additional Info</h3>
  <div class="rtabs">
    <span class="rtab active" data-t="cols" onclick="showTab('cols')">Columns</span>
    <span class="rtab" data-t="sort" onclick="showTab('sort')">Sort</span>
    <span class="rtab" data-t="filter" onclick="showTab('filter')">Filter</span>
    <span class="rtab" data-t="subfilter" onclick="showTab('subfilter')">Subfilter</span>
    <span class="rtab" data-t="prompts" onclick="showTab('prompts')">Prompts</span>
    <span class="rtab" data-t="output" onclick="showTab('output')">Output</span>
    <span class="rtab" data-t="share" onclick="showTab('share')">Share</span>
    <span class="rtab" data-t="advanced" onclick="showTab('advanced')">Advanced</span>
  </div>

  <div class="rpanel" id="p-cols">
    <div style="margin-bottom:10px">
      <button type="button" class="addbtn" onclick="addCol()"
        title="Add column">+</button>
      <span style="margin-left:8px;color:#666;font-size:13px">
        <span id="colcount">0</span> items</span>
    </div>
    <table class="colgrid">
      <thead><tr>
        <th style="width:96px"></th><th style="width:74px">Order</th>
        <th style="width:150px">*Business Object</th><th>Field</th>
        <th>Column Heading Override</th><th style="width:120px">Format</th>
        <th style="width:120px">Options</th>
      </tr></thead>
      <tbody id="colbody"></tbody>
    </table>
    <datalist id="fieldsugg">{datalist}</datalist>
    <h4 style="margin:16px 0 2px">Group Column Headings
      <span style="font-weight:400;color:#888;font-size:12px">(0 items)</span></h4>
    <p style="font-size:12px;color:#888;margin:0">Columns that share a related
      Business Object are clubbed under one group header in the output
      (e.g. Age and Name under <b>Dependents</b>).</p>
  </div>

  <div class="rpanel" id="p-sort" style="display:none">
    <label>Sort by field</label>
    <select name="sort_field" style="max-width:280px">{sort_opts}</select>
    <label>Direction</label>
    <select name="sort_dir" style="max-width:200px">
      <option value="">(none)</option>
      <option value="asc" {dir_a}>Ascending</option>
      <option value="desc" {dir_d}>Descending</option></select>
  </div>

  <div class="rpanel" id="p-filter" style="display:none">
    <h4 style="margin:4px 0 2px">Filter on Instances</h4>
    <p style="font-size:12px;color:#888;margin:0 0 8px">Filter conditions for
      filtering on instances &middot; <span id="fltcount">0</span> item(s)</p>
    <button type="button" class="addbtn" onclick="addFlt()" title="Add condition">+</button>
    <table class="colgrid"><thead><tr>
      <th style="width:64px"></th><th style="width:84px">And/Or</th>
      <th style="width:36px">(</th><th>*Field</th>
      <th style="width:210px">*Operator</th><th>Comparison Value</th>
      <th style="width:36px">)</th></tr></thead>
      <tbody id="fltbody"></tbody></table>

    <h4 style="margin:18px 0 2px">Filter on Aggregations</h4>
    <p style="font-size:12px;color:#888;margin:0 0 8px">Filter condition for
      filtering on aggregated values &middot; <span id="aggcount">0</span> item(s)</p>
    <button type="button" class="addbtn" onclick="addAgg()" title="Add aggregation">+</button>
    <table class="colgrid"><thead><tr>
      <th style="width:64px"></th><th style="width:84px">And/Or</th>
      <th style="width:150px">*Aggregation Function</th><th>Field</th>
      <th style="width:210px">*Operator</th><th>Value</th></tr></thead>
      <tbody id="aggbody"></tbody></table>
    <p style="font-size:12px;color:#888;margin-top:8px">Aggregation Field: a
      related business object for <b>Count</b> (e.g. <code>Dependents</code>),
      or <code>BO.attr</code> for Sum/Average/Min/Max
      (e.g. <code>Payments.Amount</code>).</p>
  </div>

  <div class="rpanel" id="p-subfilter" style="display:none">
    <h4 style="margin:4px 0">Sub Level Filter</h4>
    <label>Business Object <span class="req">*</span></label>
    <select name="subfilter_bo" style="max-width:240px">{sub_bo_opts}</select>
    <p style="font-size:12px;color:#888;margin:8px 0">Keeps only the related
      instances that match (e.g. <b>Dependents</b> where <b>Age less than 18</b>
      = children). This affects related-object columns and any count / aggregate
      over that object.</p>
    <button type="button" class="addbtn" onclick="addSub()" title="Add condition">+</button>
    <table class="colgrid"><thead><tr>
      <th style="width:64px"></th><th style="width:84px">And/Or</th>
      <th>*Field</th><th style="width:210px">*Operator</th>
      <th>Value</th></tr></thead>
      <tbody id="subbody"></tbody></table>
  </div>

  <div class="rpanel" id="p-prompts" style="display:none">
    <p style="font-size:13px;color:#888;margin-bottom:8px">A Required prompt
      becomes a mandatory launch parameter (asked at run time / RaaS / EIB).</p>
    <table class="grid" style="max-width:560px">
      <tr><th style="width:22%"></th><th>Prompt on Field</th>
          <th style="width:22%">Required</th></tr>
      {prompt_rows}
    </table>
  </div>

  <div class="rpanel" id="p-output" style="display:none">
    <p style="font-size:13px;color:#666">The report renders as an interactive
      grid (click a header to sort/filter). When <b>Enable As Web Service</b>
      is on (Advanced tab), the same data is available via RaaS as
      <code>?format=json</code>, <code>xml</code> or <code>csv</code>.</p>
  </div>

  <div class="rpanel" id="p-share" style="display:none">
    <p style="font-size:13px;color:#666">Sharing controls who can run the report.
      This local simulator runs single-user, so every report is visible to you.</p>
  </div>

  <div class="rpanel" id="p-advanced" style="display:none">
    <label><input type="checkbox" name="enable_ws" id="ws" {ws_checked}>
      Enable As Web Service
      <span style="font-weight:400;color:#888">(required for RaaS)</span></label>
    <p style="font-size:12px;color:#888;margin-top:8px">Only Advanced reports can
      be enabled as a web service.</p>
  </div>

  <script>window.BOS={json.dumps(bos)};window.COLDEFS={json.dumps(defs)};
  window.OPS={json.dumps(REPORT_OPERATORS)};window.FUNCS={json.dumps(AGG_FUNCTIONS)};
  window.FLT={json.dumps(rpt.get('filter_conditions') or [])};
  window.AGG={json.dumps(rpt.get('aggregation_filters') or [])};
  window.SUBF={json.dumps((rpt.get('subfilter') or {}).get('conditions') or [])};
  </script>"""


def _report_from_form(name):
    """Parse the report form into a report dict."""
    bos = request.form.getlist("col_bo")
    fields = request.form.getlist("col_field")
    headings = request.form.getlist("col_heading")
    formats = request.form.getlist("col_format")
    options = request.form.getlist("col_options")
    column_defs, columns = [], []
    for i, fld in enumerate(fields):
        fld = (fld or "").strip()
        if not fld:
            continue
        column_defs.append({
            "field": fld,
            "business_object": (bos[i] if i < len(bos) else "Worker"),
            "heading": (headings[i].strip() if i < len(headings) else ""),
            "format": (formats[i].strip() if i < len(formats) else ""),
            "options": (options[i].strip() if i < len(options) else ""),
        })
        columns.append(fld)

    # --- Filter on Instances (grid) ---
    f_fields = request.form.getlist("flt_field")
    f_ops = request.form.getlist("flt_op")
    f_vals = request.form.getlist("flt_value")
    f_aos = request.form.getlist("flt_andor")
    filter_conditions = []
    for i, fld in enumerate(f_fields):
        fld = (fld or "").strip()
        if not fld:
            continue
        filter_conditions.append({
            "field": fld,
            "op": (f_ops[i] if i < len(f_ops) else "equal to") or "equal to",
            "value": (f_vals[i].strip() if i < len(f_vals) else ""),
            "andor": (f_aos[i] if i < len(f_aos) else "And") or "And"})

    # --- Filter on Aggregations (grid) ---
    a_funcs = request.form.getlist("agg_func")
    a_flds = request.form.getlist("agg_field")
    a_ops = request.form.getlist("agg_op")
    a_vals = request.form.getlist("agg_value")
    a_aos = request.form.getlist("agg_andor")
    aggregation_filters = []
    for i, fld in enumerate(a_flds):
        fld = (fld or "").strip()
        if not fld:
            continue
        aggregation_filters.append({
            "func": (a_funcs[i] if i < len(a_funcs) else "Count") or "Count",
            "field": fld,
            "op": (a_ops[i] if i < len(a_ops) else "greater than") or "greater than",
            "value": (a_vals[i].strip() if i < len(a_vals) else ""),
            "andor": (a_aos[i] if i < len(a_aos) else "And") or "And"})

    # --- Sub Level Filter (subfilter on a related business object) ---
    sub_bo = request.form.get("subfilter_bo", "").strip()
    s_fields = request.form.getlist("sub_field")
    s_ops = request.form.getlist("sub_op")
    s_vals = request.form.getlist("sub_value")
    s_aos = request.form.getlist("sub_andor")
    sub_conds = []
    for i, fld in enumerate(s_fields):
        fld = (fld or "").strip()
        if not fld:
            continue
        sub_conds.append({
            "field": fld,
            "op": (s_ops[i] if i < len(s_ops) else "equal to") or "equal to",
            "value": (s_vals[i].strip() if i < len(s_vals) else ""),
            "andor": (s_aos[i] if i < len(s_aos) else "And") or "And"})
    subfilter = ({"business_object": sub_bo, "conditions": sub_conds}
                 if sub_bo and sub_conds else None)

    sort_field = request.form.get("sort_field", "").strip()
    sort_dir = request.form.get("sort_dir", "").strip()
    prompts = []
    for n in range(3):
        pf = request.form.get(f"prompt_field_{n}", "").strip()
        if pf:
            prompts.append({"name": pf, "field": pf,
                            "required": bool(request.form.get(f"prompt_req_{n}"))})
    return {
        "report_name": name,
        "report_type": request.form.get("report_type", "Advanced"),
        "data_source": request.form.get("data_source", "All Workers"),
        "columns": columns,
        "column_defs": column_defs,
        "filter_conditions": filter_conditions,
        "aggregation_filters": aggregation_filters,
        "subfilter": subfilter,
        "sort": ({"field": sort_field, "dir": sort_dir}
                 if sort_field and sort_dir else None),
        "prompts": prompts,
        "enable_as_web_service": request.form.get("enable_ws") == "on",
    }


# ---------------------------------------------------------------------------
# Report filter engine (instance filters, sub-level filter, aggregation filter)
# ---------------------------------------------------------------------------
REPORT_OPERATORS = ["equal to", "not equal to", "greater than",
                    "greater than or equal to", "less than",
                    "less than or equal to", "in the selection list",
                    "contains", "is empty", "is not empty"]
AGG_FUNCTIONS = ["Count", "Sum", "Average", "Minimum", "Maximum"]


def _rnum(x):
    try:
        return float(str(x).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return None


def _match_val(val, op, target):
    """Compare a value against a target using a Workday operator."""
    s = "" if val is None else str(val)
    t = "" if target is None else str(target)
    if op == "is empty":
        return s == ""
    if op == "is not empty":
        return s != ""
    if op == "in the selection list":
        return s in [x.strip() for x in t.split(",") if x.strip()]
    if op == "contains":
        return t.lower() in s.lower()
    nv, nt = _rnum(s), _rnum(t)
    if op == "greater than":
        return nv is not None and nt is not None and nv > nt
    if op == "greater than or equal to":
        return nv is not None and nt is not None and nv >= nt
    if op == "less than":
        return nv is not None and nt is not None and nv < nt
    if op == "less than or equal to":
        return nv is not None and nt is not None and nv <= nt
    if op == "not equal to":
        return (nv != nt) if (nv is not None and nt is not None) else (s.lower() != t.lower())
    # default: equal to
    return (nv == nt) if (nv is not None and nt is not None) else (s.lower() == t.lower())


def _combine(results, andors):
    """Combine row results left-to-right honoring per-row And/Or."""
    if not results:
        return True
    acc = results[0]
    for i in range(1, len(results)):
        ao = (andors[i] if i < len(andors) else "And") or "And"
        acc = (acc and results[i]) if ao == "And" else (acc or results[i])
    return acc


def _passes_instance(ctx, conds):
    """Filter on Instances: worker passes when its field values satisfy the
    condition rows. ctx is worker_context(worker)."""
    if not conds:
        return True
    res = [_match_val(ctx.get(c["field"], ""), c.get("op", "equal to"),
                      c.get("value", "")) for c in conds]
    return _combine(res, [c.get("andor", "And") for c in conds])


def _apply_subfilter(w, sub):
    """Sub Level Filter: keep only the related-object instances that match.
    Returns a shallow copy of the worker with the related list filtered, so
    related columns AND calc fields (counts/aggregates) honor the subfilter."""
    if not sub or not sub.get("business_object"):
        return w
    bo = sub["business_object"]
    if bo not in mws.RELATED_OBJECTS:
        return w
    key, card = mws.RELATED_OBJECTS[bo]
    conds = sub.get("conditions", [])
    if not conds:
        return w
    w2 = dict(w)
    items = w.get(key) or []

    def ok(it):
        res = [_match_val(it.get(c["field"], ""), c.get("op", "equal to"),
                          c.get("value", "")) for c in conds]
        return _combine(res, [c.get("andor", "And") for c in conds])

    if card == "multi":
        w2[key] = [it for it in items if ok(it)]
    return w2


def _agg_value(w, func, field):
    """Compute an aggregate for Filter on Aggregations. field can be a related
    business object name (Count) or 'BO.attr' (Sum/Average/Min/Max), or a
    numeric calc field."""
    bo, attr = (field.split(".", 1) + [None])[:2] if "." in field else (field, None)
    if bo in mws.RELATED_OBJECTS:
        key, _ = mws.RELATED_OBJECTS[bo]
        items = w.get(key) or []
        if func == "Count":
            return len(items)
        nums = [_rnum(it.get(attr)) for it in items if _rnum(it.get(attr)) is not None]
        if not nums:
            return 0
        return {"Sum": sum(nums), "Average": sum(nums) / len(nums),
                "Minimum": min(nums), "Maximum": max(nums)}.get(func, 0)
    ctx = mws.worker_context(w)
    return _rnum(ctx.get(field)) or 0


def _passes_agg(w, conds):
    """Filter on Aggregations: keep workers whose aggregate satisfies the rows."""
    if not conds:
        return True
    res = [_match_val(_agg_value(w, c.get("func", "Count"), c.get("field", "")),
                      c.get("op", "greater than"), c.get("value", ""))
           for c in conds]
    return _combine(res, [c.get("andor", "And") for c in conds])


_REPORT_CSS = """<style>
.rtabs{display:flex;flex-wrap:wrap;border-bottom:1px solid #d6dbe0;margin:10px 0 0}
.rtab{padding:8px 16px;cursor:pointer;font-size:14px;color:#555;
  border-bottom:3px solid transparent}
.rtab.active{color:#0875e1;border-bottom-color:#0875e1;font-weight:600}
.rtab:hover{color:#0875e1}
.rpanel{padding:16px 2px}
.colgrid{width:100%;border-collapse:collapse;font-size:13px}
.colgrid th{text-align:left;color:#555;font-weight:600;padding:8px;font-size:12px;
  border-bottom:1px solid #d6dbe0;white-space:nowrap}
.colgrid td{padding:5px 6px;border-bottom:1px solid #eee;vertical-align:middle}
.colgrid input,.colgrid select{width:100%;padding:6px;border:1px solid #c7cdd4;
  border-radius:4px;font-size:13px;background:#fff}
.rowbtn{border:1px solid #bbb;background:#fff;border-radius:50%;width:24px;
  height:24px;cursor:pointer;color:#555;font-weight:700;line-height:1}
.addbtn{border:1px solid #2E6DA4;background:#fff;color:#2E6DA4;border-radius:50%;
  width:26px;height:26px;cursor:pointer;font-weight:700;line-height:1}
.ordbtn{border:none;background:none;cursor:pointer;color:#2E6DA4;font-size:13px;
  padding:0 3px}
</style>"""

# kept name `_RTYPE_GATE_JS` so the create/edit routes need no change;
# this now carries all report-form logic (tabs, dynamic columns grid, gate).
_RTYPE_GATE_JS = """<script>
function showTab(t){
  document.querySelectorAll('.rpanel').forEach(p=>p.style.display='none');
  document.querySelectorAll('.rtab').forEach(x=>x.classList.remove('active'));
  document.getElementById('p-'+t).style.display='';
  document.querySelector('.rtab[data-t="'+t+'"]').classList.add('active');
}
function esc(s){return String(s==null?'':s).replace(/"/g,'&quot;');}
function boSelect(v){
  return '<select name="col_bo">'+BOS.map(b=>'<option '+(b===v?'selected':'')+
    '>'+b+'</option>').join('')+'</select>';
}
function colRow(d){
  d=d||{};
  const tr=document.createElement('tr');
  tr.innerHTML=
   '<td style="white-space:nowrap">'+
     '<button type="button" class="addbtn" title="Add row below" '+
       'onclick="addColAfter(this)">+</button> '+
     '<button type="button" class="rowbtn" title="Remove row" '+
       'onclick="delCol(this)">&#8722;</button></td>'+
   '<td style="white-space:nowrap">'+
     '<button type="button" class="ordbtn" title="Move up" '+
       'onclick="moveCol(this,-1)">&#9650;</button>'+
     '<button type="button" class="ordbtn" title="Move down" '+
       'onclick="moveCol(this,1)">&#9660;</button></td>'+
   '<td>'+boSelect(d.business_object||'Worker')+'</td>'+
   '<td><input name="col_field" list="fieldsugg" value="'+esc(d.field)+
     '" placeholder="field"></td>'+
   '<td><input name="col_heading" value="'+esc(d.heading)+
     '" placeholder="(optional)"></td>'+
   '<td><input name="col_format" value="'+esc(d.format)+'"></td>'+
   '<td><input name="col_options" value="'+esc(d.options)+'"></td>';
  return tr;
}
function refreshCount(){
  const n=document.querySelectorAll('#colbody tr').length;
  const el=document.getElementById('colcount'); if(el) el.textContent=n;
}
function addCol(){document.getElementById('colbody').appendChild(colRow({}));refreshCount();}
function addColAfter(btn){btn.closest('tr').after(colRow({}));refreshCount();}
function delCol(btn){
  const b=document.getElementById('colbody');
  if(b.rows.length>1){btn.closest('tr').remove();refreshCount();}
}
function moveCol(btn,dir){
  const tr=btn.closest('tr');
  if(dir<0&&tr.previousElementSibling)
    tr.parentNode.insertBefore(tr,tr.previousElementSibling);
  if(dir>0&&tr.nextElementSibling)
    tr.parentNode.insertBefore(tr.nextElementSibling,tr);
}
function opSelect(name,v){return '<select name="'+name+'">'+(window.OPS||[]).map(o=>
  '<option '+(o===v?'selected':'')+'>'+o+'</option>').join('')+'</select>';}
function aoSelect(name,v){v=v||'And';return '<select name="'+name+'">'+['And','Or'].map(o=>
  '<option '+(o===v?'selected':'')+'>'+o+'</option>').join('')+'</select>';}
function funcSelect(name,v){return '<select name="'+name+'">'+(window.FUNCS||[]).map(o=>
  '<option '+(o===v?'selected':'')+'>'+o+'</option>').join('')+'</select>';}
function cnt(body,countId){if(countId){const el=document.getElementById(countId);
  if(el)el.textContent=document.querySelectorAll('#'+body+' tr').length;}}
function delRow(btn,body,countId){const b=document.getElementById(body);
  if(b.rows.length>0){btn.closest('tr').remove();cnt(body,countId);}}
function rowBtns(addFn,delArgs){
  return '<td style="white-space:nowrap">'+
   '<button type="button" class="addbtn" onclick="'+addFn+'">+</button> '+
   '<button type="button" class="rowbtn" onclick="delRow(this,'+delArgs+')">&#8722;</button></td>';}
function fltRow(d){d=d||{};const tr=document.createElement('tr');
  tr.innerHTML=rowBtns("this.closest('tr').after(fltRow({}));cnt('fltbody','fltcount')","'fltbody','fltcount'")+
   '<td>'+aoSelect('flt_andor',d.andor)+'</td>'+
   '<td><input name="flt_lparen" value="" style="width:28px;text-align:center"></td>'+
   '<td><input name="flt_field" list="fieldsugg" value="'+esc(d.field)+'" placeholder="field"></td>'+
   '<td>'+opSelect('flt_op',d.op)+'</td>'+
   '<td><input name="flt_value" value="'+esc(d.value)+'" placeholder="value"></td>'+
   '<td><input name="flt_rparen" value="" style="width:28px;text-align:center"></td>';
  return tr;}
function aggRow(d){d=d||{};const tr=document.createElement('tr');
  tr.innerHTML=rowBtns("this.closest('tr').after(aggRow({}));cnt('aggbody','aggcount')","'aggbody','aggcount'")+
   '<td>'+aoSelect('agg_andor',d.andor)+'</td>'+
   '<td>'+funcSelect('agg_func',d.func)+'</td>'+
   '<td><input name="agg_field" value="'+esc(d.field)+'" placeholder="Dependents or Payments.Amount"></td>'+
   '<td>'+opSelect('agg_op',d.op)+'</td>'+
   '<td><input name="agg_value" value="'+esc(d.value)+'"></td>';
  return tr;}
function subRow(d){d=d||{};const tr=document.createElement('tr');
  tr.innerHTML=rowBtns("this.closest('tr').after(subRow({}));cnt('subbody',null)","'subbody',null")+
   '<td>'+aoSelect('sub_andor',d.andor)+'</td>'+
   '<td><input name="sub_field" value="'+esc(d.field)+'" placeholder="Age / Relationship / Type"></td>'+
   '<td>'+opSelect('sub_op',d.op)+'</td>'+
   '<td><input name="sub_value" value="'+esc(d.value)+'"></td>';
  return tr;}
function addFlt(){document.getElementById('fltbody').appendChild(fltRow({}));cnt('fltbody','fltcount');}
function addAgg(){document.getElementById('aggbody').appendChild(aggRow({}));cnt('aggbody','aggcount');}
function addSub(){document.getElementById('subbody').appendChild(subRow({}));cnt('subbody',null);}
(function(){
  const f=document.getElementById('fltbody');
  if(f){(window.FLT||[]).forEach(d=>f.appendChild(fltRow(d)));cnt('fltbody','fltcount');}
  const a=document.getElementById('aggbody');
  if(a){(window.AGG||[]).forEach(d=>a.appendChild(aggRow(d)));cnt('aggbody','aggcount');}
  const s=document.getElementById('subbody');
  if(s){(window.SUBF||[]).forEach(d=>s.appendChild(subRow(d)));}
})();
(function(){
  const b=document.getElementById('colbody');
  if(b){ (window.COLDEFS||[]).forEach(d=>b.appendChild(colRow(d))); refreshCount(); }
  const rt=document.getElementById('rtype'), ws=document.getElementById('ws');
  if(rt&&ws){
    const gate=()=>{ws.disabled=rt.value!=='Advanced'; if(ws.disabled)ws.checked=false;};
    rt.addEventListener('change',gate); gate();
  }
})();
</script>"""


@app.route("/task/create-custom-report", methods=["GET", "POST"])
def create_custom_report():
    msg = ""
    if request.method == "POST":
        name = re.sub(r"\s+", "_", request.form.get("report_name", "").strip())
        rpt = _report_from_form(name)
        if not name:
            msg = '<div class="err-banner">Validation error occurred. Report Name is required.</div>'
        elif name in mws.REPORTS:
            msg = f'<div class="err-banner">Validation error occurred. Report \'{name}\' already exists.</div>'
        elif not rpt["columns"]:
            msg = '<div class="err-banner">Validation error occurred. Select at least one column.</div>'
        else:
            mws.REPORTS[name] = rpt
            persist("report_definitions.json", list(mws.REPORTS.values()))
            link = (f'/ccx/service/customreport2/{TENANT}/ISU_Demo/{name}?format=json'
                    if rpt["enable_as_web_service"] else None)
            extra = (f' RaaS URL: <a href="{link}" target="_blank"><code>{link}</code></a>'
                     if link else
                     " Not web-service enabled - RaaS calls will return 403.")
            msg = (f'<div class="ok-banner">Created report <b>{name}</b> '
                   f'({rpt["report_type"]}).{extra} '
                   f'<a href="/task/view-report?name={name}" target="_blank">'
                   f'Run it</a> &middot; '
                   f'<a href="/task/edit-report?name={name}">Edit</a>.</div>')

    body = f"""{msg}
<form method="post"><div class="card">
  <label>Report Name <span class="req">*</span></label>
  <input type="text" name="report_name" placeholder="WICT_My_Report">
  {_report_form_fields()}
  <div class="btnrow">
    <button class="btn btn-ok" type="submit">OK</button>
    <a class="btn btn-cancel" href="/home">Cancel</a>
  </div>
</div></form>{_RTYPE_GATE_JS}"""
    return html_resp(layout("Create Custom Report",
                            "Advanced reports support Filter, Subfilter, Prompts, "
                            "and Enable As Web Service (RaaS)", body))


@app.route("/task/edit-report", methods=["GET", "POST"])
def edit_report():
    name = request.values.get("name", "")
    rpt = mws.REPORTS.get(name)
    if not rpt:
        return html_resp(layout("Edit Custom Report", "",
                                '<div class="err-banner">Report not found.</div>'))
    msg = ""
    if request.method == "POST":
        updated = _report_from_form(name)
        if not updated["columns"]:
            msg = ('<div class="err-banner">Select at least one column.</div>')
        else:
            mws.REPORTS[name] = updated
            persist("report_definitions.json", list(mws.REPORTS.values()))
            rpt = updated
            msg = (f'<div class="ok-banner">Saved changes to <b>{name}</b>. '
                   f'<a href="/task/view-report?name={name}" target="_blank">'
                   f'Run it</a>.</div>')

    body = f"""{msg}
<form method="post"><div class="card">
  <input type="hidden" name="name" value="{name}">
  <label>Report Name</label>
  <input type="text" value="{name}" disabled>
  <p style="font-size:12px;color:#888;margin:4px 0 8px">Report name is the
  identifier and cannot be changed here (use Copy to rename).</p>
  {_report_form_fields(rpt)}
  <div class="btnrow">
    <button class="btn btn-ok" type="submit">OK</button>
    <a class="btn btn-cancel" href="/task/view-report">Cancel</a>
  </div>
</div></form>{_RTYPE_GATE_JS}"""
    return html_resp(layout(f"Edit Custom Report - {name}",
                            "Change columns, filter, subfilter, prompts, web service",
                            body))


# ---------------------------------------------------------------------------
# View / run reports
# ---------------------------------------------------------------------------
@app.route("/task/view-report")
def view_report():
    name = request.args.get("name")
    if not name:
        rows = "".join(
            f'<tr><td>{r["report_name"]}</td><td>{r["report_type"]}</td>'
            f'<td>{"Yes" if r.get("enable_as_web_service") else "No"}</td>'
            f'<td><a href="/task/view-report?name={r["report_name"]}">Run</a> '
            f'&middot; <a href="/task/edit-report?name={r["report_name"]}">Edit</a>'
            f'</td></tr>'
            for r in mws.REPORTS.values())
        body = f"""<div class="card"><h2>Custom Reports</h2>
<table><tr><th>Report</th><th>Type</th><th>Web Service</th><th>Actions</th></tr>
{rows}</table></div>"""
        return html_resp(layout("View Custom Report", "All custom reports", body))

    rpt = mws.REPORTS.get(name)
    if not rpt:
        return html_resp(layout("View Custom Report", "",
                                '<div class="err-banner">Report not found.</div>'))

    prompts = rpt.get("prompts", [])
    # ---- mandatory prompts: a prompted report asks for values before it runs ----
    missing = [pr for pr in prompts if pr.get("required")
               and not request.args.get("p_" + pr["name"], "").strip()]
    if prompts and missing:
        fields = "".join(
            f'<label>{pr["name"]} <span class="req">*</span></label>'
            f'<input type="text" name="p_{pr["name"]}" '
            f'value="{request.args.get("p_"+pr["name"],"")}" '
            f'placeholder="enter value to run">' for pr in prompts)
        warn = ('<div class="err-banner">This report has required prompts '
                '(launch parameters). Enter values to run.</div>')
        body = f"""{warn}
<form method="get"><div class="card">
  <input type="hidden" name="name" value="{name}">
  <h3>Prompts (mandatory)</h3>
  {fields}
  <div class="btnrow"><button class="btn btn-ok" type="submit">OK</button>
    <a class="btn btn-cancel" href="/task/view-report">Cancel</a></div>
</div></form>"""
        return html_resp(layout(name, "Enter prompt values (launch parameters)",
                                body))

    # Resolve column definitions (rich) or synthesize from the columns list
    cdefs = rpt.get("column_defs")
    if not cdefs:
        cdefs = [{"field": c, "business_object": "Worker"}
                 for c in rpt["columns"]]

    # Keep the worker object alongside its scalar projection (for filter/sort)
    pairs = [(w, mws.worker_row(w, rpt["columns"])) for w in mws.WORKERS]

    # Filter on Instances (new grid; fall back to legacy single-equals filter)
    fconds = rpt.get("filter_conditions")
    if not fconds and rpt.get("filter"):
        lf = rpt["filter"]
        fconds = [{"field": lf["field"], "op": "equal to",
                   "value": lf["equals"], "andor": "And"}]
    if fconds:
        pairs = [(w, r) for (w, r) in pairs
                 if _passes_instance(mws.worker_context(w), fconds)]

    # Sub Level Filter: filter the related instances (legacy = worker equals)
    sub = rpt.get("subfilter")
    sub_note = ""
    if sub and sub.get("business_object"):
        pairs = [(_apply_subfilter(w, sub), r) for (w, r) in pairs]
        _c = ", ".join(f'{c["field"]} {c["op"]} {c["value"]}'.strip()
                       for c in sub.get("conditions", []))
        sub_note = (f' &middot; subfilter: <b>{sub["business_object"]}</b> '
                    f'where {_c}')
    elif sub and sub.get("field"):
        pairs = [(w, r) for (w, r) in pairs
                 if str(r.get(sub["field"])) == str(sub["equals"])]
        sub_note = f' &middot; subfilter: <b>{sub["field"]}={sub["equals"]}</b>'

    # Filter on Aggregations (e.g. Count of Dependents >= 2)
    aconds = rpt.get("aggregation_filters")
    if aconds:
        pairs = [(w, r) for (w, r) in pairs if _passes_agg(w, aconds)]

    applied = []
    for pr in prompts:
        v = request.args.get("p_" + pr["name"], "").strip()
        if v:
            pairs = [(w, r) for (w, r) in pairs
                     if str(r.get(pr["field"], "")) == v]
            applied.append(f'{pr["name"]}={v}')

    srt = rpt.get("sort")
    if srt and srt.get("field"):
        sf = srt["field"]
        def _key(pair):
            v = pair[1].get(sf, "")
            try:
                return (0, float(str(v).replace(",", "").replace("$", "")))
            except (ValueError, TypeError):
                return (1, str(v))
        pairs = sorted(pairs, key=_key, reverse=(srt.get("dir") == "desc"))

    headings = {d["field"]: d.get("heading")
                for d in cdefs if d.get("heading")}

    def _lbl(cd):
        return headings.get(cd["field"]) or cd["field"]

    def _fieldth(cd):
        return (f'<th><span class="thlbl">{_lbl(cd)}</span>'
                f'<span class="thsort"></span><span class="thfilt"></span>'
                f'<span class="thcaret">&#9662;</span></th>')

    # Group header: consecutive related-BO columns sit under one BO label.
    group_row, field_row, has_group = "", "", False
    i = 0
    while i < len(cdefs):
        bo = cdefs[i].get("business_object", "Worker")
        if bo in mws.MULTI_BOS:
            run = []
            while i < len(cdefs) and cdefs[i].get("business_object") == bo:
                run.append(cdefs[i]); i += 1
            has_group = True
            group_row += f'<th class="grp" colspan="{len(run)}">{bo}</th>'
            field_row += "".join(_fieldth(cd) for cd in run)
        else:
            group_row += '<th class="grpblank"></th>'
            field_row += _fieldth(cdefs[i]); i += 1
    head = (f'<tr>{group_row}</tr><tr>{field_row}</tr>' if has_group
            else f'<tr>{field_row}</tr>')

    # Body: multi-instance related values club together (stacked) per row.
    rows = ""
    for w, _r in pairs:
        cells = ""
        for cd in cdefs:
            vals = mws.resolve_instances(w, cd.get("business_object", "Worker"),
                                         cd["field"])
            vals = [v for v in vals if v != ""] or ([""] if not vals else vals)
            cells += '<td>' + "<br>".join(vals) + '</td>'
        rows += f"<tr>{cells}</tr>"

    crit = (f' &middot; prompts applied: <b>{", ".join(applied)}</b>'
            if applied else "")
    ws_note = (f'RaaS: <code>/ccx/service/customreport2/{TENANT}/ISU_Demo/{name}'
               f'?format=json</code>' if rpt.get("enable_as_web_service")
               else "Not enabled as web service (RaaS returns 403).")
    group_note = (' &middot; related objects (Dependents/Payments/Benefits) are '
                  '<b>clubbed together</b> within each worker row'
                  if has_group else "")
    body = f"""{GRID_CSS}<div class="card">
<h2>{name}</h2>
<p style="font-size:13px;color:#666;margin-bottom:6px">{ws_note}{sub_note}{crit}</p>
<p style="margin-bottom:12px"><a class="btn btn-cancel"
   href="/task/edit-report?name={name}">&#9998; Edit Report</a></p>
<p style="font-size:12px;color:#888;margin-bottom:6px">Tip: click any column
header to Sort Ascending / Descending or Filter (like the Workday grid).{group_note}</p>
<div class="wd-count" id="rpttbl-count"></div>
<div class="wd-grid" style="overflow-x:auto">
  <table id="rpttbl"><thead>{head}</thead><tbody>{rows}</tbody></table>
</div></div>{GRID_JS}<script>initWdGrid('rpttbl');</script>"""
    return html_resp(layout(name, f'{rpt["report_type"]} report - '
                            f'data source: {rpt.get("data_source","")}', body))


# ---------------------------------------------------------------------------
# Create EIB (inbound: upload CSV -> Request_One_Time_Payment)
# ---------------------------------------------------------------------------
SOAP_PAYROLL_ROW = """      <wd:Payroll_Input_Data>
        <wd:Worker_Reference><wd:ID wd:type="Employee_ID">{Employee_ID}</wd:ID></wd:Worker_Reference>
        <wd:Pay_Component>{Pay_Component}</wd:Pay_Component>
        <wd:Amount>{Amount}</wd:Amount>
      </wd:Payroll_Input_Data>"""

SOAP_PAYROLL = """<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
              xmlns:wd="urn:com.workday/bsvc">
  <env:Body>
    <wd:{op}_Request wd:version="v42.0">
{rows}
    </wd:{op}_Request>
  </env:Body>
</env:Envelope>"""

SOAP_COMP_CHANGE = """<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
              xmlns:wd="urn:com.workday/bsvc">
  <env:Body>
    <wd:Request_Compensation_Change_Request wd:version="v42.0">
      <wd:Worker_Reference><wd:ID wd:type="Employee_ID">{Employee_ID}</wd:ID></wd:Worker_Reference>
      <wd:New_Base_Salary>{Amount}</wd:New_Base_Salary>
    </wd:Request_Compensation_Change_Request>
  </env:Body>
</env:Envelope>"""

SOAP_OTP = """<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
              xmlns:wd="urn:com.workday/bsvc">
  <env:Body>
    <wd:Request_One_Time_Payment_Request wd:version="v42.0">
      <wd:One_Time_Payment_Data>
        <wd:Employee_Reference>
          <wd:ID wd:type="Employee_ID">{Employee_ID}</wd:ID>
        </wd:Employee_Reference>
        <wd:Amount>{Amount}</wd:Amount>
      </wd:One_Time_Payment_Data>
    </wd:Request_One_Time_Payment_Request>
  </env:Body>
</env:Envelope>"""


@app.route("/task/create-eib", methods=["GET", "POST"])
def create_eib():
    if request.method == "POST":
        name = request.form.get("eib_name", "EIB_Run")
        direction = request.form.get("direction", "inbound")

        if direction == "outbound":
            rep = request.form.get("source_report", "")
            xslt_text = request.form.get("out_xslt", "").strip()
            fname = os.path.basename(
                request.form.get("out_filename", "").strip()
                or f"{name.replace(' ', '_')}_output.txt")
            sched = request.form.get("schedule", "Run Now")
            client = app.test_client()
            # EIB behavior: prompts are mandatory launch parameters
            rpt_def = mws.REPORTS.get(rep, {})
            missing = [pr["name"] for pr in rpt_def.get("prompts", [])
                       if pr.get("required")
                       and not request.form.get(f"prompt_{pr['name']}",
                                                "").strip()]
            if missing:
                body = (f'<div class="err-banner">The integration cannot be '
                        f'launched: values must be provided for required '
                        f'prompts: <b>{", ".join(missing)}</b>. (EIB exposes '
                        f'report prompts as launch parameters and will not '
                        f'run without them.)</div>')
                return html_resp(layout("Create EIB", f"{name} - outbound",
                                        body))
            qs = ""
            for pr in rpt_def.get("prompts", []):
                v = request.form.get("prompt_" + pr["name"], "").strip()
                if v:
                    qs += f"&{pr['name']}={v}"
            r = client.get(f"/ccx/service/customreport2/{TENANT}/ISU_Demo/"
                           f"{rep}?format=xml{qs}")
            content = r.get_data(as_text=True)
            step2 = "no transform (raw report XML)"
            if r.status_code == 200 and xslt_text:
                try:
                    from lxml import etree
                    x = etree.XSLT(etree.fromstring(xslt_text.encode()))
                    content = str(x(etree.fromstring(content.encode())))
                    step2 = f"XSLT applied ({len(content)} bytes)"
                except Exception as e:
                    step2 = f"XSLT FAILED: {e}"
            os.makedirs("cc_output", exist_ok=True)
            with open(os.path.join("cc_output", fname), "w") as fo:
                fo.write(content)
            EIB_SCHEDULES.append({"eib": name, "report": rep,
                                  "schedule": sched})
            sched_note = ("Ran immediately." if sched == "Run Now" else
                          f"Schedule recorded: {sched} (simulated scheduler - "
                          f"recurrence is logged, not executed).")
            body = f"""<div class="{'err-banner' if 'FAILED' in step2 else 'ok-banner'}">
<b>{name}</b> (Outbound EIB)<br>
Get Data: custom report <b>{rep}</b> -&gt; HTTP {r.status_code}<br>
Transform: {step2}<br>
Deliver: <a href="/cc-output/{fname}" target="_blank">{fname}</a><br>
{sched_note}</div>"""
            return html_resp(layout("Create EIB", f"{name} - outbound run",
                                    body))

        f = request.files.get("data_file")
        if not f or not f.filename:
            body = '<div class="err-banner">Validation error occurred. Attach a CSV file at launch.</div>'
            return html_resp(layout("Create EIB", "", body + eib_form()))

        rows = list(csv.DictReader(io.StringIO(f.read().decode("utf-8"))))
        client = app.test_client()
        results = []
        op = request.form.get("ws_operation", "Request_One-Time_Payment")

        if op == "Import_Payroll_Input":
            # Bulk: ONE web service call for the whole file (asynchronous style)
            row_xml = "\n".join(SOAP_PAYROLL_ROW.format(
                Employee_ID=r0.get("Employee_ID", ""),
                Pay_Component=r0.get("Pay_Component", "Earning"),
                Amount=r0.get("Amount", "0")) for r0 in rows)
            soap = SOAP_PAYROLL.format(op="Import_Payroll_Input", rows=row_xml)
            r = client.post(f"/ccx/service/{TENANT}/Payroll/v42.0",
                            data=soap, content_type="text/xml")
            txt = r.get_data(as_text=True)
            loaded = re.search(r"<wd:Loaded>(\d+)<", txt)
            failedn = re.search(r"<wd:Failed>(\d+)<", txt)
            errs = re.findall(r"<wd:Error>([^<]*)<", txt)
            for i, r0 in enumerate(rows, 1):
                bad = any(r0.get("Employee_ID", "") in e for e in errs)
                results.append((i, r0.get("Employee_ID"),
                                "FAILED" if bad else "COMPLETED",
                                next((e for e in errs
                                      if r0.get("Employee_ID", "") in e), "")))
            results.append(("-", "BULK CALL",
                            "COMPLETED" if r.status_code == 200 else "FAILED",
                            f"1 Import_Payroll_Input request: "
                            f"{loaded.group(1) if loaded else '?'} loaded, "
                            f"{failedn.group(1) if failedn else '?'} failed"))
        else:
            for i, row in enumerate(rows, 1):
                if op == "Submit_Payroll_Input":
                    soap = SOAP_PAYROLL.format(
                        op="Submit_Payroll_Input",
                        rows=SOAP_PAYROLL_ROW.format(
                            Employee_ID=row.get("Employee_ID", ""),
                            Pay_Component=row.get("Pay_Component", "Earning"),
                            Amount=row.get("Amount", "0")))
                    path = f"/ccx/service/{TENANT}/Payroll/v42.0"
                elif op == "Request_Compensation_Change":
                    soap = SOAP_COMP_CHANGE.format(
                        Employee_ID=row.get("Employee_ID", ""),
                        Amount=row.get("Amount", "0"))
                    path = f"/ccx/service/{TENANT}/Compensation/v42.0"
                else:
                    soap = SOAP_OTP.format(
                        Employee_ID=row.get("Employee_ID", ""),
                        Amount=row.get("Amount", "0"))
                    path = f"/ccx/service/{TENANT}/Compensation/v42.0"
                r = client.post(path, data=soap, content_type="text/xml")
                if r.status_code == 200:
                    results.append((i, row.get("Employee_ID"), "COMPLETED", ""))
                else:
                    txt = r.get_data(as_text=True)
                    fault = txt.split("<faultstring>")[1].split("</faultstring>")[0] \
                        if "<faultstring>" in txt else "SOAP Fault"
                    results.append((i, row.get("Employee_ID"), "FAILED", fault))

        done = sum(1 for r in results if r[2] == "COMPLETED")
        status = "Completed" if done == len(results) else "Completed with Errors"
        trs = "".join(
            f'<tr><td>{l}</td><td>{e}</td>'
            f'<td style="color:{"#256d25" if s == "COMPLETED" else "#a32018"}">{s}</td>'
            f'<td>{err}</td></tr>' for l, e, s, err in results)
        body = f"""<div class="{'ok-banner' if done == len(results) else 'err-banner'}">
<b>{name}</b> - Overall Status: {status} ({done} loaded,
{len(results) - done} failed)</div>
<div class="card"><h2>Process Monitor</h2>
<table><tr><th>Line</th><th>Employee_ID</th><th>Status</th><th>Error</th></tr>
{trs}</table>
<p style="margin-top:14px;font-size:13px">Verify loads in
<a href="/task/integration-events" target="_blank">Integration Events</a>.</p></div>"""
        return html_resp(layout("Create EIB", f"{name} - run summary", body))

    return html_resp(layout("Create EIB",
                            "Inbound EIBs import data into Workday. "
                            "Outbound EIBs export data from Workday.",
                            eib_form()))


def eib_form():
    rep_opts = "".join(
        f'<option>{r["report_name"]}</option>' for r in mws.REPORTS.values()
        if r.get("enable_as_web_service"))
    prompts_json = json.dumps({r["report_name"]: r.get("prompts", [])
                               for r in mws.REPORTS.values()
                               if r.get("enable_as_web_service")})
    return f"""
<form method="post" enctype="multipart/form-data"><div class="card">
  <label>Name <span class="req">*</span></label>
  <input type="text" name="eib_name" placeholder="PS_EIB_Inbound_Sampl">
  <label>Direction <span class="req">*</span></label>
  <div class="checks">
    <label><input type="radio" name="direction" value="inbound" checked
      onclick="gate()"> Inbound</label>
    <label><input type="radio" name="direction" value="outbound"
      onclick="gate()"> Outbound</label>
  </div>
  <div id="inb">
    <label>Get Data - Retrieval Method</label>
    <select disabled><option>Attach File at Launch</option></select>
    <label>Attach File (CSV: Employee_ID, Amount)</label>
    <input type="file" name="data_file" accept=".csv">
    <label>Deliver - Workday Web Service Operation</label>
    <select name="ws_operation">
      <option value="Request_One-Time_Payment">Request One-Time Payment (Compensation)</option>
      <option value="Submit_Payroll_Input">Submit Payroll Input (Payroll - single/synchronous)</option>
      <option value="Import_Payroll_Input">Import Payroll Input (Payroll - bulk/asynchronous)</option>
      <option value="Request_Compensation_Change">Request Compensation Change (Compensation)</option>
    </select>
    <p style="font-size:12px;color:#888">Payroll operations expect CSV columns:
    Employee_ID, Pay_Component, Amount (sample: payroll_inputs.csv)</p>
    <div style="background:#F4F7FA;border:1px solid #D7DEE5;border-radius:6px;
      padding:8px 12px;font-size:12.5px">
      <b>Actions &gt; Template Model &gt; Generate Spreadsheet Template:</b>
      <a href="/task/generate-template?op=Request_One-Time_Payment">
        Request One-Time Payment</a> |
      <a href="/task/generate-template?op=Submit_Payroll_Input">
        Submit Payroll Input</a> |
      <a href="/task/generate-template?op=Import_Payroll_Input">
        Import Payroll Input</a> |
      <a href="/task/generate-template?op=Request_Compensation_Change">
        Request Compensation Change</a>
      &nbsp;&middot;&nbsp; <a href="/task/my-reports">My Reports</a><br>
      <b>Actions &gt; Integration &gt;</b>
      <a href="/task/launch-schedule-eib">Launch / Schedule</a>
      <span style="color:#888">(Integration Criteria: Attachment, Load Error
      Limit, Validate Only Load, Add Errors to Attachment)</span>
    </div>
  </div>
  <div id="outb" style="display:none">
    <label>Get Data - Custom Report (web-service enabled only)</label>
    <select name="source_report" id="srcrep">{rep_opts}</select>
    <div id="prompt_fields"></div>
    <label>Transform - XSLT (optional; blank = deliver raw report XML)</label>
    <textarea name="out_xslt" rows="6" placeholder="Paste an XSLT, e.g. from workers_to_psv.xsl"></textarea>
    <label>Deliver - Output Filename</label>
    <input type="text" name="out_filename" placeholder="report_output.csv">
    <label>Schedule</label>
    <select name="schedule"><option>Run Now</option><option>Daily</option>
    <option>Weekly</option><option>Monthly</option></select>
  </div>
  <script>
  // EIB behavior: a prompted report automatically exposes its prompts as
  // launch parameters (Integration Criteria) - and they are mandatory.
  const REPORT_PROMPTS = {prompts_json};
  function renderPrompts() {{
    const rep = document.getElementById('srcrep');
    const box = document.getElementById('prompt_fields');
    if (!rep || !box) return;
    const prs = REPORT_PROMPTS[rep.value] || [];
    box.innerHTML = prs.length
      ? '<div style="background:#f0f6fc;border-radius:4px;padding:8px 10px;'
        + 'margin-top:8px"><b style="font-size:13px">Integration Criteria '
        + '(report prompts exposed as launch parameters)</b>'
        + prs.map(p => '<label>' + p.name + (p.required
            ? ' <span class="req">*</span>' : '')
            + '</label><input type="text" name="prompt_' + p.name
            + '" placeholder="Specify Value">').join('') + '</div>'
      : '';
  }}
  document.getElementById('srcrep') &&
    document.getElementById('srcrep').addEventListener('change', renderPrompts);
  renderPrompts();
  </script>
  </div>
  <div class="btnrow">
    <button class="btn btn-ok" type="submit">OK</button>
    <a class="btn btn-cancel" href="/home">Cancel</a>
  </div>
</div></form>
<script>
function gate() {{
  const inb = document.querySelector('input[value=inbound]').checked;
  document.getElementById('inb').style.display = inb ? '' : 'none';
  document.getElementById('outb').style.display = inb ? 'none' : '';
}}
</script>"""


# ---------------------------------------------------------------------------
# Integration Events + All Workers
# ---------------------------------------------------------------------------
@app.route("/task/integration-events")
def integration_events():
    rows = "".join(f'<tr><td>{i+1}</td><td>{p["Employee_ID"]}</td>'
                   f'<td>{p["Amount"]}</td></tr>'
                   for i, p in enumerate(mws.PAYMENT_LOG)) or \
           '<tr><td colspan="3">No inbound loads yet. Run Create EIB first.</td></tr>'
    body = f"""<div class="card"><h2>One-Time Payments loaded by inbound EIBs</h2>
<table><tr><th>#</th><th>Employee_ID</th><th>Amount</th></tr>{rows}</table></div>"""
    return html_resp(layout("Integration Events",
                            "Data written into the tenant this session", body))


@app.route("/task/all-workers")
def all_workers():
    rows = "".join(
        f'<tr><td>{w["Employee_ID"]}</td><td>{w["First_Name"]} {w["Last_Name"]}</td>'
        f'<td>{w["Org"]}</td><td>{w["Hire_Date"]}</td>'
        f'<td>{"Active" if w["Active"] == "1" else "Terminated"}</td>'
        f'<td>{len(w["Payments"])}</td></tr>' for w in mws.WORKERS)
    body = f"""<div class="card"><h2>{len(mws.WORKERS)} workers</h2>
<table><tr><th>Employee_ID</th><th>Name</th><th>Org</th><th>Hire Date</th>
<th>Status</th><th>Payments</th></tr>{rows}</table></div>"""
    return html_resp(layout("All Workers", "Worker business object", body))


@app.route("/ui")
def ui_redirect():
    return redirect("/home")




# ============================================================
#  Generate Spreadsheet Template (standard Workday EIB flow)
#  Actions > Template Model > Generate Spreadsheet Template
#  Produces SpreadsheetML (.xml) - opens directly in Excel.
# ============================================================
TEMPLATE_DIR = os.path.join("cc_output", "templates")

EIB_TEMPLATES = {
    "Request_One-Time_Payment": {
        "desc": ("This web service operation is designed to pay an employee "
                 "a one-time payment such as a signing bonus using the "
                 "Request One-Time Payment business process."),
        "fields": [("Spreadsheet Key*", "Required", "Text"),
                   ("Employee*", "Required", "Employee_ID"),
                   ("Effective Date*", "Required", "YYYY-MM-DD"),
                   ("One Time Payment Plan*", "Required",
                    "One-Time_Payment_Plan_ID"),
                   ("Amount*", "Required", "Decimal"),
                   ("Currency*", "Required", "Currency_ID"),
                   ("Comment", "Optional", "Text")]},
    "Submit_Payroll_Input": {
        "desc": ("Submits a single payroll input synchronously, returning "
                 "validation results in the response."),
        "fields": [("Spreadsheet Key*", "Required", "Text"),
                   ("Employee*", "Required", "Employee_ID"),
                   ("Pay Component*", "Required", "Pay_Component_ID"),
                   ("Start Date*", "Required", "YYYY-MM-DD"),
                   ("End Date", "Optional", "YYYY-MM-DD"),
                   ("Amount*", "Required", "Decimal")]},
    "Import_Payroll_Input": {
        "desc": ("High-volume bulk load of payroll inputs. The request is "
                 "accepted in one call and processed asynchronously "
                 "(Loaded / Failed per line in the monitor)."),
        "fields": [("Spreadsheet Key*", "Required", "Text"),
                   ("Employee*", "Required", "Employee_ID"),
                   ("Pay Component*", "Required", "Pay_Component_ID"),
                   ("Start Date*", "Required", "YYYY-MM-DD"),
                   ("End Date", "Optional", "YYYY-MM-DD"),
                   ("Amount*", "Required", "Decimal")]},
    "Request_Compensation_Change": {
        "desc": ("Requests a base compensation change for a worker using "
                 "the Request Compensation Change business process."),
        "fields": [("Spreadsheet Key*", "Required", "Text"),
                   ("Employee*", "Required", "Employee_ID"),
                   ("Effective Date*", "Required", "YYYY-MM-DD"),
                   ("Base Salary*", "Required", "Decimal"),
                   ("Currency", "Optional", "Currency_ID")]},
}

def _sml_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def build_spreadsheet_template(op):
    """SpreadsheetML 2003 workbook: Overview sheet + operation sheet with
    Area / Restrictions / Format / Fields banded header rows."""
    t = EIB_TEMPLATES[op]
    title = op.replace("_", " ")
    cells_fields = "".join(
        f'<Cell ss:StyleID="sFld"><Data ss:Type="String">'
        f'{_sml_escape(f[0])}</Data></Cell>' for f in t["fields"])
    cells_restr = "".join(
        f'<Cell ss:StyleID="sRes"><Data ss:Type="String">{f[1]}</Data></Cell>'
        for f in t["fields"])
    cells_fmt = "".join(
        f'<Cell ss:StyleID="sRes"><Data ss:Type="String">{f[2]}</Data></Cell>'
        for f in t["fields"])
    return f"""<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Styles>
  <Style ss:ID="sTitle"><Font ss:Bold="1" ss:Size="16" ss:Color="#1F3864"/>
  </Style>
  <Style ss:ID="sHdr"><Font ss:Bold="1"/></Style>
  <Style ss:ID="sBP"><Interior ss:Color="#2F3699" ss:Pattern="Solid"/>
   <Font ss:Color="#FFFFFF" ss:Bold="1"/></Style>
  <Style ss:ID="sArea"><Interior ss:Color="#6B7C3A" ss:Pattern="Solid"/>
   <Font ss:Color="#FFFFFF" ss:Bold="1"/></Style>
  <Style ss:ID="sRes"><Interior ss:Color="#FFFDE7" ss:Pattern="Solid"/>
   <Font ss:Size="9"/></Style>
  <Style ss:ID="sFld"><Interior ss:Color="#2F3699" ss:Pattern="Solid"/>
   <Font ss:Color="#FFFFFF" ss:Bold="1"/></Style>
 </Styles>
 <Worksheet ss:Name="Overview">
  <Table>
   <Row/><Row><Cell ss:Index="2" ss:StyleID="sTitle">
    <Data ss:Type="String">{_sml_escape(title)}</Data></Cell></Row>
   <Row/><Row><Cell ss:Index="2">
    <Data ss:Type="String">{_sml_escape(t["desc"])}</Data></Cell></Row>
   <Row/>
   <Row>
    <Cell ss:Index="2" ss:StyleID="sHdr">
     <Data ss:Type="String">Business Process</Data></Cell>
    <Cell ss:StyleID="sHdr">
     <Data ss:Type="String">Processing Instruction</Data></Cell>
    <Cell ss:StyleID="sHdr">
     <Data ss:Type="String">Processing Comment</Data></Cell>
   </Row>
   <Row>
    <Cell ss:Index="2" ss:StyleID="sBP">
     <Data ss:Type="String">{_sml_escape(title)}</Data></Cell>
    <Cell><Data ss:Type="String">Manual Processing | Automatic Processing |
 Run Now | Run Now With Automatic Processing</Data></Cell>
   </Row>
  </Table>
 </Worksheet>
 <Worksheet ss:Name="{_sml_escape(title)[:31]}">
  <Table>
   <Row><Cell ss:StyleID="sTitle">
    <Data ss:Type="String">{_sml_escape(title)}</Data></Cell></Row>
   <Row><Cell ss:StyleID="sArea"><Data ss:Type="String">Area</Data></Cell>
    <Cell ss:StyleID="sBP" ss:MergeAcross="{len(t['fields'])-1}">
     <Data ss:Type="String">All</Data></Cell></Row>
   <Row><Cell ss:StyleID="sArea">
    <Data ss:Type="String">Restrictions</Data></Cell>{cells_restr}</Row>
   <Row><Cell ss:StyleID="sArea">
    <Data ss:Type="String">Format</Data></Cell>{cells_fmt}</Row>
   <Row><Cell ss:StyleID="sArea">
    <Data ss:Type="String">Fields</Data></Cell>{cells_fields}</Row>
  </Table>
 </Worksheet>
</Workbook>"""

@app.route("/task/generate-template", methods=["GET", "POST"])
def generate_template():
    op = request.values.get("op", "Request_One-Time_Payment")
    if request.method == "GET":
        return html_resp(layout("Confirm Spreadsheet Generation",
            op.replace("_", " "), f"""
  <p>Confirm the generation</p>
  <form method="post">
    <input type="hidden" name="op" value="{op}">
    <label>Confirm <span class="req">*</span>
      <input type="checkbox" name="confirm" required></label>
    <button class="primary" type="submit">Submit</button>
    <a href="/task/create-eib"><button type="button">Cancel</button></a>
  </form>"""))
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    fname = f"{op}.xml"
    with open(os.path.join(TEMPLATE_DIR, fname), "w") as f:
        f.write(build_spreadsheet_template(op))
    return html_resp(layout("Spreadsheet Template Generation Initiated", "",
        f"""
  <p>The spreadsheet template is being generated in the background. When your
  file is ready for download, you will be able to access it from the
  notification link next to your sign-in name or from the My Reports task.
  You can also track progress in the Process Monitor.</p>
  <div style="background:#FFF8E6;border:1px solid #E8C868;border-radius:6px;
    padding:10px 14px;margin:12px 0;display:inline-block">
    &#128196; <b>{fname}</b> is now available in
    <a href="/task/my-reports">My Reports</a></div><br>
  <a href="/task/my-reports"><button class="primary">Done</button></a>"""))

@app.route("/task/my-reports")
def my_reports():
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    files = sorted(os.listdir(TEMPLATE_DIR))
    rows = "".join(
        f'<tr><td>&#128196; {f}</td><td>Spreadsheet Template (Excel)</td>'
        f'<td><a href="/download/template/{f}">Download</a></td></tr>'
        for f in files) or '<tr><td colspan="3">No generated files yet. '         'Use Generate Spreadsheet Template on the Create EIB page.</td></tr>'
    return html_resp(layout("My Reports", "Generated files", f"""
  <table class="grid"><tr><th>File</th><th>Type</th><th></th></tr>{rows}
  </table>"""))

@app.route("/download/template/<path:fname>")
def download_template(fname):
    from flask import send_from_directory
    return send_from_directory(os.path.abspath(TEMPLATE_DIR), fname,
                               as_attachment=True)




# ============================================================
#  Launch / Schedule Integration (inbound EIB) - standard
#  Workday Integration Criteria grid:
#    (Attachment)            Integration Attachment
#    (Workday Web Service)   Load Error Limit | Validate Only Load
#    (Operation)             Add Errors to Attachment
# ============================================================
@app.route("/task/launch-schedule-eib", methods=["GET", "POST"])
def launch_schedule_eib():
    ops = list(EIB_TEMPLATES.keys())
    if request.method == "GET":
        op = request.values.get("op", ops[0])
        opts = "".join(f'<option {"selected" if o==op else ""}>{o}</option>'
                       for o in ops)
        disp = op.replace("_", " ")
        return html_resp(layout("Schedule an Integration", "", f"""
  <form method="post" enctype="multipart/form-data">
  <label>Request Name <span class="req">*</span></label>
  <input type="text" name="request_name" value="INT_{op}" required>
  <label>Integration System (Web Service Operation)</label>
  <select name="ws_operation">{opts}</select>
  <label>Run Frequency</label>
  <select disabled><option>Run Now</option></select>

  <h3 style="margin-top:18px">Integration Criteria <span style="color:#888;
    font-weight:400;font-size:13px">5 items</span></h3>
  <table class="grid">
   <tr><th style="width:34%">Provider</th><th>Field</th>
       <th style="width:18%">Value Type</th><th>Value</th></tr>
   <tr><td rowspan="2">(Launch Parameter) {disp}</td>
       <td>&#128640; Effective Date <span class="req">*</span></td>
       <td>Prompt - mandatory launch parameter</td>
       <td><input type="date" name="lp_effective_date"
            value="2026-06-30" required style="max-width:200px"></td></tr>
   <tr><td>&#128221; Run Comment</td>
       <td>Prompt - optional</td>
       <td><input type="text" name="lp_run_comment"
            placeholder="optional note" style="max-width:220px"></td></tr>
   <tr><td>(Attachment) {disp} (Web Service)</td>
       <td>&#128206; Integration Attachment <span class="req">*</span></td>
       <td>Specify Value &mdash; Create Integration Attachment</td>
       <td><input type="file" name="data_file" accept=".csv" required></td></tr>
   <tr><td rowspan="2">(Workday Web Service) {disp} (Web Service)</td>
       <td>&#128290; Load Error Limit</td>
       <td>Use System Default / Specify Value</td>
       <td><input type="text" name="load_error_limit"
            placeholder="Use System Default (no limit)"
            style="max-width:220px"></td></tr>
   <tr><td>&#9989; Validate Only Load</td>
       <td>Specify Value</td>
       <td><input type="checkbox" name="validate_only"></td></tr>
   <tr><td>{disp}</td>
       <td>&#128221; Add Errors to Attachment</td>
       <td>Specify Value</td>
       <td><input type="checkbox" name="add_errors"></td></tr>
  </table>
  <p style="font-size:12.5px;color:#a06000;margin:6px 0">A required Launch
  Parameter (e.g. Effective Date) must have a value or the integration will not
  launch - exactly like a prompted Workday integration.</p>
  <button class="primary" type="submit">OK</button>
  <a href="/task/create-eib"><button type="button">Cancel</button></a>
  </form>"""))

    # ---------------- POST: run with the criteria ----------------
    op = request.form.get("ws_operation", ops[0])
    req_name = request.form.get("request_name", f"INT_{op}")
    validate_only = bool(request.form.get("validate_only"))
    add_errors = bool(request.form.get("add_errors"))
    lel_raw = request.form.get("load_error_limit", "").strip()
    load_error_limit = int(lel_raw) if lel_raw.isdigit() else None

    # Mandatory launch parameters: integration will NOT run without them.
    lp_effective_date = request.form.get("lp_effective_date", "").strip()
    lp_run_comment = request.form.get("lp_run_comment", "").strip()
    if not lp_effective_date:
        return html_resp(layout("Schedule an Integration", "",
            '<div class="err-banner">The integration cannot be launched: the '
            'required launch parameter <b>Effective Date</b> has no value. '
            'Enter a value for every required launch parameter, then launch.'
            '</div>'))

    f = request.files.get("data_file")
    if not f or not f.filename:
        return html_resp(layout("Schedule an Integration", "",
            '<div class="err-banner">Integration Attachment is required '
            '(Create Integration Attachment).</div>'))
    rows = list(csv.DictReader(io.StringIO(f.read().decode("utf-8"))))

    valid_ids = {w["Employee_ID"] for w in mws.WORKERS
                 if w.get("Active") == "1"}
    client = app.test_client()
    results, err_count, aborted = [], 0, False

    for i, row in enumerate(rows, 1):
        emp = row.get("Employee_ID", "")
        if aborted:
            results.append((i, emp, "ABORTED",
                            "Load Error Limit reached - line not processed"))
            continue
        # ---- validation phase (always) ----
        verr = None
        if emp not in valid_ids:
            verr = f"Validation error: Worker {emp} does not exist or is inactive."
        else:
            try:
                float(row.get("Amount", "0"))
            except ValueError:
                verr = f"Validation error: Amount '{row.get('Amount')}' is not numeric."
        if verr:
            err_count += 1
            results.append((i, emp, "FAILED", verr))
        elif validate_only:
            results.append((i, emp, "VALIDATED",
                            "Row passed validation. Not committed "
                            "(Validate Only Load)."))
        else:
            # ---- commit phase ----
            if op in ("Submit_Payroll_Input", "Import_Payroll_Input"):
                soap = SOAP_PAYROLL.format(op="Submit_Payroll_Input",
                    rows=SOAP_PAYROLL_ROW.format(Employee_ID=emp,
                        Pay_Component=row.get("Pay_Component", "Earning"),
                        Amount=row.get("Amount", "0")))
                path = f"/ccx/service/{TENANT}/Payroll/v42.0"
            elif op == "Request_Compensation_Change":
                soap = SOAP_COMP_CHANGE.format(Employee_ID=emp,
                                               Amount=row.get("Amount", "0"))
                path = f"/ccx/service/{TENANT}/Compensation/v42.0"
            else:
                soap = SOAP_OTP.format(Employee_ID=emp,
                                       Amount=row.get("Amount", "0"))
                path = f"/ccx/service/{TENANT}/Compensation/v42.0"
            r = client.post(path, data=soap, content_type="text/xml")
            if r.status_code == 200:
                results.append((i, emp, "COMPLETED", ""))
            else:
                txt = r.get_data(as_text=True)
                fault = txt.split("<faultstring>")[1].split(
                    "</faultstring>")[0] if "<faultstring>" in txt                     else "SOAP Fault"
                err_count += 1
                results.append((i, emp, "FAILED", fault))
        if load_error_limit is not None and err_count >= load_error_limit:
            aborted = True

    # ---- Add Errors to Attachment ----
    err_link = ""
    if add_errors:
        errs = [r for r in results if r[2] in ("FAILED", "ABORTED")]
        if errs:
            os.makedirs("cc_output", exist_ok=True)
            efn = f"{req_name}_errors.csv"
            with open(os.path.join("cc_output", efn), "w", newline="") as ef:
                w = csv.writer(ef)
                w.writerow(["Line", "Employee_ID", "Status", "Error"])
                w.writerows(errs)
            err_link = (f'<p>&#128206; Errors added to attachment: '
                        f'<a href="/download/output/{efn}">{efn}</a></p>')

    nfail = sum(1 for r in results if r[2] in ("FAILED", "ABORTED"))
    nok = len(results) - nfail
    status = ("Completed" if nfail == 0 else
              "Completed with Errors" if nok else "Failed")
    mode_note = ""
    if validate_only:
        mode_note = ('<div style="background:#EAF3FB;border:1px solid '
                     '#9CC3E5;border-radius:6px;padding:8px 12px;margin:'
                     '8px 0"><b>Validate Only Load:</b> rows were validated '
                     'against the tenant but <b>no data was committed</b>. '
                     'Uncheck it to perform the actual load.</div>')
    abort_note = ""
    if aborted:
        abort_note = (f'<div class="err-banner">Load Error Limit '
                      f'({load_error_limit}) reached - the load was aborted; '
                      f'remaining lines were not processed.</div>')
    trs = "".join(
        f'<tr><td>{l}</td><td>{e}</td><td style="color:'
        f'{"#1B7F3B" if s in ("COMPLETED","VALIDATED") else "#A33"}">{s}</td>'
        f'<td>{d}</td></tr>' for l, e, s, d in results)
    return html_resp(layout("View Background Process", req_name, f"""
  <p><b>Process:</b> {req_name} &nbsp; <b>Status:</b> {status} &nbsp;
     ({nok} succeeded, {nfail} failed/aborted)</p>
  <p style="font-size:13px;color:#555"><b>Launch Parameters:</b>
     Effective Date = <b>{lp_effective_date}</b>{(' &middot; Run Comment = <b>'
     + lp_run_comment + '</b>') if lp_run_comment else ''}</p>
  {mode_note}{abort_note}{err_link}
  <table class="grid"><tr><th>Line</th><th>Employee</th><th>Status</th>
   <th>Message / Fault</th></tr>{trs}</table>
  <p><a href="/task/launch-schedule-eib?op={op}">Launch again</a> &middot;
     <a href="/home">Home</a></p>"""))

@app.route("/download/output/<path:fname>")
def download_output(fname):
    from flask import send_from_directory
    return send_from_directory(os.path.abspath("cc_output"), fname,
                               as_attachment=True)


if __name__ == "__main__":
    import sys
    sys.modules.setdefault("workday_ui", sys.modules["__main__"])
    import core_connector  # noqa: F401  (registers Core Connector routes)
    import security        # noqa: F401  (registers ISU/ISSG routes)
    import orchestrate     # registers Workday Orchestrate
    import studio          # noqa: F401  (registers Workday Studio clone)
    import extend_app     # noqa: F401  (registers Workday Extend App Builder)
    import bp_orchestration   # noqa: F401  (registers BP-triggered orchestration flow)
    import sup_org   # noqa: F401  (registers Create Supervisory Organization + Human_Resources mock)
    print("Mock Workday tenant + UI -> http://127.0.0.1:8443/home")
    app.run(host="0.0.0.0", port=8443, threaded=True)
