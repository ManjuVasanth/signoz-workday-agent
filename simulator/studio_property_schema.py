"""
studio_property_schema.py
=========================
Schema-driven Properties panel for the mock Workday Studio canvas.

WHY THIS EXISTS
---------------
ONE place (COMPONENT_SCHEMA) defines every component's fields, their tabs, and
which ones accept MVEL. The panel renders from it; the engine asks it which
fields to resolve. Add a component, tab, or field = edit the dict, nothing else.

HOW TO EXTEND
-------------
1. Add/modify an entry in COMPONENT_SCHEMA using F(...).
2. Done. Panel shows it; engine resolves it if it is an MVEL field.

FIELD TYPES
-----------
  text          plain string
  mvel          string with @{...} interpolation, resolved at run time
  mvel_cond     MVEL boolean (Execute When / route condition)
  expr_list     eval-style rows:  props['key'] = <mvel expr>   (add/remove/reorder)
  select        dropdown / radio (uses options=[...])
  bool          checkbox
  textarea      multiline, NOT interpolated
  io_message    Input/Output row: (message|property) + name + optional MIME Type
  grid          column-defined grid with add/remove rows (uses columns=[...])

TABS
----
  Any tab name is allowed. Fields render grouped under their tab, in the order
  the tabs first appear. workday-in uses four: Common / Advanced /
  Launch Parameters / Services.

MVEL SURFACE (available inside mvel / mvel_cond / expr_list)
------------------------------------------------------------
  lp.getSimpleData('Label')                       -> String   (simple param)
  lp.getReferenceData('Label', 'Reference_ID_Type')          -> String
  lp.getReferenceData('Provider', 'Label', 'Reference_ID_Type') -> String
  lp.getReferenceDataList('Label', 'Type')        -> List<String>
  lp.getReferenceDataList('Provider', 'Label', 'Type') -> List<String>
  props['key']                                    read / write
  vars.<name>   or  @{vars.<name>}                integration variables
  intsys.reportService.getExtrapath('ReportAlias')
  doc                                             current document; doc.count('<wd:Report_Entry>')

  DEPRECATED ALIASES kept so old practice expressions still run:
  lp.getdate -> getSimpleData, lp.gettext -> getSimpleData,
  lp.getreferenceData -> getReferenceData

EXTRA PATH PROMPT SYNTAX (workday-out-rest)
-------------------------------------------
  ?format=simplexml
  &SimplePrompt=@{props['k']}
  &RefPrompt!Reference_ID_Type=@{props['k']}        (reference, e.g. Organization_Reference_ID)
  &RefPrompt!WID=@{props['k']}                      (by Workday ID)
"""

# ---------------------------------------------------------------------------
# Field helper + type registry
# ---------------------------------------------------------------------------

MVEL_FIELD_TYPES = {"mvel", "mvel_cond", "expr_list"}

# Canonical lp methods -> aliases the engine should also accept.
LP_ALIASES = {
    "getdate": "getSimpleData",
    "gettext": "getSimpleData",
    "getreferenceData": "getReferenceData",
}


def F(name, label, ftype="text", tab="Common", mvel=None, default="",
      options=None, placeholder="", help="", columns=None, mime=False):
    """Build one field. mvel defaults True for MVEL-capable types.
    columns: for grid -> [{"name","label","type"("text"|"select"|"mvel"),"options"}]
    mime:    for io_message -> show a MIME Type dropdown (use on Output)."""
    if mvel is None:
        mvel = ftype in MVEL_FIELD_TYPES
    return {
        "name": name, "label": label, "type": ftype, "tab": tab,
        "mvel": mvel, "default": default, "options": options or [],
        "placeholder": placeholder, "help": help,
        "columns": columns or [], "mime": mime,
    }


# ---------------------------------------------------------------------------
# THE SCHEMA  -- edit only this dict
# ---------------------------------------------------------------------------

COMPONENT_SCHEMA = {

    # ---- workday-in : four tabs (Image 4 + Image 8) -----------------------
    "workday-in": [
        F("service", "Integration Service", placeholder="Custom Studio Integration"),
        # Launch Parameters tab: Name / Type / (for reference) Class Report Field
        F("launch_parameters", "Launch Parameters", "grid", tab="Launch Parameters",
          columns=[
              {"name": "name", "label": "Name", "type": "text"},
              {"name": "type", "label": "Type", "type": "select",
               "options": ["text", "date", "reference"]},
              {"name": "crf", "label": "Class Report Field / Reference ID Type",
               "type": "text"},
          ],
          help="Read in eval: lp.getSimpleData('Name') or lp.getReferenceData('Name','Reference_ID_Type')."),
        # Services tab: the report-service grid
        F("services", "Services", "grid", tab="Services",
          columns=[
              {"name": "alias", "label": "Alias", "type": "text"},
              {"name": "description", "label": "Description", "type": "text"},
              {"name": "report_reference", "label": "Report Reference", "type": "text"},
          ],
          help="Alias maps to a report. Reference it via report_services in workday-out-rest."),
    ],

    # ---- workday-out-rest (Images 1, 2, 3 prior turn) ---------------------
    "workday-out-rest": [
        F("id", "Id", placeholder="CallReport"),
        F("routes_response_to", "Routes Response To",
          placeholder="next component id (e.g. Transform0)"),
        F("execute_when", "Execute When", "mvel_cond",
          placeholder="press ctrl-space for content assist",
          help="MVEL boolean. Step runs only when true. Blank = always."),
        F("extra_path", "Extra Path", "mvel",
          placeholder="@{intsys.reportService.getExtrapath('CRT_Demo_Manager')}?format=simplexml&Hire_Date=@{props['hiredate']}&Supervisory_Organization!Organization_Reference_ID=@{props['so']}",
          help="RaaS path. SimplePrompt=@{props['k']} ; RefPrompt!Reference_ID_Type=@{props['k']} ; RefPrompt!WID=@{props['k']}"),
        F("report", "Report", "text", "Advanced", placeholder="CRT_Demo_Manager"),
        F("format", "Format", "select", "Advanced",
          options=["xml", "simplexml", "json", "csv"], default="xml"),
    ],

    "workday-out-soap": [
        F("id", "Id", placeholder="RequestOTP"),
        F("service", "Service", placeholder="Compensation"),
        F("operation", "Operation", placeholder="Request_One_Time_Payment"),
        F("execute_when", "Execute When", "mvel_cond", "Advanced",
          placeholder="press ctrl-space for content assist"),
        F("request_body", "Request Field Expressions", "expr_list", "Advanced",
          help="props['Employee_ID'] = lp.getSimpleData('EmployeeID')"),
    ],

    "write": [
        F("filename", "File Name", "mvel", placeholder="output_@{vars.runId}.xml"),
        F("content", "Content", "mvel", "Advanced", placeholder="@{vars.document}"),
    ],

    # ---- Mediation containers --------------------------------------------
    "mediation": [
        F("id", "Id", placeholder="ProcessData"),
        F("on_error", "On Error", "select", options=["stop", "continue"], default="stop",
          help="SendError lane behaviour."),
    ],
    "async-mediation": [
        F("id", "Id", placeholder="AsyncMediation"),
        F("on_error", "On Error", "select", options=["stop", "continue"], default="stop"),
    ],

    # ---- eval (MVEL) : the centerpiece (Images 3, 4 prior turn) ----------
    "eval": [
        F("expressions", "Expressions", "expr_list",
          help="One assignment per row: props['hiredate'] = lp.getSimpleData('HireDate')"),
    ],

    # ---- xslt (Image 2 prior turn) : references external .xsl by Url ------
    "xslt": [
        F("id", "Step ID", placeholder="Xslt"),
        F("input", "Input", "io_message"),
        F("output", "Output", "io_message", mime=True),
        F("url", "Url", "text", placeholder="Wict_july_EIB.xsl",
          help="Path/reference to the stylesheet."),
        F("parameters", "Stylesheet Parameters", "expr_list", "Advanced",
          help="props['p1'] = vars.x  ->  passed in as <xsl:param>"),
    ],

    "copy": [
        F("source", "Source", "mvel", placeholder="XPath or @{...}"),
        F("target", "Target", "text"),
    ],
    "splitter": [F("split_expression", "Split Expression", "mvel", placeholder="//wd:Report_Entry")],
    "aggregator": [F("aggregate_expression", "Aggregate Expression", "mvel")],
    "csv-to-xml": [
        F("delimiter", "Delimiter", "text", default=","),
        F("has_header", "First Row Is Header", "bool", default=True),
        F("root_element", "Root Element", "text", "Advanced", placeholder="Report_Data"),
    ],
    "route": [
        F("condition", "Condition", "mvel_cond", placeholder="vars.totalWorkers > 0"),
        F("targets", "Branch Targets", "textarea", "Advanced", placeholder="one target id per line"),
    ],

    # ---- log : Common + Message Builder ----------------------------------
    "log": [
        F("id", "Step ID", placeholder="Log"),
        F("input", "Input", "io_message"),
        F("level", "Level", "select",
          options=["debug", "info", "warn", "error", "fatal"], default="info",
          help="Log4J level. Default is info."),
        F("message", "Message", "mvel", placeholder="Processed @{vars.totalWorkers} workers"),
        F("limit", "Limit", "text", "Advanced", default="0",
          help="Max chars logged. 0 = no limit."),
    ],

    "put-integration-message": [
        F("severity", "Severity", "select", options=["Info", "Warning", "Error"], default="Info"),
        F("message", "Message", "mvel", placeholder="Processed @{vars.totalWorkers} workers"),
    ],

    # ---- store : full Common set (Image 1) -------------------------------
    "store": [
        F("id", "Step ID", placeholder="Store"),
        F("input", "Input", "io_message"),
        F("output", "Output", "io_message", mime=True),
        F("collection", "Collection", "mvel", placeholder="press ctrl-space for content assist"),
        F("expires_in", "Expires In", "text", default="P7D",
          help="ISO-8601 duration. Default P7D (7 days)."),
        F("summary", "Summary", "mvel", "Advanced", placeholder="press ctrl-space for content assist"),
        F("title", "Title", "text", placeholder="Output.csv"),
        F("create_document_before", "Create Document Before", "bool", "Advanced", default=False),
    ],

    # ---- Error handlers ---------------------------------------------------
    "global-error-handler": [
        F("handler_type", "Handler Type", "select",
          options=["log-and-stop", "log-and-continue", "divert"], default="log-and-stop"),
    ],
    "log-error": [
        F("level", "Level", "select",
          options=["debug", "info", "warn", "error", "fatal"], default="error"),
        F("message", "Message", "mvel", placeholder="Failed: @{vars._lasterror}"),
    ],
    "send-error": [
        F("message", "Message", "mvel", placeholder="Integration failed: @{vars._lasterror}"),
        F("mark_failed", "Mark Failed", "bool", default=True),
    ],
    "route-retry": [
        F("max_retries", "Max Retries", "text", default="3"),
        F("condition", "Retry When", "mvel_cond", "Advanced", placeholder="vars.attempt < 3"),
    ],
}


# ---------------------------------------------------------------------------
# Lookups the ENGINE uses
# ---------------------------------------------------------------------------

def get_fields(component_type):
    return COMPONENT_SCHEMA.get(component_type, [])


def is_mvel_field(component_type, field_name):
    for f in get_fields(component_type):
        if f["name"] == field_name:
            return f["mvel"]
    return False


def mvel_fields(component_type):
    return [f["name"] for f in get_fields(component_type) if f["mvel"]]


def iter_mvel_values(component_type, values):
    """Yield (field_name, field_type, raw_value) for MVEL fields with a value.
    Engine resolves by type: expr_list -> run rows, mvel_cond -> bool, mvel -> @{}."""
    for f in get_fields(component_type):
        if not f["mvel"]:
            continue
        raw = (values or {}).get(f["name"], f["default"])
        if raw not in ("", None, []):
            yield f["name"], f["type"], raw


def normalize_lp_call(expr):
    """Rewrite deprecated lp aliases to canonical names before evaluating."""
    for old, new in LP_ALIASES.items():
        expr = expr.replace("lp." + old, "lp." + new)
    return expr


def tabs_for(component_type):
    """Distinct tab names in first-seen order."""
    seen = []
    for f in get_fields(component_type):
        if f["tab"] not in seen:
            seen.append(f["tab"])
    return seen


# ---------------------------------------------------------------------------
# Render layer -- emits the panel HTML from the schema (multi-tab)
# ---------------------------------------------------------------------------

MIME_OPTIONS = ["MIME Type", "text/xml", "application/json", "text/csv", "text/plain"]


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _render_field(f, value):
    t, name = f["type"], f["name"]
    val = value if value is not None else f["default"]
    title = _esc(f["help"]) if f["help"] else ""
    badge = '<span class="wd-mvel-badge" title="Accepts MVEL">MVEL</span>' if f["mvel"] else ""
    label = f'<div class="wd-prop-label" title="{title}">{_esc(f["label"])} {badge}</div>'

    if t == "select":
        opts = "".join(
            f'<option value="{_esc(o)}"{" selected" if str(o)==str(val) else ""}>{_esc(o)}</option>'
            for o in f["options"])
        ctrl = f'<select class="wd-prop-input" name="{name}">{opts}</select>'

    elif t == "bool":
        checked = "checked" if val in (True, "true", "True", "1", 1) else ""
        ctrl = f'<input type="checkbox" class="wd-prop-check" name="{name}" {checked}>'

    elif t == "textarea":
        ctrl = (f'<textarea class="wd-prop-input wd-prop-area" name="{name}" '
                f'placeholder="{_esc(f["placeholder"])}">{_esc(val)}</textarea>')

    elif t == "io_message":
        v = val if isinstance(val, dict) else {}
        kind = v.get("kind", "message")
        kopts = "".join(
            f'<option value="{k}"{" selected" if k==kind else ""}>{k}</option>'
            for k in ("message", "property"))
        mime_sel = ""
        if f["mime"]:
            cur = v.get("mime", "MIME Type")
            mopts = "".join(
                f'<option value="{_esc(m)}"{" selected" if m==cur else ""}>{_esc(m)}</option>'
                for m in MIME_OPTIONS)
            mime_sel = f'<select class="wd-prop-input wd-io-mime">{mopts}</select>'
        ctrl = (f'<div class="wd-io" data-name="{name}">'
                f'<select class="wd-prop-input wd-io-kind">{kopts}</select>'
                f'<input class="wd-prop-input wd-io-name" value="{_esc(v.get("name",""))}">'
                f'{mime_sel}</div>')

    elif t == "expr_list":
        rows = val if isinstance(val, list) else (
            [r for r in str(val).splitlines() if r.strip()] if val else [])
        if not rows:
            rows = [""]
        row_html = "".join(
            f'''<div class="wd-expr-row">
              <input class="wd-prop-input wd-expr-input" value="{_esc(r)}"
                     placeholder="props['key'] = lp.getSimpleData('Param')">
              <button class="wd-expr-up" title="move up">&#9650;</button>
              <button class="wd-expr-dn" title="move down">&#9660;</button>
              <button class="wd-expr-rm" title="remove">&#10006;</button>
            </div>''' for r in rows)
        ctrl = (f'<div class="wd-expr-list" data-name="{name}">{row_html}'
                f'<button class="wd-expr-add">+ Add expression</button></div>')

    elif t == "grid":
        cols = f["columns"]
        head = "".join(f'<th>{_esc(c["label"])}</th>' for c in cols) + "<th></th>"

        def cell(c, cval):
            if c.get("type") == "select":
                o = "".join(
                    f'<option value="{_esc(x)}"{" selected" if str(x)==str(cval) else ""}>{_esc(x)}</option>'
                    for x in c.get("options", []))
                return f'<td><select class="wd-grid-cell" data-col="{c["name"]}">{o}</select></td>'
            return (f'<td><input class="wd-grid-cell" data-col="{c["name"]}" '
                    f'value="{_esc(cval)}"></td>')

        rows = val if isinstance(val, list) else []
        if not rows:
            rows = [{}]
        body = ""
        for r in rows:
            cells = "".join(cell(c, (r or {}).get(c["name"], "")) for c in cols)
            body += f'<tr class="wd-grid-row">{cells}<td><button class="wd-grid-rm" title="remove">&#10006;</button></td></tr>'
        ctrl = (f'<div class="wd-grid" data-name="{name}">'
                f'<table class="wd-grid-table"><thead><tr>{head}</tr></thead>'
                f'<tbody>{body}</tbody></table>'
                f'<button class="wd-grid-add">+ Add row</button></div>')

    else:  # text, mvel, mvel_cond
        ctrl = (f'<input class="wd-prop-input" name="{name}" '
                f'value="{_esc(val)}" placeholder="{_esc(f["placeholder"])}">')

    return f'<div class="wd-prop-row" data-type="{t}">{label}<div class="wd-prop-ctrl">{ctrl}</div></div>'


def render_properties_html(component_type, values=None):
    values = values or {}
    fields = get_fields(component_type)
    if not fields:
        return (f'<div class="wd-props"><div class="wd-prop-title">{_esc(component_type)}</div>'
                f'<div class="wd-prop-empty">No editable properties.</div></div>')

    tabs = tabs_for(component_type)
    tab_buttons = "".join(
        f'<button class="wd-tab{" active" if i==0 else ""}" data-tab="{_esc(tb)}">{_esc(tb)}</button>'
        for i, tb in enumerate(tabs))

    panes = ""
    for i, tb in enumerate(tabs):
        rows = "".join(_render_field(f, values.get(f["name"]))
                       for f in fields if f["tab"] == tb)
        hidden = "" if i == 0 else " hidden"
        panes += f'<div class="wd-tabpane" data-pane="{_esc(tb)}"{hidden}>{rows}</div>'

    return (f'<div class="wd-props" data-component="{_esc(component_type)}">'
            f'<div class="wd-prop-title">{_esc(component_type)}</div>'
            f'<div class="wd-prop-tabs">{tab_buttons}</div>{panes}</div>')


# ---------------------------------------------------------------------------
# Flask wiring
# ---------------------------------------------------------------------------

def register_studio_properties(app):
    """Register where you register orchestrate.py. Adds:
       GET /studio/schema                 -> full schema JSON (client render)
       GET /studio/properties/<ctype>     -> ready HTML panel (server render)"""
    from flask import jsonify, request
    import json

    @app.route("/studio/schema")
    def _studio_schema():
        return jsonify(COMPONENT_SCHEMA)

    @app.route("/studio/properties/<ctype>")
    def _studio_props(ctype):
        raw = request.args.get("values")
        vals = json.loads(raw) if raw else {}
        return render_properties_html(ctype, vals)

    return app


# Self-register on import if a shared app exists (mirror your other modules).
try:
    from workday_ui import app as _app  # adjust if your app object lives elsewhere
    register_studio_properties(_app)
except Exception:
    pass
