# -*- coding: utf-8 -*-
"""
orchestrate.py  --  Workday Orchestrate clone for the mock-workday tenant.

Replicates the real developer.workday.com Orchestration Builder plus the
end-to-end lifecycle:

  Developer Site  ->  Build an Integration App  ->  add Orchestration
  ->  Orchestration Builder (Trigger -> Send RaaS -> Store Document -> End)
  ->  Validate  ->  Build  ->  Deploy to tenant
  ->  Tenant: View Integration System (Orchestrate template)
  ->  Launch / Schedule Integration (Run Now)
  ->  View Background Process  ->  Output Files  ->  RAAS DATA (.txt)

INSTALL
-------
1. Drop this file next to workday_ui.py.
2. In workday_ui.py, inside the `if __name__ == "__main__":` block, add ONE line
   next to your other `import core_connector` / `import security` lines:

       import orchestrate     # noqa: F401  (registers Workday Orchestrate)

3. Restart, Ctrl+F5, then open:  http://127.0.0.1:8443/orchestrate
   (or type "Orchestrate" in the tenant search bar)

Self-contained: only needs Flask + the `app` object from workday_ui.
"""

import os
import re
import ast
import json
import time
import random
import string
import datetime
import urllib.request
import urllib.error
import urllib.parse

from flask import request, Response

import workday_ui as wd            # the running app aliases itself in __main__
app = wd.app

# --- OpenTelemetry instrumentation (Agents of SigNoz hackathon) ---
import logging
from opentelemetry import trace as otel_trace
from opentelemetry.trace import Status, StatusCode

_tracer = otel_trace.get_tracer("orchestration")
_orch_logger = logging.getLogger("orchestration")
_orch_logger.setLevel(logging.INFO)

# show up in the tenant task search bar
try:
    if not any(t.get("url") == "/orchestrate" for t in wd.TASKS):
        wd.TASKS.append({"name": "Workday Orchestrate", "url": "/orchestrate"})
except Exception:
    pass

STORE = "orchestrate_store.json"

# ===========================================================================
# Sample RaaS dataset (what "Send Workday RaaS Request" returns)
# ===========================================================================
RAAS_ROWS = [
    {"Employee_ID": "21001", "Worker": "Logan McNeil",  "Manager": "Joy Banks",
     "Org": "Engineering", "Email": "lmcneil@corp.com"},
    {"Employee_ID": "21002", "Worker": "Priya Menon",   "Manager": "Logan McNeil",
     "Org": "Finance",     "Email": "pmenon@corp.com"},
    {"Employee_ID": "21003", "Worker": "Diego Reyes",   "Manager": "Logan McNeil",
     "Org": "Sales",       "Email": "dreyes@corp.com"},
    {"Employee_ID": "21004", "Worker": "Mei Lin",       "Manager": "Logan McNeil",
     "Org": "Engineering", "Email": "mlin@corp.com"},
    {"Employee_ID": "21005", "Worker": "Omar Haddad",   "Manager": "Logan McNeil",
     "Org": "HR",          "Email": "ohaddad@corp.com"},
]

TENANTS = ["wday_wcpdev40", "wday_wcpdev41", "wday_wcpdev42", "wday_wcpdev43",
           "wday_wcpdev47", "wday_wcpdev48", "wday_wcpdev49", "wday_wcpdev5"]


def _ref_suffix():
    return "".join(random.choice(string.ascii_lowercase) for _ in range(6))


def seed():
    return {
        "apps": {
            "raas_nkzjqw": {
                "id": "raas_nkzjqw",
                "name": "raas",
                "refId": "raas_nkzjqw",
                "appId": "a39edc955766c3c20a4bb48edeafce06",
                "description": "--",
                "created": "04/24/2026",
                "createdBy": "Tony Gilfillan",
                "orchestrations": {
                    "raas": {
                        "name": "raas",
                        "type": "Workday Integration System",
                        "startType": "integration",
                        "lastBuild": None,
                        "steps": [
                            {
                                "id": "s_raas",
                                "type": "send-workday-raas-request",
                                "ref": "SendWorkdayRaaSRequest",
                                "props": {
                                    "method": "GET",
                                    "urlPrefix": "http://127.0.0.1:8443/task/view-report?name=",
                                    "path": "CRT_INT01_Raas",
                                    "auth": "Default Workday API Credential",
                                    "contentType": "Any",
                                },
                            },
                            {
                                "id": "s_store",
                                "type": "store-document",
                                "ref": "StoreDocument",
                                "props": {
                                    "documentToStore": [{"t": "ref", "v": "SendWorkdayRaaSRequest.response"}],
                                    "documentTitle": [{"t": "string", "v": "RAAS DATA"}],
                                    "description": [],
                                    "collection": [],
                                    "expiresIn": "7",
                                    "expiresUnit": "Days",
                                    "attachToEvent": "true",
                                    "deliver": "false",
                                },
                            },
                        ],
                    },
                    "Looping": {
                        "name": "Looping",
                        "type": "Synchronous",
                        "startType": "synchronous",
                        "lastBuild": None,
                        "steps": [
                            {
                                "id": "s_ctt",
                                "type": "create-text-template",
                                "ref": "CreateTextTemplate",
                                "props": {
                                    "contentType": "application/json",
                                    "message": ('{\n  "company": {\n    "employees": [\n'
                                                '      {"id":101,"name":"Sarah Connor","role":"Manager","department":"Operations","active":true},\n'
                                                '      {"id":102,"name":"James Howlett","role":"Security Specialist","department":"Security","active":true},\n'
                                                '      {"id":103,"name":"Diana Prince","role":"Legal Consultant","department":"Legal","active":false},\n'
                                                '      {"id":104,"name":"Tony Stark","role":"Lead Engineer","department":"R&D","active":true}\n'
                                                '    ]\n  }\n}'),
                                },
                            },
                            {
                                "id": "s_loop",
                                "type": "loop",
                                "ref": "Loop",
                                "props": {
                                    "dataType": "AutoType Iterator",
                                    "dataSetRef": "CreateTextTemplate.message",
                                    "dataSetPath": "$.company.employees[*]",
                                    "filterPath": "$.active",
                                    "sortBy": [{"path": "$.role", "dir": "asc"}],
                                    "locale": "",
                                },
                                "body": [
                                    {
                                        "id": "s_log",
                                        "type": "log",
                                        "ref": "Log",
                                        "props": {"messageRef": "Loop.item", "messageFn": "toString",
                                                  "condition": "true"},
                                    }
                                ],
                                "aggregation": {
                                    "ref": "Aggregate",
                                    "outputs": [{"name": "ActiveUsers", "strategy": "JSON"}],
                                    "failWhenNoInputs": False,
                                    "earlyStop": None,
                                    "errorHandler": False,
                                    "deleted": False,
                                },
                            },
                        ],
                    },
                },
            },
            "stock_app": {
                "id": "stock_app",
                "name": "StockNotifications",
                "refId": "stock_app",
                "appId": "6f4026e444f4f3f37ac1d53d4a63a298",
                "description": "Retrieve stock prices from an external API",
                "created": "06/27/2026",
                "createdBy": "Tony Gilfillan",
                "orchestrations": {
                    "StockRetrieval": {
                        "name": "StockRetrieval",
                        "type": "Synchronous",
                        "startType": "synchronous",
                        "lastBuild": None,
                        "steps": [
                            {
                                "id": "s_http",
                                "type": "send-http-request",
                                "ref": "SendHTTPRequest",
                                "props": {
                                    "method": "GET",
                                    "url": "http://127.0.0.1:8443/orchestrate/mock-api/stock",
                                    "auth": "No Auth",
                                    "advancedMode": False,
                                    "queryParams": [
                                        {"key": "ticker", "value": "AAPL"},
                                        {"key": "apiKey", "value": "demo"},
                                    ],
                                },
                            },
                            {
                                "id": "s_cv",
                                "type": "create-values",
                                "ref": "CreateValues",
                                "props": {
                                    "values": [
                                        {"name": "Ticker", "sourceRef": "SendHTTPRequest.response",
                                         "jsonPath": "$.results[0].T"},
                                        {"name": "OpenPrice", "sourceRef": "SendHTTPRequest.response",
                                         "jsonPath": "$.results[0].o"},
                                        {"name": "ClosePrice", "sourceRef": "SendHTTPRequest.response",
                                         "jsonPath": "$.results[0].c"},
                                    ],
                                },
                            },
                            {
                                "id": "s_log2",
                                "type": "log",
                                "ref": "Log",
                                "props": {"messageRef": "CreateValues.OpenPrice", "condition": "true"},
                            },
                        ],
                    },
                },
            },
            "hackathon_app": {
                "id": "hackathon_app",
                "name": "HackathonTickets",
                "refId": "hackathontickets_svfbfp",
                "appId": "5d5ed13bc9cfee28a9ec1bc9369ebeef",
                "description": "Hackathon ticket registration app",
                "created": "02/24/2026",
                "createdBy": "Tony Gilfillan",
                "orchestrations": {
                    "AddUserToSlack": {
                        "name": "AddUserToSlack",
                        "type": "Synchronous Orchestration",
                        "startType": "synchronous",
                        "lastBuild": None,
                        "steps": [
                            {"id": "s_log", "type": "log", "ref": "Log",
                             "props": {"message": "USER ADDED - ORCHESTRATION HIT", "condition": "true"}},
                        ],
                    },
                    "AddUserBPTrigger": {
                        "name": "AddUserBPTrigger",
                        "type": "Workday Business Process",
                        "startType": "business-process",
                        "lastBuild": None,
                        "steps": [
                            {"id": "s_log", "type": "log", "ref": "Log",
                             "props": {"message": "ADD USER _ BP TRIGGER", "condition": "true"}},
                        ],
                    },
                },
            },
            "suporg_app": {
                "id": "suporg_app",
                "name": "SupOrgManagement",
                "refId": "suporgmanagement_svfbfp",
                "appId": "7a1c0e9b2d4f46a8b3c5d7e9f1a2b3c4",
                "description": "Create Supervisory Organizations via Add_Update_Organization",
                "created": "06/29/2026",
                "createdBy": "Vasanth",
                "orchestrations": {
                    "CreateSupOrg": {
                        "name": "CreateSupOrg",
                        "type": "Synchronous Orchestration",
                        "startType": "synchronous",
                        "lastBuild": None,
                        "steps": [
                            # 1+2  receive input (Input.*) + validate required fields
                            {"id": "s_val", "type": "create-values", "ref": "ValidateInput",
                             "props": {"values": [
                                 {"name": "code", "sourceRef": "Input", "jsonPath": "$.SupOrgCode"},
                                 {"name": "name", "sourceRef": "Input", "jsonPath": "$.SupOrgName"},
                             ]}},
                            # 3  check if Sup Org code already exists
                            {"id": "s_chk", "type": "send-http-request", "ref": "CheckExists",
                             "props": {"method": "GET", "auth": "No Auth",
                                       "url": "http://127.0.0.1:8443/tenant/soap/human_resources/exists",
                                       "queryParams": [{"key": "code", "value": "{Input.SupOrgCode}"}]}},
                            # 4  read the exists flag
                            {"id": "s_exists", "type": "create-values", "ref": "Existence",
                             "props": {"values": [
                                 {"name": "exists", "sourceRef": "CheckExists.response", "jsonPath": "$.exists"},
                             ]}},
                            # 5  build the SOAP request payload (Add_Update_Organization)
                            {"id": "s_soap", "type": "create-text-template", "ref": "BuildSoapPayload",
                             "props": {"contentType": "text/xml", "message": (
                                 '<?xml version="1.0" encoding="UTF-8"?>\n'
                                 '<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/" '
                                 'xmlns:wd="urn:com.workday/bsvc">\n'
                                 '  <env:Body>\n'
                                 '    <wd:Add_Update_Organization_Request wd:version="v43.0">\n'
                                 '      <wd:Organization_Data>\n'
                                 '        <wd:Organization_Code>{Input.SupOrgCode}</wd:Organization_Code>\n'
                                 '        <wd:Organization_Name>{Input.SupOrgName}</wd:Organization_Name>\n'
                                 '        <wd:Organization_Type_Reference>Supervisory</wd:Organization_Type_Reference>\n'
                                 '        <wd:Organization_Subtype_Reference>{Input.OrgSubtype}</wd:Organization_Subtype_Reference>\n'
                                 '        <wd:Availability_Date>{Input.AvailabilityDate}</wd:Availability_Date>\n'
                                 '        <wd:Include_Manager_in_Name>true</wd:Include_Manager_in_Name>\n'
                                 '        <wd:Superior_Organization_Reference>{Input.SuperiorOrg}</wd:Superior_Organization_Reference>\n'
                                 '        <wd:Staffing_Model>{Input.StaffingModel}</wd:Staffing_Model>\n'
                                 '        <wd:Location_Reference>{Input.PrimaryLocation}</wd:Location_Reference>\n'
                                 '        <wd:Manager_Reference>{Input.Manager}</wd:Manager_Reference>\n'
                                 '      </wd:Organization_Data>\n'
                                 '    </wd:Add_Update_Organization_Request>\n'
                                 '  </env:Body>\n</env:Envelope>')}},
                            # 6+7  call Human_Resources / Add_Update_Organization, capture response
                            {"id": "s_call", "type": "send-http-request", "ref": "CallHumanResources",
                             "props": {"method": "POST", "auth": "Default Workday API Credential",
                                       "contentType": "text/xml",
                                       "url": "http://127.0.0.1:8443/tenant/soap/human_resources",
                                       "bodyRef": "BuildSoapPayload.message"}},
                            {"id": "s_cap", "type": "create-values", "ref": "Result",
                             "props": {"values": [
                                 {"name": "orgRef", "sourceRef": "CallHumanResources.response",
                                  "jsonPath": "$.Organization_Reference"},
                                 {"name": "status", "sourceRef": "CallHumanResources.response", "jsonPath": "$.status"},
                                 {"name": "message", "sourceRef": "CallHumanResources.response", "jsonPath": "$.message"},
                             ]}},
                            # 8  return success/error message
                            {"id": "s_log", "type": "log", "ref": "Log",
                             "props": {"messageRef": "Result.message", "condition": "true"}},
                        ],
                    },
                },
            },
        },
        "builds": [],
        "deployments": [],
        "integration_systems": {},
        "bg_processes": {},
        "output_files": {},
        "counters": {"build": 2, "bp": 0, "of": 0, "is": 0},
    }


def load():
    if not os.path.exists(STORE):
        save(seed())
    try:
        with open(STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return seed()


def save(data):
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def esc(t):
    return (str(t) if t is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ===========================================================================
# Self-contained mock stock API
# Gives "Send HTTP Request" a live JSON endpoint to hit with no external key.
# Shape mirrors Polygon.io so JSON paths match real practice
# ($.results[0].o = open, .c = close, .h/.l = high/low, .v = volume).
# Swap the orchestration URL to a real API anytime; the engine GETs either way.
# ===========================================================================
_STOCK_SEED = {
    "AAPL": {"o": 189.33, "h": 192.10, "l": 188.50, "c": 191.24, "v": 54213400},
    "MSFT": {"o": 421.05, "h": 425.66, "l": 419.80, "c": 424.12, "v": 19872300},
    "TSLA": {"o": 245.10, "h": 251.44, "l": 243.02, "c": 249.88, "v": 88345100},
    "NVDA": {"o": 121.40, "h": 124.95, "l": 120.10, "c": 123.77, "v": 301244500},
}


@app.route("/orchestrate/mock-api/stock")
def mock_stock_api():
    ticker = (request.args.get("ticker") or "AAPL").upper()
    base = _STOCK_SEED.get(ticker, _STOCK_SEED["AAPL"])
    jitter = lambda x: round(x * (1 + random.uniform(-0.01, 0.01)), 2)  # noqa: E731
    payload = {
        "status": "OK",
        "request_id": _ref_suffix(),
        "ticker": ticker,
        "results": [{
            "T": ticker,
            "o": jitter(base["o"]),
            "h": jitter(base["h"]),
            "l": jitter(base["l"]),
            "c": jitter(base["c"]),
            "v": base["v"],
            "t": int(time.time() * 1000),
        }],
    }
    return Response(json.dumps(payload), mimetype="application/json")


# ===========================================================================
# Engine (executes an orchestration; used by Run and by tenant Launch)
# ===========================================================================
def resolve_tokens(tokens, ctx):
    """Concatenate a token list ([{t:string|ref, v}]) into a value/string."""
    if not tokens:
        return ""
    parts = []
    for tok in tokens:
        if tok.get("t") == "ref":
            parts.append(get_path(ctx, tok.get("v", "")))
        else:
            parts.append(tok.get("v", ""))
    if len(parts) == 1:
        return parts[0]
    return "".join(str(p) for p in parts)


def get_path(ctx, path):
    cur = ctx
    for key in str(path).split("."):
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            return None
    return cur


def fetch_report(full_url):
    """GET the configured report URL and parse whatever comes back.
    Works against the user's own tenant (e.g. http://127.0.0.1:8443/task/view-report?name=...)
    or any external RaaS endpoint. Never hardcodes data."""
    if not full_url or not str(full_url).lower().startswith(("http://", "https://")):
        return {"response": {"error": "No valid URL configured"}, "responseStatusCode": 0,
                "responseHeaders": {}, "error": "No valid URL configured"}
    try:
        req = urllib.request.Request(full_url, headers={"User-Agent": "WorkdayOrchestrate/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode("utf-8", "replace")
            ct = r.headers.get("Content-Type", "")
            return {"response": parse_report(body), "responseStatusCode": getattr(r, "status", 200),
                    "responseHeaders": {"Content-Type": ct}}
    except urllib.error.HTTPError as e:
        return {"response": {"error": "HTTP %s" % e.code}, "responseStatusCode": e.code,
                "responseHeaders": {}, "error": "HTTP %s" % e.code}
    except Exception as e:
        return {"response": {"error": str(e)}, "responseStatusCode": 0,
                "responseHeaders": {}, "error": str(e)}


def subst(text, ctx):
    """Replace {Some.Path} tokens in a string with values pulled from ctx.
    Tightly scoped to {Word.Word} so JSON/XML braces are never touched."""
    if not isinstance(text, str):
        return text

    def _r(m):
        v = get_path(ctx, m.group(1))
        return str(v) if v is not None else m.group(0)
    return re.sub(r"\{([A-Za-z0-9_.]+)\}", _r, text)


def http_send(url, method, body, content_type="application/json"):
    """POST/PUT/PATCH/DELETE with a request body (SOAP or JSON)."""
    if not url or not str(url).lower().startswith(("http://", "https://")):
        return {"response": {"error": "No valid URL configured"}, "responseStatusCode": 0,
                "responseHeaders": {}, "error": "No valid URL configured"}
    try:
        data = (body or "").encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"User-Agent": "WorkdayOrchestrate/1.0",
                                              "Content-Type": content_type})
        with urllib.request.urlopen(req, timeout=10) as r:
            txt = r.read().decode("utf-8", "replace")
            ct = r.headers.get("Content-Type", "")
            return {"response": parse_report(txt), "responseStatusCode": getattr(r, "status", 200),
                    "responseHeaders": {"Content-Type": ct}}
    except urllib.error.HTTPError as e:
        try:
            txt = e.read().decode("utf-8", "replace")
        except Exception:
            txt = ""
        return {"response": parse_report(txt) if txt else {"error": "HTTP %s" % e.code},
                "responseStatusCode": e.code, "responseHeaders": {}, "error": "HTTP %s" % e.code}
    except Exception as e:
        return {"response": {"error": str(e)}, "responseStatusCode": 0,
                "responseHeaders": {}, "error": str(e)}


def parse_report(body):
    """Turn a report response into structured rows when possible."""
    b = (body or "").strip()
    if not b:
        return []
    if b[:1] in "[{":
        try:
            return json.loads(b)
        except Exception:
            pass
    if "<table" in b.lower():
        rows = extract_html_table(b)
        if rows:
            return rows
    if "<" not in b[:300] and ("\n" in b) and ("," in b or "\t" in b):
        return parse_delimited(b)
    return b  # raw text


def extract_html_table(html):
    m = re.search(r"<table.*?</table>", html, re.I | re.S)
    if not m:
        return []
    trs = re.findall(r"<tr.*?</tr>", m.group(0), re.I | re.S)
    headers, rows = [], []
    for tr in trs:
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.I | re.S)
        cells = [re.sub(r"<[^>]+>", "", c).replace("&nbsp;", " ").strip() for c in cells]
        if not cells:
            continue
        if not headers:
            headers = cells
        else:
            rows.append(dict(zip(headers, cells)))
    return rows


def parse_delimited(text):
    import csv
    import io
    delim = "\t" if "\t" in text.splitlines()[0] else ","
    return list(csv.DictReader(io.StringIO(text), delimiter=delim))


def jsonpath(data, path):
    """Minimal JSONPath: $.a.b[*].c , $.x , [n]."""
    if data is None:
        return None
    p = (path or "").strip()
    if p.startswith("$"):
        p = p[1:]
    cur = [data]; multi = False
    for key, idx in re.findall(r"\.([A-Za-z0-9_]+)|\[(\*|\d+)\]", p):
        nxt = []
        for node in cur:
            if key and isinstance(node, dict):
                nxt.append(node.get(key))
            elif idx == "*" and isinstance(node, list):
                nxt.extend(node); multi = True
            elif idx.isdigit() and isinstance(node, list) and int(idx) < len(node):
                nxt.append(node[int(idx)])
        cur = nxt
    if multi:
        return cur
    return cur[0] if len(cur) == 1 else cur


def truthy(v):
    if isinstance(v, str):
        return v.strip().lower() not in ("", "false", "0", "none", "null")
    return bool(v)


def run_orchestration(orch, trigger_label="Run", inputs=None):
    ctx = {"Input": inputs or {}}
    trace = []
    out_files = []
    status = "Completed"
    error = None
    t0 = time.time()

    def log(step, typ, msg, st="Completed"):
        trace.append({"step": step, "type": typ, "status": st, "message": msg})
        span = otel_trace.get_current_span()
        span.add_event(msg, {"step.ref": str(step), "step.status": st})
        if st == "Error":
            span.set_status(Status(StatusCode.ERROR, msg))
            _orch_logger.error("[%s|%s] %s", step, typ, msg)
        else:
            _orch_logger.info("[%s|%s] %s", step, typ, msg)

    def exec_steps(steps, depth=0):
        for i, s in enumerate(steps, start=1):
            typ = s.get("type", "unknown")
            ref = s.get("ref", typ)
            if depth == 0:
                span_name = "step-%02d.%s.%s" % (i, typ, ref)
            else:
                span_name = "%s.%s" % (typ, ref)
            with _tracer.start_as_current_span(span_name) as span:
                span.set_attribute("step.index", i)
                span.set_attribute("step.depth", depth)
                span.set_attribute("step.type", str(typ))
                span.set_attribute("step.ref", str(ref))
                if s.get("inject"):
                    span.set_attribute("chaos.injected", str(s.get("inject")))
                try:
                    exec_one(s, depth)
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

    def run_loop(s, depth):
        ref = s.get("ref", "Loop")
        p = s.get("props", {}) or {}
        src = get_path(ctx, p.get("dataSetRef", "")) if p.get("dataSetRef") else None
        items = jsonpath(src, p.get("dataSetPath", "")) if p.get("dataSetPath") else src
        if not isinstance(items, list):
            items = [items] if items is not None else []
        fp = p.get("filterPath", "")
        if fp:
            items = [it for it in items if truthy(jsonpath(it, fp))]
        for sb in (p.get("sortBy") or []):
            sp = sb.get("path", "")
            if sp:
                try:
                    items = sorted(items, key=lambda it: (jsonpath(it, sp) is None, jsonpath(it, sp)),
                                   reverse=(sb.get("dir") == "desc"))
                except Exception:
                    pass
        log(ref, "Loop", "iterating %d item(s)" % len(items))
        agg = s.get("aggregation") or {}
        do_agg = bool(agg) and not agg.get("deleted")
        collected = {o["name"]: [] for o in (agg.get("outputs") or [])} if do_agg else {}
        for i, it in enumerate(items):
            ctx["Loop"] = {"item": it, "index": i}
            ctx[ref] = {"item": it, "index": i}
            # Early Stop condition (optional)
            es = agg.get("earlyStop") if do_agg else None
            if es and truthy(jsonpath(it, es)):
                log(ref, "Loop", "early stop at item %d" % i)
                break
            exec_steps(s.get("body", []), depth + 1)
            for name in collected:
                collected[name].append(it)
        if do_agg:
            aref = agg.get("ref", "Aggregate")
            result = {}
            for o in (agg.get("outputs") or []):
                vals = collected.get(o["name"], [])
                strat = o.get("strategy", "JSON")
                if strat == "Text":
                    result[o["name"]] = "\n".join(str(v) for v in vals)
                elif strat == "Count":
                    result[o["name"]] = len(vals)
                else:
                    result[o["name"]] = vals
            ctx[aref] = result
            if agg.get("failWhenNoInputs") and not items:
                raise ValueError("Aggregate '%s': no inputs" % aref)
            summary = " | ".join("%s=%s(%d)" % (o["name"], o.get("strategy", "JSON"),
                      len(collected.get(o["name"], []))) for o in (agg.get("outputs") or []))
            log(aref, "Aggregate", summary or "no outputs")

    def exec_one(s, depth=0):
        typ = s.get("type")
        ref = s.get("ref", typ)
        p = s.get("props", {}) or {}

        if typ == "send-workday-raas-request":
            prefix = p.get("urlPrefix", "") or ""
            path = p.get("path", "")
            if isinstance(path, list):
                path = resolve_tokens(path, ctx)
            full_url = prefix + str(path or "")
            res = fetch_report(full_url)
            ctx[ref] = {"response": res["response"], "responseHeaders": res["responseHeaders"],
                        "responseStatusCode": res["responseStatusCode"]}
            if res.get("error"):
                log(ref, typ, "GET %s -> ERROR: %s" % (full_url, res["error"]), "Error")
            else:
                n = len(res["response"]) if isinstance(res["response"], list) else None
                log(ref, typ, "GET %s -> %s%s" % (full_url, res["responseStatusCode"],
                    (" (%d rows)" % n) if n is not None else " (data)"))

        elif typ == "send-http-request":
            url = p.get("url", "") or ""
            if isinstance(url, list):
                url = resolve_tokens(url, ctx)
            url = subst(str(url), ctx)
            method = (p.get("method", "GET") or "GET").upper()
            # append Query Parameters (Key/Value pairs) to the URL
            pairs = []
            for q in (p.get("queryParams") or []):
                k = (q.get("key") or "").strip()
                v = q.get("value", "")
                if isinstance(v, list):
                    v = resolve_tokens(v, ctx)
                v = subst(str(v), ctx)
                if k:
                    pairs.append("%s=%s" % (urllib.parse.quote(k), urllib.parse.quote(v)))
            if pairs:
                url = url + ("&" if "?" in url else "?") + "&".join(pairs)
            if method == "GET":
                res = fetch_report(url)
            else:
                # body can come from a step ref (bodyRef), a token list, or a literal
                if p.get("bodyRef"):
                    body = get_path(ctx, p.get("bodyRef"))
                elif isinstance(p.get("body"), list):
                    body = resolve_tokens(p.get("body"), ctx)
                else:
                    body = subst(p.get("body", "") or "", ctx)
                if isinstance(body, (dict, list)):
                    body = json.dumps(body)
                res = http_send(url, method, str(body if body is not None else ""),
                                p.get("contentType", "application/json"))
            ctx[ref] = {"response": res["response"], "responseHeaders": res["responseHeaders"],
                        "responseStatusCode": res["responseStatusCode"]}
            if res.get("error"):
                log(ref, typ, "%s %s -> ERROR: %s" % (method, url, res["error"]), "Error")
            else:
                log(ref, typ, "%s %s -> %s" % (method, url, res["responseStatusCode"]))

        elif typ in ("send-paged-http-request", "send-workday-api-request",
                     "send-paged-workday-rest-call", "send-paged-workday-soap-call", "send-prism-request"):
            ctx[ref] = {"response": {"ok": True}, "responseStatusCode": 200}
            log(ref, typ, "request sent -> 200")

        elif typ == "store-document":
            doc = resolve_tokens(p.get("documentToStore", []), ctx)
            title = resolve_tokens(p.get("documentTitle", []), ctx) or "Document"
            body = render_txt(doc) if isinstance(doc, (list, dict)) else str(doc)
            out_files.append({"title": title, "type": "Text Document (TXT)", "body": body})
            log(ref, typ, "stored '%s' (%d bytes)" % (title, len(body)))

        elif typ == "create-text-template":
            msg = subst(p.get("message", "") or "", ctx)
            try:
                val = json.loads(msg) if msg.strip()[:1] in "[{" else msg
            except Exception:
                val = msg
            ctx[ref] = {"message": val, "contentType": p.get("contentType", "application/json")}
            log(ref, typ, "text template created (%s)" % p.get("contentType", ""))

        elif typ in ("create-values", "create-json"):
            out = {}
            for v in (p.get("values") or []):
                name = v.get("name") or "value"
                src = get_path(ctx, v.get("sourceRef", "")) if v.get("sourceRef") else None
                out[name] = jsonpath(src, v.get("jsonPath", "")) if v.get("jsonPath") else src
            if out and "value" not in out:
                out["value"] = next(iter(out.values()))
            ctx[ref] = out or {"value": None}
            summ = ", ".join("%s=%s" % (k, out[k]) for k in out if k != "value")
            log(ref, typ, "extracted " + (summ or "(no mappings)"))

        elif typ == "validate":
            log(ref, typ, "validation passed")

        elif typ in ("loop", "batch-loop", "join-loop"):
            run_loop(s, depth)

        elif typ == "log":
            cond = p.get("condition", "true")
            if truthy(cond):
                if p.get("messageRef"):
                    val = get_path(ctx, p.get("messageRef"))
                else:
                    val = p.get("message", "")
                log(ref, "LogStep", str(val))
            else:
                log(ref, "LogStep", "(skipped: condition false)", "Skipped")

        elif typ in ("branch-on-conditions", "continue-on-conditions"):
            log(ref, typ, "evaluated condition")
            exec_steps(s.get("body", []), depth + 1)

        elif typ in ("trigger-business-process", "trigger-integration", "trigger-pdf-generation"):
            log(ref, typ, "triggered")

        elif typ in ("put-amazon-eventbridge-event", "invoke-aws-lambda-function"):
            ctx[ref] = {"response": {"ok": True}}
            log(ref, typ, "AWS call ok")

        else:
            log(ref, typ, "executed")

    try:
        exec_steps(orch.get("steps", []))
    except Exception as e:
        status = "Error"
        error = str(e)

    return {
        "status": status,
        "error": error,
        "durationMs": int((time.time() - t0) * 1000),
        "trace": trace,
        "outputFiles": out_files,
        "context": ctx,
    }


# --- Root span wrapper: every orchestration run becomes one named trace ---
_run_orchestration_impl = run_orchestration

def run_orchestration(orch, trigger_label="Run", inputs=None):
    with _tracer.start_as_current_span("orchestration.run") as root:
        root.set_attribute("orchestration.name", str(orch.get("name", "unnamed")))
        root.set_attribute("orchestration.step_count", len(orch.get("steps", []) or []))
        root.set_attribute("orchestration.trigger", str(trigger_label))
        result = _run_orchestration_impl(orch, trigger_label, inputs)
        try:
            root.set_attribute("orchestration.status", str(result.get("status", "")))
            root.set_attribute("orchestration.duration_ms", int(result.get("durationMs", 0)))
            if result.get("status") == "Error":
                root.set_status(Status(StatusCode.ERROR, str(result.get("error") or "orchestration failed")))
        except Exception:
            pass
        return result


def render_txt(data):
    """Render RaaS rows as a tab-delimited text document."""
    if isinstance(data, list) and data and isinstance(data[0], dict):
        cols = list(data[0].keys())
        lines = ["\t".join(cols)]
        for row in data:
            lines.append("\t".join(str(row.get(c, "")) for c in cols))
        return "\n".join(lines)
    return json.dumps(data, indent=2, default=str)


# ===========================================================================
# Icons (inline SVG) for fidelity
# ===========================================================================
IC_PLUG = ('<svg viewBox="0 0 24 24" width="38" height="38" fill="none" stroke="#5a6472" '
           'stroke-width="1.6"><path d="M8 3v5M16 3v5M6 8h12v3a6 6 0 0 1-12 0V8z"/>'
           '<path d="M12 17v4"/></svg>')
IC_MEGA = ('<svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="#5a6472" '
           'stroke-width="1.6"><path d="M3 11v2a1 1 0 0 0 1 1h2l9 5V6L6 11H4a1 1 0 0 0-1 0z"/>'
           '<path d="M18 9a3 3 0 0 1 0 6"/></svg>')
IC_DB = ('<svg viewBox="0 0 24 24" width="15" height="15" fill="#fff"><ellipse cx="12" cy="5" rx="8" ry="3"/>'
         '<path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></svg>')
IC_BRACKETS = ('<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="#fff" stroke-width="2.2">'
               '<path d="M9 4H6v16h3M15 4h3v16h-3"/></svg>')
IC_BRANCH = ('<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="#fff" stroke-width="2">'
             '<path d="M6 3v6M6 9a6 6 0 0 0 6 6h6M18 11l3-2-3-2M18 19l3-2-3-2"/></svg>')

# Category icons (small, colored) for the palette headers
CAT_DB = ('<svg viewBox="0 0 24 24" width="16" height="16" fill="#2f9e44"><ellipse cx="12" cy="5" rx="8" ry="3"/>'
          '<path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></svg>')
CAT_BR = ('<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#2563eb" stroke-width="2.2">'
          '<path d="M9 4H6v16h3M15 4h3v16h-3"/></svg>')
CAT_LOGIC = ('<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#d9730d" stroke-width="2">'
             '<path d="M6 3v6M6 9a6 6 0 0 0 6 6h6M18 11l3-2-3-2M18 19l3-2-3-2"/></svg>')


# ===========================================================================
# Shared chrome - Developer Site (white)
# ===========================================================================
DEV_HEAD = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>__TITLE__</title>
<style>
 *{box-sizing:border-box;margin:0;padding:0}
 body{font-family:'Segoe UI',Roboto,Arial,sans-serif;background:#fff;color:#1c1f23;font-size:14px}
 a{color:#2557d6;text-decoration:none} a:hover{text-decoration:underline}
 .dev-top{display:flex;align-items:center;gap:18px;padding:14px 22px;border-bottom:1px solid #e7e9ee}
 .wlogo{width:36px;height:36px;border-radius:50%;background:#0a2540;color:#f5b700;display:flex;
        align-items:center;justify-content:center;font-weight:800;font-size:18px}
 .dev-top .brand{color:#2557d6;font-weight:700;font-size:20px}
 .dev-top .ham{color:#5a6472;font-size:22px;cursor:pointer}
 .dev-search{flex:1;max-width:860px;background:#eef1f5;border-radius:8px;padding:11px 16px;color:#7a828c}
 .dev-top .who{display:flex;align-items:center;gap:8px;color:#5a6472;font-weight:600;padding-left:18px;border-left:1px solid #e7e9ee}
 .layout{display:flex;min-height:calc(100vh - 66px)}
 .side{width:262px;border-right:1px solid #eef1f5;padding:26px 12px}
 .side a{display:flex;align-items:center;gap:14px;padding:12px 16px;border-radius:10px;color:#2b2f36;font-weight:600}
 .side a.active{background:#eef3ff;color:#2557d6}
 .side a:hover{background:#f5f7fb;text-decoration:none}
 .side .ic{width:22px;color:#5a6472}
 .main{flex:1;padding:26px 36px;max-width:1340px}
 .crumb{color:#5a6472;font-size:14px;margin-bottom:18px}
 .crumb a{color:#2557d6}
 h1{font-size:30px;margin-bottom:4px}
 h2{font-size:20px;margin-bottom:14px}
 .banner{background:linear-gradient(90deg,#1f4fc4,#f5a623);color:#fff;text-align:center;
         padding:11px;font-weight:600;display:flex;align-items:center;justify-content:center;gap:18px}
 .banner .lm{background:#fff;color:#1c1f23;border-radius:18px;padding:5px 14px;font-size:13px}
 .cards{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin:26px 0}
 .bigcard{border:1px solid #e7e9ee;border-radius:14px;padding:22px;display:flex;align-items:center;gap:16px;cursor:pointer}
 .bigcard:hover{border-color:#2557d6;box-shadow:0 2px 10px rgba(37,87,214,.08)}
 .bigcard .t{font-size:18px;font-weight:700} .bigcard .s{color:#6b727c;font-size:13px}
 .bigcard .arr{margin-left:auto;color:#9aa3b0;font-size:22px}
 .panel{border:1px solid #e7e9ee;border-radius:14px;padding:22px;margin-bottom:20px}
 .tabs{display:flex;gap:26px;border-bottom:1px solid #e7e9ee;margin-bottom:22px}
 .tabs a{padding:12px 2px;color:#5a6472;font-weight:600;border-bottom:3px solid transparent}
 .tabs a.active{color:#2557d6;border-bottom-color:#2557d6}
 .twocol{display:grid;grid-template-columns:1.7fr 1fr;gap:24px}
 .addlink{color:#2557d6;font-weight:600;display:inline-flex;align-items:center;gap:6px;margin-top:14px}
 .meta .k{font-size:13px;color:#8a909a;margin-top:16px} .meta .v{font-size:15px}
 .btn{display:inline-block;border:1px solid #c4ccd6;background:#fff;border-radius:22px;padding:9px 20px;
      cursor:pointer;font-size:14px;font-weight:600}
 .btn.pri{background:#2557d6;border-color:#2557d6;color:#fff}
 .btn:hover{background:#f3f6fb} .btn.pri:hover{background:#1f49b8}
 .modal-bg{position:fixed;inset:0;background:rgba(20,30,50,.45);display:flex;align-items:center;justify-content:center;z-index:60}
 .modal{background:#fff;border-radius:14px;padding:30px;width:560px;max-width:92vw}
 .modal h3{font-size:24px;margin-bottom:18px}
 .modal label{display:block;font-weight:600;margin-bottom:6px}
 .modal input{width:100%;border:1px solid #2557d6;border-radius:8px;padding:11px 12px;font-size:15px}
 .row2{display:flex;gap:12px;margin-top:20px}
 .recent{border:1px solid #e7e9ee;border-radius:14px;padding:20px}
 .recent .item{display:flex;align-items:center;gap:10px;padding:14px 4px;border-bottom:1px solid #f0f2f6}
 .recent .ok{color:#1f9d55} .recent .sub{color:#8a909a;font-size:13px}
 .sel{border:2px solid #2557d6 !important}
</style></head><body>"""

DEV_NAV = """
<div class="dev-top">
  <div class="wlogo">W</div>
  <div class="brand">Developers</div>
  <div class="ham">&#9776;</div>
  <div class="dev-search">&#128269;&nbsp; Search Developer Site (/)</div>
  <div class="who">&#128100; WCP</div>
</div>"""


def dev_side(active):
    items = [("Apps", "/orchestrate/apps", "&#128462;"),
             ("Analytics", "#", "&#128200;"),
             ("Tenants", "#", "&#128451;"),
             ("API Clients", "#", "&#128274;"),
             ("Users", "#", "&#128101;"),
             ("Third Party Integrations", "#", "&#128279;")]
    h = '<div class="side">'
    for name, url, ic in items:
        cls = " active" if name == active else ""
        h += '<a class="%s" href="%s"><span class="ic">%s</span>%s</a>' % (cls, url, ic, name)
    return h + "</div>"


def dev_page(title, body, nav=True):
    html = DEV_HEAD.replace("__TITLE__", title)
    if nav:
        html += DEV_NAV
    return Response(html + body + "</body></html>", mimetype="text/html")


# ===========================================================================
# Developer Site: Home
# ===========================================================================
@app.route("/orchestrate")
def dev_home():
    d = load()
    recents = ""
    names = list(d["apps"].values())
    show = (names + [{"name": "localDisk"}, {"name": "ParkingRegistration"}])[:3]
    for i, a in enumerate(show):
        link = ("/orchestrate/console/apps/view/%s" % a["id"]) if a.get("id") else "#"
        recents += ('<div class="item"><span class="ok">&#10004;</span>'
                    '<div><a href="%s"><b>%s</b></a>'
                    '<div class="sub">Last Modified %s by Tony Gilfillan</div></div></div>'
                    % (link, esc(a["name"]), "a few seconds ago" if i == 0 else "an hour ago"))
    body = """
    <div class="banner">Workday DevCon | June 1-4, 2026 | Resorts World Las Vegas | Registration Open Now.
      <span class="lm">Learn More &#8599;</span></div>
    <div class="main" style="max-width:1340px;margin:0 auto">
      <h1 style="margin:26px 0 0">Hi Tony! Welcome to the Developer Site.</h1>
      <div class="cards">
        <div class="bigcard"><span style="font-size:30px">&#128202;</span>
          <div><div class="t">Build an Extend App</div><div class="s">With App Builder</div></div>
          <span class="arr">&#8250;</span></div>
        <div class="bigcard" onclick="location='/orchestrate/build-app'">
          <span style="font-size:30px">&#128719;</span>
          <div><div class="t">Build an Integration App</div><div class="s">With Orchestration Builder</div></div>
          <span class="arr">&#8250;</span></div>
        <div class="bigcard" onclick="location='/orchestrate/apps'">
          <span style="font-size:30px">&#128187;</span>
          <div><div class="t">Manage Apps</div><div class="s">See all apps in your company.</div></div>
          <span class="arr">&#8250;</span></div>
      </div>
      <div class="twocol">
        <div>
          <h2>Pick Up Where You Left Off</h2>
          <div class="recent"><div style="font-weight:700;margin-bottom:6px">Recently Modified</div>__RECENT__</div>
        </div>
        <div>
          <h2>What's New</h2>
          <div class="recent">
            <div style="font-weight:700;color:#2557d6;margin-bottom:10px">&#128240; Product Updates</div>
            <div style="padding:8px 0"><a href="#">&#128640; Workday Developer CLI - Now Generally Available</a></div>
            <div style="padding:8px 0"><a href="#">&#128640; Orchestrate - 48 Hour Runtime</a></div>
            <div style="padding:8px 0"><a href="#">Orchestrate - Pagination for External REST APIs</a></div>
          </div>
        </div>
      </div>
    </div>""".replace("__RECENT__", recents)
    return dev_page("Developer Site", body, nav=False)


# ===========================================================================
# Build an Integration App modal
# ===========================================================================
@app.route("/orchestrate/build-app")
def build_app():
    body = """
    <div class="modal-bg" onclick="if(event.target===this)location='/orchestrate'">
      <div class="modal" style="width:760px">
        <div style="display:flex;align-items:center"><h3 style="flex:1;font-size:22px">
          Build an Integration App <span style="color:#6b727c;font-weight:400">with Orchestration Builder</span></h3>
          <a href="/orchestrate" style="font-size:22px;color:#5a6472">&#10005;</a></div>
        <p style="color:#5a6472;margin-bottom:18px">Orchestration Builder enables you to author Integration apps
          on the Workday Developer Site. <a href="#">Learn More</a></p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
          <div>
            <div style="font-weight:700;margin-bottom:10px">Create App</div>
            <div class="bigcard" style="margin-bottom:12px"><span style="font-size:22px">&#128214;</span>
              <div class="t" style="font-size:15px">Copy from App Catalog</div><span class="arr">&#8250;</span></div>
            <div class="bigcard" style="margin-bottom:12px"><span style="font-size:22px">&#11014;</span>
              <div class="t" style="font-size:15px">Upload a Zip File</div><span class="arr">&#8250;</span></div>
            <div class="bigcard" onclick="location='/orchestrate/create-app'"><span style="font-size:22px">&#128736;</span>
              <div class="t" style="font-size:15px">Start from Scratch</div><span class="arr">&#8250;</span></div>
          </div>
          <div>
            <div style="font-weight:700;margin-bottom:10px">Open App</div>
            <div class="bigcard" style="margin-bottom:12px" onclick="location='/orchestrate/apps'">
              <span style="font-size:22px">&#128194;</span>
              <div class="t" style="font-size:15px">Open from App Hub</div><span class="arr">&#8250;</span></div>
            <div class="bigcard"><span style="font-size:22px">&#128193;</span>
              <div class="t" style="font-size:15px">Open a Local Folder</div></div>
          </div>
        </div>
      </div>
    </div>"""
    return dev_page("Build an Integration App", body, nav=False)


@app.route("/orchestrate/create-app", methods=["GET", "POST"])
def create_app():
    if request.method == "POST":
        d = load()
        name = request.form.get("name", "New App").strip()
        ref = re.sub(r"\W+", "", name)[:24] or "app"
        aid = "%s_%s" % (ref, _ref_suffix())
        d["apps"][aid] = {"id": aid, "name": name, "refId": aid,
                          "appId": _ref_suffix() + _ref_suffix(),
                          "description": request.form.get("description", "--") or "--",
                          "created": datetime.date.today().strftime("%m/%d/%Y"),
                          "createdBy": "Tony Gilfillan", "orchestrations": {}}
        save(d)
        return Response("", status=302, headers={"Location": "/orchestrate/console/apps/view/%s" % aid})
    suffix = "_" + _ref_suffix()
    body = """
    <div class="modal-bg" onclick="if(event.target===this)location='/orchestrate/build-app'">
      <div class="modal">
        <h3>Create an App <span style="color:#6b727c;font-weight:400">from Scratch</span></h3>
        <div style="color:#8a909a;font-weight:600">Company</div><div style="margin-bottom:14px">WCP</div>
        <label>Name <span style="color:#d33">*</span></label>
        <input id="nm" value="Display Name For Integration"
          oninput="document.getElementById('rid').value=this.value.replace(/[^A-Za-z0-9]/g,'')">
        <label style="margin-top:16px">Reference ID <span style="color:#d33">*</span></label>
        <div style="display:flex;align-items:center;gap:8px">
          <input id="rid" value="displayNameForIntegration"><span style="color:#8a909a">__SUF__</span></div>
        <label style="margin-top:16px">Description</label>
        <textarea id="ds" style="width:100%;border:1px solid #c4ccd6;border-radius:8px;padding:10px;min-height:80px"
          placeholder="Optional"></textarea>
        <div class="row2">
          <button class="btn pri" onclick="go()">Create and Edit</button>
          <button class="btn" onclick="go()">Create and Go to Overview</button>
        </div>
      </div>
    </div>
    <script>
    function go(){var f=document.createElement('form');f.method='POST';f.action='/orchestrate/create-app';
      f.innerHTML='<input name=name value="'+document.getElementById('nm').value.replace(/"/g,'&quot;')+'">'+
        '<input name=description value="'+document.getElementById('ds').value.replace(/"/g,'&quot;')+'">';
      document.body.appendChild(f);f.submit();}
    </script>""".replace("__SUF__", suffix)
    return dev_page("Create an App", body, nav=False)


# ===========================================================================
# Apps list + App overview
# ===========================================================================
@app.route("/orchestrate/apps")
def apps_list():
    d = load()
    rows = ""
    for a in d["apps"].values():
        rows += ('<div class="recent"><div class="item" style="border:none">'
                 '<a href="/orchestrate/console/apps/view/%s"><b>%s</b></a></div></div>'
                 % (a["id"], esc(a["name"])))
    body = ('<div class="layout">%s<div class="main"><div class="crumb">'
            '<a href="/orchestrate">Home</a> &#8250; Apps</div><h1>Apps</h1>'
            '<div style="margin-top:18px">%s</div>'
            '<button class="btn pri" style="margin-top:18px" onclick="location=\'/orchestrate/build-app\'">'
            '+ Build an Integration App</button></div></div>'
            % (dev_side("Apps"), rows or "<p>No apps yet.</p>"))
    return dev_page("Apps", body)


@app.route("/orchestrate/console/apps/view/<app_id>")
def app_overview(app_id):
    d = load()
    a = d["apps"].get(app_id)
    if not a:
        return dev_page("Not found", "<div class='main'>App not found.</div>")
    orchs = ""
    for o in a["orchestrations"].values():
        orchs += ('<div class="item"><a href="/orchestrate/app/%s/development/orchestrations/%s"><b>%s</b></a>'
                  '<span style="margin-left:auto;color:#9aa3b0">&#8942;</span></div>'
                  % (a["appId"], o["name"], esc(o["name"])))
    body = """
    <div class="layout">__SIDE__
      <div class="main">
        <div class="crumb"><a href="/orchestrate">Home</a> &#8250; <a href="/orchestrate/apps">Apps</a> &#8250; __NAME__</div>
        <h1 style="display:flex;align-items:center;gap:12px">__NAME__
          <span style="border:1px solid #e7e9ee;border-radius:50%;width:42px;height:42px;display:inline-flex;
            align-items:center;justify-content:center;font-size:20px">&#8230;</span></h1>
        <div class="tabs" style="margin-top:18px">
          <a class="active">Overview</a><a>Promotions</a><a>Activity</a>
          <a>Orchestration Activity</a><a>Logs</a></div>
        <div class="twocol">
          <div>
            <div class="panel">
              <h2>Orchestrations</h2>
              <div>__ORCHS__</div>
              <a class="addlink" href="/orchestrate/app/__APPID__/orchestrations">+ Add Orchestration</a>
            </div>
            <div class="panel">
              <h2>Tenant Configuration</h2>
              <p style="color:#6b727c">No Tenant Configuration</p>
              <a class="addlink" href="#">+ Add Tenant Configuration</a>
            </div>
          </div>
          <div>
            <div class="panel meta">
              <h2>About</h2>
              <div class="k">Description</div><div class="v">__DESC__</div>
              <div class="k">Reference ID</div><div class="v">__REF__</div>
              <div class="k">Created</div><div class="v">__CREATED__ by __BY__</div>
            </div>
          </div>
        </div>
      </div>
    </div>"""
    body = (body.replace("__SIDE__", dev_side("Apps")).replace("__NAME__", esc(a["name"]))
            .replace("__ORCHS__", orchs or "<p style='color:#6b727c'>No orchestrations yet.</p>")
            .replace("__APPID__", a["appId"]).replace("__DESC__", esc(a["description"]))
            .replace("__REF__", esc(a["refId"])).replace("__CREATED__", a["created"])
            .replace("__BY__", esc(a["createdBy"])))
    return dev_page(a["name"] + " - Apps", body)


def _app_by_appid(d, appid):
    for a in d["apps"].values():
        if a.get("appId") == appid:
            return a
    return None


# ===========================================================================
# Create Orchestration (type selection + name modal)
# ===========================================================================
@app.route("/orchestrate/app/<appid>/orchestrations")
def create_orch_page(appid):
    d = load()
    a = _app_by_appid(d, appid)
    nm = a["name"] if a else "app"
    body = """
    <div style="min-height:100vh;background:#eef2f7;position:relative;overflow:hidden">
      <div class="dev-top" style="background:#fff"><div class="wlogo">W</div></div>
      <div style="padding:30px 40px"><div class="crumb"><a href="/orchestrate/apps">My Apps</a> &#8250; <b>__NM__</b></div>
        <div style="font-size:34px;margin:20px 0">__NM__</div></div>
      <div style="position:absolute;left:0;top:200px;width:560px;height:560px;border-radius:50%;
        background:radial-gradient(circle at 60% 40%,#9cc0ff,#3b82f6);opacity:.5"></div>
      <div style="max-width:760px;margin:0 auto;padding:0 30px 60px;position:relative">
        <h1 style="font-size:34px">Create Orchestration</h1>
        <p style="color:#5a6472;margin:10px 0 28px">Select from the following Orchestration types as your starting point.</p>
        <div style="color:#8a909a;font-weight:700;letter-spacing:.5px;margin-bottom:14px">BUILD YOUR OWN</div>
        <div class="bigcard" style="margin-bottom:16px;background:#fff" onclick="open_modal('Synchronous Orchestration')">
          <span style="font-size:30px;color:#2557d6">&#127939;</span>
          <div><div class="t">Synchronous Orchestration</div>
            <div class="s">Create an Orchestration that starts and completes without awaiting any other input.</div></div></div>
        <div class="bigcard" style="margin-bottom:28px;background:#fff" onclick="open_modal('Asynchronous Orchestration')">
          <span style="font-size:30px;color:#2557d6">&#9749;</span>
          <div><div class="t">Asynchronous Orchestration</div>
            <div class="s">Create an Orchestration that can await input from other processes.</div></div></div>
        <div style="color:#8a909a;font-weight:700;letter-spacing:.5px;margin-bottom:14px">REQUEST FROM WORKDAY</div>
        <div class="bigcard" style="margin-bottom:16px;background:#fff" onclick="open_modal('Workday Business Process')">
          <span style="font-size:30px;color:#2557d6">&#9685;</span>
          <div><div class="t">Workday Business Process</div>
            <div class="s">Create an Orchestration that's triggered by an existing Workday business process.</div></div></div>
        <div class="bigcard" style="margin-bottom:16px;background:#fff" onclick="open_modal('Workday Home Card')">
          <span style="font-size:30px;color:#2557d6">&#9685;</span>
          <div><div class="t">Workday Home Card</div>
            <div class="s">Create an Orchestration that adds data to a custom Workday Home card.</div></div></div>
        <div class="bigcard sel" style="background:#fff" onclick="open_modal('Workday Integration System')">
          <span style="font-size:30px;color:#2557d6">&#9685;</span>
          <div><div class="t">Workday Integration System</div>
            <div class="s">Create an orchestration that is triggered from a Workday integration system.</div></div></div>
      </div>
    </div>
    <div class="modal-bg" id="mb" style="display:none">
      <div class="modal">
        <div style="display:flex"><h3 style="flex:1">Create New Orchestration</h3>
          <span onclick="document.getElementById('mb').style.display='none'"
            style="color:#2557d6;font-size:22px;cursor:pointer">&#10005;</span></div>
        <label>Name</label><input id="onm" placeholder="raas">
        <div class="row2"><button class="btn pri" onclick="done()">Done</button>
          <button class="btn" onclick="document.getElementById('mb').style.display='none'">Cancel</button></div>
      </div>
    </div>
    <script>
    var OTYPE='Workday Integration System';
    function open_modal(t){OTYPE=t;document.getElementById('mb').style.display='flex';document.getElementById('onm').focus();}
    function done(){var n=document.getElementById('onm').value.trim()||'raas';
      var f=document.createElement('form');f.method='POST';
      f.action='/orchestrate/app/__APPID__/orchestrations/create';
      f.innerHTML='<input name=name value="'+n.replace(/"/g,'')+'"><input name=type value="'+OTYPE+'">';
      document.body.appendChild(f);f.submit();}
    </script>""".replace("__NM__", esc(nm)).replace("__APPID__", appid)
    return dev_page("Create Orchestration", body, nav=False)


@app.route("/orchestrate/app/<appid>/orchestrations/create", methods=["POST"])
def create_orch(appid):
    d = load()
    a = _app_by_appid(d, appid)
    name = request.form.get("name", "raas").strip() or "raas"
    type_str = request.form.get("type", "Workday Integration System")
    start_map = {"Synchronous Orchestration": "synchronous", "Synchronous": "synchronous",
                 "Asynchronous Orchestration": "asynchronous", "Asynchronous": "asynchronous",
                 "Workday Business Process": "business-process",
                 "Workday Home Card": "home-card",
                 "Workday Integration System": "integration"}
    start = start_map.get(type_str, "integration")
    if start == "integration":
        steps = [{"id": "s1", "type": "send-workday-raas-request",
                  "ref": "SendWorkdayRaaSRequest",
                  "props": {"method": "GET",
                            "urlPrefix": "http://127.0.0.1:8443/task/view-report?name=",
                            "path": "", "auth": "Default Workday API Credential",
                            "contentType": "Any"}}]
    else:
        steps = []   # real builder starts with an empty canvas (Start + End only)
    if a:
        a["orchestrations"][name] = {"name": name, "type": type_str, "startType": start,
                                     "lastBuild": None, "steps": steps}
        save(d)
    return Response("", status=302,
                    headers={"Location": "/orchestrate/app/%s/development/orchestrations/%s" % (appid, name)})


# ===========================================================================
# ORCHESTRATION BUILDER
# ===========================================================================
@app.route("/orchestrate/app/<appid>/development/orchestrations/<name>")
def builder(appid, name):
    d = load()
    a = _app_by_appid(d, appid)
    if not a or name not in a["orchestrations"]:
        return dev_page("Not found", "<div class='main'>Orchestration not found.</div>")
    orch = a["orchestrations"][name]
    payload = {"appId": appid, "appName": a["name"], "orch": orch,
               "tenants": TENANTS, "buildNo": d["counters"]["build"] + 1}
    html = (BUILDER_HEAD + BUILDER_BODY.replace("__DATA__", json.dumps(payload)))
    return Response(html, mimetype="text/html")


@app.route("/orchestrate/api/save", methods=["POST"])
def api_save():
    data = request.get_json(force=True)
    d = load()
    a = _app_by_appid(d, data["appId"])
    if a:
        a["orchestrations"][data["orch"]["name"]] = data["orch"]
        save(d)
    return {"ok": True, "savedAt": datetime.datetime.now().strftime("%I:%M %p")}


@app.route("/orchestrate/api/validate", methods=["POST"])
def api_validate():
    orch = request.get_json(force=True).get("orch", {})
    issues = []
    for s in orch.get("steps", []):
        if s["type"] == "store-document" and not s.get("props", {}).get("documentToStore"):
            issues.append("%s: Document to Store is required" % s.get("ref"))
        if s["type"] == "store-document" and not s.get("props", {}).get("documentTitle"):
            issues.append("%s: Document Title is required" % s.get("ref"))
    return {"ok": len(issues) == 0, "issues": issues}


@app.route("/orchestrate/api/build", methods=["POST"])
def api_build():
    data = request.get_json(force=True)
    d = load()
    a = _app_by_appid(d, data["appId"])
    d["counters"]["build"] += 1
    bn = d["counters"]["build"]
    if a and data["orch"]["name"] in a["orchestrations"]:
        a["orchestrations"][data["orch"]["name"]] = data["orch"]
        a["orchestrations"][data["orch"]["name"]]["lastBuild"] = bn
    save(d)
    return {"ok": True, "buildNo": bn, "tenants": TENANTS}


@app.route("/orchestrate/api/run", methods=["POST"])
def api_run():
    orch = request.get_json(force=True).get("orch", {})
    res = run_orchestration(orch, "Run Logs")
    return res


@app.route("/orchestrate/api/deploy", methods=["POST"])
def api_deploy():
    data = request.get_json(force=True)
    d = load()
    a = _app_by_appid(d, data["appId"])
    tenant = data.get("tenant")
    name = data["orch"]["name"]
    # register a tenant Integration System auto-wired to the orchestration
    d["counters"]["is"] += 1
    isid = "IS%03d" % d["counters"]["is"]
    d["integration_systems"][isid] = {
        "id": isid, "systemName": name + " demo", "systemId": (name + "demo"),
        "template": "Orchestrate Integration Template", "tenant": tenant,
        "orchestrationName": name, "appReferenceId": a["refId"] if a else name + "_x",
    }
    d["deployments"].append({"tenant": tenant, "orch": name, "isId": isid,
                             "at": datetime.datetime.now().isoformat(timespec="seconds")})
    save(d)
    return {"ok": True, "isId": isid, "tenant": tenant}


@app.route("/orchestrate/api/tenants")
def api_tenants():
    return {"tenants": TENANTS}


# ===========================================================================
# TENANT SIDE - View Integration System / Launch / Background Process / Output
# ===========================================================================
TEN_HEAD = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>__TITLE__</title>
<style>
 *{box-sizing:border-box;margin:0;padding:0}
 body{font-family:'Segoe UI',Roboto,Arial,sans-serif;background:#fff;color:#1c1f23;font-size:14px}
 a{color:#2557d6;text-decoration:none} a:hover{text-decoration:underline}
 .wtop{display:flex;align-items:center;gap:18px;background:#f6f7f9;padding:10px 22px}
 .wtop .w{width:34px;height:34px;border-radius:50%;background:#0a2540;color:#f5b700;display:flex;
          align-items:center;justify-content:center;font-weight:800}
 .wsearch{flex:1;max-width:760px;background:#fff;border:1px solid #e1e4ea;border-radius:24px;padding:9px 18px;color:#8a909a}
 .ttl{background:#1e4fc4;color:#fff;padding:16px 24px;font-size:22px;font-weight:700;display:flex;align-items:center;gap:12px}
 .ttl .sub{font-size:14px;font-weight:400;opacity:.92}
 .body{padding:24px 30px;max-width:1500px}
 h2{font-size:18px;margin:22px 0 10px}
 .kv{display:grid;grid-template-columns:200px 1fr;row-gap:12px;max-width:900px}
 .kv .k{font-weight:700} 
 table{width:100%;border-collapse:collapse;margin-top:8px}
 th,td{text-align:left;padding:11px 12px;border:1px solid #e7e9ee;font-size:13px}
 th{background:#f6f8fb;font-weight:700}
 .btn{display:inline-block;border:1px solid #c4ccd6;background:#fff;border-radius:22px;padding:9px 22px;
      cursor:pointer;font-weight:600}
 .btn.pri{background:#2557d6;border-color:#2557d6;color:#fff}
 .bar{height:8px;width:340px;background:#e7e9ee;border-radius:6px;overflow:hidden;display:inline-block;vertical-align:middle}
 .bar > i{display:block;height:100%;background:#2557d6}
 .tabs{display:flex;gap:26px;border-bottom:1px solid #e7e9ee;margin:18px 0}
 .tabs a{padding:12px 2px;color:#5a6472;font-weight:600;border-bottom:3px solid transparent}
 .tabs a.active{color:#2557d6;border-bottom-color:#2557d6}
 .modal-bg{position:fixed;inset:0;background:rgba(20,30,50,.45);display:flex;align-items:flex-start;justify-content:center;z-index:60}
 .modal{background:#fff;border-radius:12px;margin-top:90px;width:720px;max-width:94vw;overflow:hidden}
 .modal .mh{background:#1e4fc4;color:#fff;padding:14px 22px;font-size:18px;font-weight:700}
 .modal .mb{padding:22px}
 .frow{display:grid;grid-template-columns:200px 1fr;align-items:center;margin-bottom:16px}
 .frow .lab{font-weight:700} .frow .lab .req{color:#d33}
 .pill{border:1px solid #c4ccd6;border-radius:6px;padding:8px 10px;display:flex;align-items:center;gap:8px;background:#fff}
 .chip{background:#eef1f5;border-radius:5px;padding:2px 8px}
 .mf{padding:16px 22px;display:flex;gap:12px;border-top:1px solid #eef1f5}
</style></head><body>"""


def ten_nav(search="create int sys"):
    return ('<div class="wtop"><div class="w">W</div>'
            '<div class="wsearch">&#128269;&nbsp; %s</div>'
            '<div style="margin-left:auto;color:#5a6472">&#128172; &#128276; &#128100;</div></div>' % search)


@app.route("/orchestrate/tenant/integration-system/<isid>")
def view_is(isid):
    d = load()
    s = d["integration_systems"].get(isid)
    if not s:
        return Response(TEN_HEAD.replace("__TITLE__", "Not found") + ten_nav() +
                        "<div class='body'>Integration System not found. Deploy an orchestration first.</div></body></html>",
                        mimetype="text/html")
    body = TEN_HEAD.replace("__TITLE__", "Integration System") + ten_nav()
    body += """
    <div class="ttl">View Integration System <span class="sub">__NAME__ &#8230;</span></div>
    <div class="body">
      <h2>Basic Details</h2>
      <div class="kv"><div class="k">System Name</div><div>__NAME__</div></div>
      <div style="margin:14px 0;color:#2557d6">&#9656; System ID &nbsp; <span style="color:#1c1f23">__SID__</span></div>
      <div class="kv" style="max-width:none">
        <div class="k">Integration Template</div><div>Orchestrate Integration Template</div>
        <div class="k">Template Description</div>
        <div>This template is used when implementing an Orchestration. The user must implement the
          External_Integrations WSDL to be invoked by this Template.</div></div>
      <h2>Integration Services <span style="font-weight:400;color:#8a909a">1 item</span></h2>
      <table><tr><th>Integration Template Service</th><th>Initial Service to Invoke</th><th>Optional</th><th>Enabled</th></tr>
        <tr><td>Orchestrate Integration Template / Integration Deployed Orchestrate Service*</td>
          <td>Yes</td><td></td><td>Yes</td></tr></table>
      <h2>Integration Attributes <span style="font-weight:400;color:#8a909a">2 items</span></h2>
      <table><tr><th>Attribute Provider</th><th>Attribute</th><th>Description</th><th>Value</th><th>Restricted to Environment</th></tr>
        <tr><td>Integration Deployed Orchestrate Service</td><td>Orchestration Name</td><td></td><td>__ORCH__</td><td></td></tr>
        <tr><td></td><td>Application Reference ID</td><td></td><td>__APPREF__</td><td></td></tr></table>
      <div style="margin-top:26px">
        <a class="btn pri" href="/orchestrate/tenant/launch/__ISID__">Actions &#8250; Integration &#8250; Launch / Schedule</a>
      </div>
    </div></body></html>"""
    body = (body.replace("__NAME__", esc(s["systemName"])).replace("__SID__", esc(s["systemId"]))
            .replace("__ORCH__", esc(s["orchestrationName"])).replace("__APPREF__", esc(s["appReferenceId"]))
            .replace("__ISID__", isid))
    return Response(body, mimetype="text/html")


@app.route("/orchestrate/tenant/launch/<isid>", methods=["GET", "POST"])
def launch_is(isid):
    d = load()
    s = d["integration_systems"].get(isid)
    if not s:
        return Response("not found", status=404)
    if request.method == "POST":
        # run the deployed orchestration -> create background process + output file
        a = None
        for ap in d["apps"].values():
            if s["orchestrationName"] in ap["orchestrations"]:
                a = ap
                break
        orch = a["orchestrations"][s["orchestrationName"]] if a else {"steps": []}
        res = run_orchestration(orch, "Launch")
        d["counters"]["bp"] += 1
        bp_id = "BP%03d" % d["counters"]["bp"]
        of_ids = []
        for of in res["outputFiles"]:
            d["counters"]["of"] += 1
            ofid = "OF%03d" % d["counters"]["of"]
            d["output_files"][ofid] = {"id": ofid, "title": of["title"], "type": of["type"],
                                       "body": of["body"], "createdBy": "Logan McNeil",
                                       "created": datetime.datetime.now().strftime("%m/%d/%Y %I:%M %p"),
                                       "expires": (datetime.date.today() + datetime.timedelta(days=7)).strftime("%m/%d/%Y")}
            of_ids.append(ofid)
        d["bg_processes"][bp_id] = {
            "id": bp_id, "request": request.form.get("request", s["systemName"]),
            "process": s["systemName"], "status": "Completed", "isId": isid,
            "system": s["systemName"], "initiatedBy": "Logan McNeil",
            "initiatedAt": datetime.datetime.now().strftime("%m/%d/%Y %I:%M:%S %p"),
            "outputFiles": of_ids, "trace": res["trace"],
        }
        save(d)
        return Response("", status=302, headers={"Location": "/orchestrate/tenant/bg-process/%s" % bp_id})
    body = TEN_HEAD.replace("__TITLE__", "Launch / Schedule Integration") + ten_nav()
    body += """
    <div class="modal-bg" onclick="if(event.target===this)location='/orchestrate/tenant/integration-system/__ISID__'">
      <div class="modal">
        <div class="mh">Launch / Schedule Integration</div>
        <div class="mb">
          <div class="frow"><div class="lab">Integration <span class="req">*</span></div>
            <div class="pill"><span class="chip">&#10005; __NAME__ &#8230;</span></div></div>
          <div class="frow"><div class="lab">Organization</div><div class="pill">&nbsp;</div></div>
          <div class="frow"><div class="lab">Integration System Context</div><div class="pill">&nbsp;</div></div>
          <div class="frow"><div class="lab">Run Frequency <span class="req">*</span></div>
            <div class="pill"><span class="chip">&#10005; Run Now</span></div></div>
        </div>
        <div class="mf">
          <button class="btn pri" onclick="document.getElementById('lf').submit()">OK</button>
          <button class="btn" onclick="location='/orchestrate/tenant/integration-system/__ISID__'">Cancel</button>
        </div>
      </div>
    </div>
    <form id="lf" method="POST" style="display:none"><input name="request" value="__NAME__"></form>
    </body></html>"""
    body = body.replace("__NAME__", esc(s["systemName"])).replace("__ISID__", isid)
    return Response(body, mimetype="text/html")


@app.route("/orchestrate/tenant/bg-process/<bpid>")
def bg_process(bpid):
    d = load()
    bp = d["bg_processes"].get(bpid)
    if not bp:
        return Response("not found", status=404)
    of_rows = ""
    for ofid in bp["outputFiles"]:
        of = d["output_files"][ofid]
        of_rows += ('<tr><td>%s</td><td><a href="/orchestrate/tenant/output/%s">%s</a></td>'
                    '<td>%s</td><td>%s</td><td></td><td>%s</td></tr>'
                    % (of["created"], ofid, esc(of["title"]), of["type"], esc(of["createdBy"]), of["expires"]))
    nof = len(bp["outputFiles"])
    trace_rows = ""
    for e in (bp.get("trace") or []):
        lvl = "ERROR" if e.get("status") == "Error" else "INFO"
        chip = ("background:#fdeaea;color:#c0392b" if lvl == "ERROR" else "background:#e8f1fd;color:#1f6feb")
        if e.get("type") == "LogStep":
            msg = "&lt;LogStep&gt; - %s [Log] [orchId=%s]" % (esc(e["message"]), esc(bp.get("process", "")))
        else:
            msg = "&lt;%s&gt; - %s" % (esc(e.get("type", "Step")), esc(e["message"]))
        trace_rows += ('<tr><td><span style="%s;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700">%s</span></td>'
                       '<td style="font-family:Consolas,monospace;font-size:12px">%s</td>'
                       '<td>%s</td></tr>' % (chip, lvl, msg, esc(e.get("step", ""))))
    ntrace = len(bp.get("trace") or [])
    body = TEN_HEAD.replace("__TITLE__", "View Background Process") + ten_nav()
    body += """
    <div class="ttl">View Background Process <span class="sub">__REQ__ &#8230;</span></div>
    <div class="body">
      <div class="kv">
        <div class="k">Process</div><div><a href="#">__PROC__</a></div>
        <div class="k">Request Name</div><div>__REQ__</div>
        <div class="k">Status</div><div>__STATUS__</div>
        <div class="k">Current Processing Time (hh:mm:ss)</div><div>00:00:03</div>
      </div>
      <div class="tabs">
        <a>Integration Details</a><a>Process Info</a><a>Process History</a>
        <a class="active">Output Files (__NOF__)</a><a>Messages (1)</a><a>Child Processes (2)</a></div>
      <h2 style="margin-top:0">Reports and Other Output Files</h2>
      <div style="color:#8a909a;margin-bottom:6px">__NOF__ item</div>
      <table>
        <tr><th>Date and Time Created</th><th>File</th><th>Type</th><th>Created by</th>
            <th>Number of Shared Users</th><th>Expiration Date</th></tr>
        __ROWS__
      </table>
      <h2 style="margin-top:26px">Run Logs <span style="color:#8a909a;font-weight:400">(__NTRACE__)</span></h2>
      <table>
        <tr><th style="width:90px">wd_level</th><th>wd_message</th><th style="width:160px">Step</th></tr>
        __TRACE__
      </table>
    </div></body></html>"""
    body = (body.replace("__REQ__", esc(bp["request"])).replace("__PROC__", esc(bp["process"]))
            .replace("__STATUS__", bp["status"]).replace("__NOF__", str(nof))
            .replace("__NTRACE__", str(ntrace))
            .replace("__TRACE__", trace_rows or "<tr><td colspan=3>No log entries.</td></tr>")
            .replace("__ROWS__", of_rows or "<tr><td colspan=6>No output files.</td></tr>"))
    return Response(body, mimetype="text/html")


@app.route("/orchestrate/tenant/output/<ofid>")
def output_file(ofid):
    d = load()
    of = d["output_files"].get(ofid)
    if not of:
        return Response("not found", status=404)
    return Response(of["body"], mimetype="text/plain",
                    headers={"Content-Disposition": 'attachment; filename="%s.txt"' % of["title"]})


# ===========================================================================
# BUILDER HTML (head + body with the big canvas/palette/properties JS)
# ===========================================================================
BUILDER_HEAD = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Orchestration Builder</title>
<style>
 *{box-sizing:border-box;margin:0;padding:0}
 body{font-family:'Segoe UI',Roboto,Arial,sans-serif;color:#1c1f23;font-size:14px;background:#fff;overflow:hidden}
 a{color:#2557d6;text-decoration:none}
 /* top bar */
 .top{display:flex;align-items:center;gap:14px;padding:12px 18px;border-bottom:1px solid #eef1f5;height:60px}
 .top .w{width:30px;height:30px;border-radius:50%;background:#0a2540;color:#f5b700;display:flex;
         align-items:center;justify-content:center;font-weight:800}
 .top .crumb{color:#2557d6;font-weight:700;font-size:18px;text-decoration:underline}
 .top .saved{margin-left:auto;color:#5a6472}
 .btn{border:1px solid #c4ccd6;background:#fff;border-radius:22px;padding:8px 18px;cursor:pointer;font-weight:700}
 .btn:hover{background:#f3f6fb}
 .btn.pri{background:#2557d6;border-color:#2557d6;color:#fff}.btn.pri:hover{background:#1f49b8}
 .btn.disabled{opacity:.5;pointer-events:none}
 /* shell */
 .shell{display:flex;height:calc(100vh - 60px - 44px)}
 .rail{width:54px;border-right:1px solid #eef1f5;display:flex;flex-direction:column;align-items:center;
       padding:14px 0;gap:18px;color:#7a828c}
 .rail .r{width:30px;height:30px;display:flex;align-items:center;justify-content:center;border-radius:8px;cursor:pointer}
 .rail .r.act{background:#eef3ff;color:#2557d6}
 .rail .badge{position:relative}
 .rail .badge::after{content:"1";position:absolute;top:-4px;right:-4px;background:#d9480f;color:#fff;
   font-size:10px;border-radius:50%;width:15px;height:15px;display:flex;align-items:center;justify-content:center}
 /* palette */
 .palette{width:300px;border-right:1px solid #eef1f5;display:flex;flex-direction:column}
 .palette .ph{display:flex;align-items:center;padding:16px 18px;font-size:18px;font-weight:700}
 .palette .ph .x{margin-left:auto;color:#5a6472;cursor:pointer;font-size:20px}
 .palette .search{margin:0 14px 10px;border:1px solid #d7dde6;border-radius:8px;padding:10px 12px;color:#8a909a}
 .palette .scroll{overflow:auto;flex:1;padding:0 8px 20px}
 .pal-cat{display:flex;align-items:center;gap:8px;font-weight:700;padding:14px 10px 6px}
 .pal-cat.dr{color:#2f9e44}.pal-cat.do{color:#2563eb}.pal-cat.ol{color:#d9730d}
 .pal-item{display:flex;align-items:center;padding:11px 12px;border-radius:8px;cursor:grab;color:#2b2f36}
 .pal-item:hover{background:#f3f6fb}
 .pal-item .dots{margin-left:auto;color:#b8c0cb;letter-spacing:1px}
 /* canvas */
 .canvas{flex:1;background:radial-gradient(#dfe4ea 1.3px,transparent 1.3px);background-size:20px 20px;
         overflow:auto;position:relative}
 .ctop{position:sticky;top:0;background:#fff;display:flex;align-items:center;gap:10px;padding:14px 18px;
       border-bottom:1px solid #eef1f5;z-index:5}
 .ctop .nm{font-weight:700}.ctop .ic{margin-left:auto;color:#7a828c;font-size:18px;display:flex;gap:14px}
 .flow{display:flex;flex-direction:column;align-items:center;padding:34px 20px 80px}
 .card{width:340px;background:#fff;border:1px solid #e7e9ee;border-radius:12px;box-shadow:0 1px 4px rgba(10,37,64,.06);
       position:relative}
 .card.trigger{padding:24px 24px 18px;text-align:center}
 .card.trigger .tt{font-size:18px;font-weight:700;margin:6px 0}
 .card.trigger .ts{color:#5a6472;font-size:13.5px;line-height:1.4}
 .card.trigger .cfg{display:block;border-top:1px solid #eef1f5;margin-top:16px;padding-top:14px;color:#2557d6;font-weight:700}
 .card.step{padding:22px 16px 18px;text-align:center;cursor:pointer}
 .card.step.sel{border-color:#2557d6;box-shadow:0 0 0 2px #cfe0ff}
 .card .badge{position:absolute;top:-15px;left:50%;transform:translateX(-50%);width:30px;height:30px;border-radius:8px;
              display:flex;align-items:center;justify-content:center}
 .card .ctype{font-weight:800;font-size:13px;letter-spacing:.4px}
 .card.step.dr .ctype{color:#2f9e44}.card.step.do .ctype{color:#2563eb}.card.step.ol .ctype{color:#d9730d}
 .card .cref{color:#5a6472;font-size:13px;margin-top:3px}
 .card .menu{position:absolute;top:10px;right:12px;color:#9aa3b0;cursor:pointer}
 .card.end{padding:22px 16px;text-align:center}
 .card.end .et{font-weight:700;font-size:16px;margin-top:4px}
 .conn{width:2px;height:22px;background:#c4ccd6;position:relative}
 .conn::before,.conn::after{content:"";position:absolute;left:50%;transform:translateX(-50%);
   width:7px;height:7px;border-radius:50%;background:#9aa3b0}
 .conn::before{top:-3px}.conn::after{bottom:-3px}
 .drop{width:340px;border:1.5px dashed #c4ccd6;border-radius:12px;padding:22px;text-align:center;color:#9aa3b0}
 .drop.over{border-color:#2557d6;background:#eef6ff;color:#2557d6}
 .zoom{position:absolute;right:22px;bottom:22px;display:flex;flex-direction:column;gap:0;border:1px solid #e7e9ee;
       border-radius:24px;background:#fff;overflow:hidden}
 .zoom div{width:42px;height:42px;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:18px;color:#5a6472}
 .zoom div+div{border-top:1px solid #eef1f5}
 /* properties */
 .props{width:520px;border-left:1px solid #eef1f5;display:none;flex-direction:column;overflow:auto}
 .props.show{display:flex}
 .props .ph{display:flex;align-items:center;gap:10px;padding:16px 18px;border-bottom:1px solid #eef1f5}
 .props .ph .pt{font-size:18px;font-weight:700}
 .props .ph .ed{margin-left:auto;background:#eef1f5;border-radius:6px;padding:2px 10px;font-size:12px;color:#5a6472}
 .props .ph .x{color:#5a6472;cursor:pointer;font-size:18px}
 .props .pb{padding:18px;overflow:auto}
 .fld{margin-bottom:16px}
 .fld label{display:block;font-weight:700;margin-bottom:6px}
 .fld label .req{color:#d33}
 .fld input,.fld select{width:100%;border:1px solid #c4ccd6;border-radius:6px;padding:9px 11px;font-size:14px}
 .reqrow{display:flex;gap:0;border:1px solid #c4ccd6;border-radius:8px;overflow:hidden}
 .reqrow select{border:none;border-right:1px solid #e7e9ee;border-radius:0;background:#f6f8fb;width:140px}
 .reqrow .urlp{border:none;border-right:1px solid #e7e9ee;padding:9px 11px;flex:1;color:#1c1f23;background:#fff;outline:none;font-family:inherit;font-size:14px}
 .reqrow .pathin{flex:0 0 210px;border-right:none}
 .reqrow .tokwrap{padding:6px;display:flex;align-items:center;gap:6px;min-width:180px}
 .tabs{display:flex;gap:24px;border-bottom:1px solid #eef1f5;margin:16px 0}
 .tabs a{padding:10px 2px;color:#5a6472;font-weight:700;cursor:pointer;border-bottom:3px solid transparent}
 .tabs a.active{color:#2557d6;border-bottom-color:#2557d6}
 .tokfield{border:1px solid #c4ccd6;border-radius:8px;padding:8px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;position:relative}
 .tok{border-radius:6px;padding:4px 10px;font-size:13px;display:inline-flex;align-items:center;gap:6px}
 .tok.string{background:#23272e;color:#fff}
 .tok.ref{background:#3358cc;color:#fff}
 .tok .rm{cursor:pointer;opacity:.8}
 .addbtn{border:1px solid #d7dde6;background:#f6f8fb;border-radius:6px;width:26px;height:26px;cursor:pointer;color:#5a6472}
 .insbtn{border:1px solid #f0c39a;background:#fdf0e4;border-radius:6px;width:26px;height:26px;cursor:pointer;color:#d9730d}
 .hint{color:#8a909a;font-size:12.5px;margin-top:6px}
 .picker{position:absolute;top:100%;left:0;margin-top:4px;width:420px;background:#fff;border:1px solid #e7e9ee;
         border-radius:10px;box-shadow:0 8px 28px rgba(10,37,64,.16);z-index:30;overflow:hidden}
 .picker .typ{padding:10px 12px;border-bottom:1px solid #eef1f5}
 .picker .typ input{width:100%;border:none;outline:none;font-size:14px}
 .picker .grp{padding:10px 12px;display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:700;color:#1c1f23}
 .picker .grp:hover{background:#f6f8fb}
 .picker .sub{padding:8px 12px 8px 34px;cursor:pointer}.picker .sub:hover{background:#f6f8fb}
 .picker .sub b{color:#2557d6}.picker .sub i{color:#8a909a;font-style:italic;margin-left:8px}
 .picker .add{padding:12px;color:#2557d6;font-weight:700;cursor:pointer;border-top:1px solid #eef1f5}
 .picker .stepname{color:#2f9e44;font-weight:800}
 /* deploy panel */
 .deploy{position:fixed;top:60px;right:0;width:560px;bottom:0;background:#fff;border-left:1px solid #e7e9ee;
         box-shadow:-8px 0 24px rgba(10,37,64,.12);z-index:40;display:none;flex-direction:column}
 .deploy.show{display:flex}
 .deploy .dh{display:flex;align-items:center;gap:10px;padding:18px;border-bottom:1px solid #eef1f5}
 .deploy .dh .ok{color:#1f9d55;font-weight:700}.deploy .dh a{margin-left:auto}
 .deploy .ts{margin:14px 18px;border:1px solid #d7dde6;border-radius:8px;padding:10px 12px;color:#8a909a}
 .deploy .list{overflow:auto;flex:1;padding:0 18px 20px}
 .deploy .trow{display:flex;align-items:center;padding:14px 4px;border-bottom:1px solid #f0f2f6}
 .deploy .trow b{flex:1}
 /* footer */
 .foot{height:44px;border-top:1px solid #eef1f5;display:flex;align-items:center;gap:26px;padding:0 18px}
 .foot a{color:#1c1f23;font-weight:700;cursor:pointer}
 .foot .err{margin-left:auto;display:flex;align-items:center;gap:8px;color:#d9480f;font-weight:700}
 .foot .err .dot{background:#d9480f;color:#fff;border-radius:50%;width:20px;height:20px;display:flex;
   align-items:center;justify-content:center;font-size:12px}
 .console{position:fixed;left:54px;right:0;bottom:44px;max-height:40vh;overflow:auto;background:#0a2540;color:#cfe3ff;
          padding:12px 18px;font-family:Consolas,monospace;font-size:12.5px;display:none;z-index:35}
 .console.show{display:block}
 .console .ok{color:#7fe3a4}.console .er{color:#ff8e8e}.console .mut{color:#7e93ad}
 .console .cx{float:right;cursor:pointer}
 .toast{position:fixed;bottom:60px;left:50%;transform:translateX(-50%);background:#0a2540;color:#fff;
        padding:10px 18px;border-radius:8px;opacity:0;transition:.2s;z-index:80}
 .toast.show{opacity:1}
 /* Create Group + loop container + aggregation + chips */
 .grpbtn{border:1px solid #d7dbe3;background:#fff;border-radius:18px;padding:5px 14px;font-size:13px;font-weight:600;
         color:#1c1f23;cursor:pointer;margin-left:8px}
 .grpbtn:hover{background:#f3f5f8}
 .loopwrap{border:1.5px solid #e3472a;border-radius:14px;background:#fafbfc;padding:6px 16px 14px;
           display:flex;flex-direction:column;align-items:center;min-width:300px}
 .loopwrap.over{background:#fff3f0;border-style:dashed}
 .loopchev{width:30px;height:30px;border-radius:50%;background:#fff;border:1.5px solid #e3472a;color:#e3472a;
           display:flex;align-items:center;justify-content:center;font-weight:800;margin:-20px 0 6px;font-size:13px}
 .loopdrop{border:1.5px dashed #c4ccd6;border-radius:10px;padding:18px;color:#9aa3b0;font-size:13px;width:90%;text-align:center}
 .aggbar{margin-top:2px;background:#eef0f3;border:1px solid #d7dbe3;border-radius:20px;padding:8px 18px;font-weight:800;
         font-size:12.5px;letter-spacing:.4px;color:#3a414d;cursor:pointer;display:flex;align-items:center;gap:10px}
 .aggbar:hover{background:#e6e9ee}
 .aggbar.sel{outline:2px solid #e3472a;outline-offset:1px}
 .aggbar.faint{opacity:.45}
 .aggmenu{cursor:pointer;font-weight:800;color:#5a6472}
 .aggmenupop{position:fixed;background:#fff;border:1px solid #d7dbe3;border-radius:10px;box-shadow:0 8px 26px rgba(0,0,0,.16);
             z-index:90;min-width:210px;padding:6px 0;font-size:14px}
 .aggmenupop .ami{padding:9px 16px;cursor:pointer;color:#1c1f23}
 .aggmenupop .ami:hover{background:#eef6ff;color:#0875e1}
 .chiprow{display:flex;flex-wrap:wrap;align-items:center;gap:6px;border:1px solid #e1e4ea;border-radius:9px;
          padding:8px;background:#fff}
 .chip{border-radius:6px;padding:5px 9px;font-size:12.5px;font-weight:600;border:none;outline:none;font-family:inherit}
 .chip.cref{background:#1f6feb;color:#fff;min-width:120px}
 .chip.citem{background:#1f6feb;color:#fff}
 .chip.cfn{background:#7048d6;color:#fff}
 .chip.cjp{background:#172a3a;color:#9fe6b4;min-width:90px}
 .chip.cbool{background:#0c2a1b;color:#7fe3a4;min-width:90px}
 .sortdir{cursor:pointer;color:#5a6472;font-weight:800;padding:0 4px}
 .chiprm{cursor:pointer;color:#b34;font-weight:700;padding:0 2px}
 .addlink{display:inline-block;margin-top:8px;color:#0875e1;font-weight:600;font-size:13px;cursor:pointer}
 .code{width:100%;min-height:180px;font-family:Consolas,monospace;font-size:12.5px;border:1px solid #d7dbe3;
       border-radius:8px;padding:10px;background:#0a2540;color:#cfe3ff;resize:vertical}
 .aggtbl{width:100%;border-collapse:collapse;margin-top:6px;font-size:13px}
 .aggtbl th{text-align:left;border-bottom:2px solid #e7e9ee;padding:8px 6px;color:#3a414d}
 .aggtbl td{border-bottom:1px solid #eef0f3;padding:6px}
 .aggtbl input,.aggtbl select{width:100%;border:1px solid #d7dbe3;border-radius:6px;padding:6px 8px;font-family:inherit}
 .aggtbl .trash{cursor:pointer}
 .aggopt{display:flex;align-items:center;gap:10px;margin-top:16px;font-weight:600;color:#3a414d}
 .aggempty{text-align:center;color:#9aa3b0;margin-top:36px;line-height:1.5}
</style></head><body>"""

BUILDER_BODY = r"""
<div class="top">
  <div class="w">W</div>
  <a class="crumb" id="crumb" href="#"></a>
  <span class="saved" id="saved">Saved to session less than a minute ago.</span>
  <button class="btn" id="saveAll">Save All to App Hub</button>
  <button class="btn pri" id="deployBtn" onclick="onDeploy()">Deploy</button>
</div>

<div class="shell">
  <div class="rail">
    <div class="r"><svg viewBox="0 0 24 24" width="20" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="9" y="3" width="6" height="6" rx="1"/><rect x="3" y="15" width="6" height="6" rx="1"/><rect x="15" y="15" width="6" height="6" rx="1"/><path d="M12 9v3M6 15v-1.5h12V15"/></svg></div>
    <div class="r act"><svg viewBox="0 0 24 24" width="20" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 7l8-4 8 4-8 4-8-4z"/><path d="M4 12l8 4 8-4M4 17l8 4 8-4"/></svg></div>
    <div class="r"><svg viewBox="0 0 24 24" width="19" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg></div>
    <div style="flex:1"></div>
    <div class="r">&#9000;</div>
    <div class="r badge">&#128227;</div>
    <div class="r"><i>fx</i></div>
    <div class="r">&#128295;</div>
  </div>

  <div class="palette">
    <div class="ph">Components <span class="x" title="(visual)">&#10005;</span></div>
    <div class="search">&#128269;&nbsp; Search Components</div>
    <div class="scroll" id="palette"></div>
  </div>

  <div class="canvas" id="canvasWrap">
    <div class="ctop"><span class="nm" id="orchName"></span> <span style="color:#9aa3b0">&#8942;</span>
      <button class="grpbtn" onclick="alert('Create Group groups selected steps (visual in the mock).')">Create Group</button>
      <span class="ic">&#9889; &#8635; &#9881;</span></div>
    <div class="flow" id="flow"></div>
    <div class="zoom"><div onclick="zoom(0)">&#8635;</div><div onclick="zoom(1)">+</div><div onclick="zoom(-1)">&#8722;</div></div>
  </div>

  <div class="props" id="props">
    <div class="ph"><span id="pIcon"></span><span class="pt" id="pType"></span>
      <span class="ed">Editing</span><span style="color:#9aa3b0">&#128221;</span>
      <span style="color:#9aa3b0">&#8689;</span><span class="x" onclick="deselect()">&#10005;</span></div>
    <div class="pb" id="pBody"></div>
  </div>
</div>

<div class="foot">
  <a onclick="toggleConsole('build')">Build Logs</a>
  <a onclick="toggleConsole('run')">Run Logs</a>
  <div class="err" id="errBadge" style="display:none"><span class="dot">!</span><span id="errCount">1</span></div>
  <button class="btn" style="margin-left:auto" onclick="validate()">Validate</button>
</div>

<div class="deploy" id="deploy">
  <div class="dh"><span class="ok">&#10004; Build #<span id="bn"></span> succeeded</span><a onclick="toggleConsole('build')">View Build Logs</a></div>
  <div class="ts">&#128269;&nbsp; Search tenants</div>
  <div class="list" id="tenantList"></div>
</div>

<div class="console" id="console"><span class="cx" onclick="document.getElementById('console').classList.remove('show')">&#10005;</span><div id="consoleBody"></div></div>
<div class="toast" id="toast"></div>

<script>
const DATA = __DATA__;
const ORCH = DATA.orch;
const APPID = DATA.appId;
let sel=null, selKind="step", scale=1, builtNo=DATA.buildNo-1, isBuilt=false;

const SVG_DB='<svg viewBox="0 0 24 24" width="15" height="15" fill="#fff"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></svg>';
const SVG_BR='<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="#fff" stroke-width="2.2"><path d="M9 4H6v16h3M15 4h3v16h-3"/></svg>';
const SVG_BRANCH='<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="#fff" stroke-width="2"><path d="M6 3v6M6 9a6 6 0 0 0 6 6h6M18 11l3-2-3-2M18 19l3-2-3-2"/></svg>';
const PLUG_SVG='<svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="#5a6472" stroke-width="1.5"><path d="M8 3v5M16 3v5M6 8h12v3a6 6 0 0 1-12 0V8z"/><path d="M12 17v4"/></svg>';
const MEGA_SVG='<svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="#5a6472" stroke-width="1.5"><path d="M3 11v2a1 1 0 0 0 1 1h2l9 5V6L6 11H4a1 1 0 0 0-1 0z"/><path d="M18 9a3 3 0 0 1 0 6"/></svg>';
const RABBIT_SVG='<svg viewBox="0 0 24 24" width="44" height="44" fill="none" stroke="#5a6472" stroke-width="1.4"><path d="M3 17c3 1 7 1 10-1 2-1.3 3-3.5 6-3.5 1.7 0 2.6 1 2.6 2s-1 1.8-2 1.8"/><path d="M7 15c-2 0-3.6 1.2-3.6 3"/><path d="M14 9c-.4-2.6.6-4.6 2.6-5.6M16.6 9.2c.6-2.6 2.4-3.8 4.4-3.8"/></svg>';
const BP_SVG='<svg viewBox="0 0 24 24" width="42" height="42" fill="none" stroke="#5a6472" stroke-width="1.4"><circle cx="12" cy="4" r="2"/><circle cx="4" cy="12" r="2"/><circle cx="20" cy="12" r="2"/><circle cx="12" cy="20" r="2"/><path d="M12 6v2M12 16v2M6 12h2M16 12h2M7.5 7.5l2 2M14.5 14.5l2 2M16.5 7.5l-2 2M9.5 14.5l-2 2"/></svg>';
const PLANE_SVG='<svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="#5a6472" stroke-width="1.4"><path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>';

// component catalog (exact names + categories)
const CAT = {
 "Data Requests": {cls:"dr", color:"#2f9e44", icon:SVG_DB, items:[
   ["Send Paged HTTP Request","send-paged-http-request"],
   ["Send HTTP Request","send-http-request"],
   ["Send Prism Request","send-prism-request"],
   ["Send Workday API Request","send-workday-api-request"],
   ["Send Workday RaaS Request","send-workday-raas-request"],
   ["Send Paged Workday REST Call","send-paged-workday-rest-call"],
   ["Send Paged Workday SOAP Call","send-paged-workday-soap-call"],
   ["Trigger Business Process","trigger-business-process"],
   ["Trigger Integration","trigger-integration"],
   ["Trigger PDF Generation","trigger-pdf-generation"]]},
 "Data Operations": {cls:"do", color:"#2563eb", icon:SVG_BR, items:[
   ["Create JSON","create-json"],
   ["Create Text Template","create-text-template"],
   ["Create Values","create-values"],
   ["Store Document","store-document"],
   ["Validate","validate"]]},
 "Orchestration Logic": {cls:"ol", color:"#e3472a", icon:SVG_BRANCH, items:[
   ["Batch Loop","batch-loop"],
   ["Branch on Conditions","branch-on-conditions"],
   ["Continue on Conditions","continue-on-conditions"],
   ["Join Loop","join-loop"],
   ["Log","log"],
   ["Loop","loop"]]},
 "Amazon Web Services (AWS)": {cls:"aws", color:"#d9730d", icon:SVG_BRANCH, items:[
   ["Put Amazon EventBridge Event","put-amazon-eventbridge-event"],
   ["Invoke AWS Lambda Function","invoke-aws-lambda-function"]]}
};
function typeMeta(type){
  for(const c in CAT){for(const it of CAT[c].items){if(it[1]===type)return {name:it[0],cls:CAT[c].cls,color:CAT[c].color,icon:CAT[c].icon};}}
  return {name:type,cls:"do",color:"#2563eb",icon:SVG_BR};
}
function defaultRef(type){return typeMeta(type).name.replace(/[^A-Za-z]/g,"");}

let dragType=null;
function buildPalette(){
  let h="";
  for(const c in CAT){
    const cat=CAT[c];
    h+="<div class='pal-cat "+cat.cls+"'>"+cat.icon.replace(/#fff/g,cat.color)+" "+c+"</div>";
    for(const it of cat.items){
      h+="<div class='pal-item' draggable='true' ondragstart='dragType=\""+it[1]+"\"' onclick='addStep(\""+it[1]+"\")'>"
        +it[0]+"<span class='dots'>&#10303;</span></div>";
    }
  }
  document.getElementById("palette").innerHTML=h;
}

function newStep(type){
  const s={id:"n"+Math.random().toString(36).slice(2,7),type:type,ref:defaultRef(type),props:defaults(type)};
  if(["loop","batch-loop","join-loop","branch-on-conditions","continue-on-conditions"].includes(type)) s.body=[];
  if(["loop","batch-loop"].includes(type)) s.aggregation={ref:"Aggregate",outputs:[],failWhenNoInputs:false,earlyStop:null,errorHandler:false,deleted:false};
  return s;
}
function defaults(type){
  if(type==="send-workday-raas-request")return{method:"GET",urlPrefix:"http://127.0.0.1:8443/task/view-report?name=",
    path:"",auth:"Default Workday API Credential",contentType:"Any"};
  if(type==="store-document")return{documentToStore:[],documentTitle:[],description:[],collection:[],
    expiresIn:"7",expiresUnit:"Days",attachToEvent:"true",deliver:"false"};
  if(type==="create-text-template")return{contentType:"application/json",message:""};
  if(type==="loop"||type==="batch-loop"||type==="join-loop")
    return{dataType:"AutoType Iterator",dataSetRef:"",dataSetPath:"",filterPath:"",sortBy:[],locale:""};
  if(type==="log")return{messageRef:"",condition:"true"};
  if(type==="create-json"||type==="create-values")return{values:[]};
  if(type==="validate")return{};
  if(type.startsWith("put-amazon")||type.startsWith("invoke-aws"))return{};
  if(type==="send-http-request")return{method:"GET",url:"",auth:"No Auth",advancedMode:false,queryParams:[]};
  if(type.startsWith("send-")||type.startsWith("trigger-"))return{method:"GET",url:"",auth:"Default Workday API Credential"};
  return{};
}
function addStep(type){ORCH.steps.push(newStep(type));render();save(true);}
function addToLoop(loopId,type){const l=findStep(ORCH.steps,loopId);if(!l)return;l.body=l.body||[];l.body.push(newStep(type));render();save(true);}
function findStep(steps,id){for(const s of (steps||[])){if(s.id===id)return s;if(s.body){const r=findStep(s.body,id);if(r)return r;}}return null;}
function removeStep(id){
  function rm(steps){const i=steps.findIndex(x=>x.id===id);if(i>=0){steps.splice(i,1);return true;}for(const x of steps){if(x.body&&rm(x.body))return true;}return false;}
  rm(ORCH.steps);if(sel&&sel.id===id)deselect();render();save(true);
}

/* ---- canvas ---- */
function render(){
  document.getElementById("crumb").textContent=DATA.appName;
  document.getElementById("orchName").textContent=ORCH.name;
  const sync=(ORCH.startType==="synchronous"||ORCH.startType==="asynchronous");
  const bp=(ORCH.startType==="business-process");
  let h="";
  if(bp){
    h+="<div class='card trigger'>"+BP_SVG+
       "<div class='tt'>Business Process Trigger</div>"+
       "<div class='ts'>Orchestration will listen for a business process request</div>"+
       "<a class='cfg'>Configure Request &#8594;</a></div>";
  } else if(sync){
    h+="<div class='card trigger'>"+RABBIT_SVG+
       "<div class='tt'>Orchestration Start</div>"+
       "<div class='ts'>Synchronous orchestration will immediately return an HTTP response</div>"+
       "<a class='cfg'>Configure Request &#8594;</a></div>";
  } else {
    h+="<div class='card trigger'>"+PLUG_SVG+
       "<div class='tt'>Integration Framework Trigger</div>"+
       "<div class='ts'>Orchestration will be triggered by a Workday integration system</div>"+
       "<a class='cfg'>Configure Parameters &#8594;</a></div>";
  }
  ORCH.steps.forEach(s=>{ h+="<div class='conn'></div>"+renderStep(s); });
  h+="<div class='conn'></div>";
  if(bp){
    h+="<div class='card end'>"+MEGA_SVG+
       "<div class='et'>Orchestration End</div>"+
       "<div class='ts'>Business process will respond based on its own configuration</div></div>";
  } else if(sync){
    h+="<div class='card end'>"+PLANE_SVG+
       "<div class='et'>Orchestration End</div>"+
       "<div class='ts'>Setup response format to share with requesting service</div>"+
       "<a class='cfg'>Configure Response &#8594;</a></div>";
  } else {
    h+="<div class='card end'>"+MEGA_SVG+"<div class='et'>Orchestration End</div></div>";
  }
  const flow=document.getElementById("flow");
  flow.innerHTML=h; flow.style.transform="scale("+scale+")"; flow.style.transformOrigin="top center";
  attachLoopDnD();
}
function renderStep(s){
  const m=typeMeta(s.type);
  const isLoop=["loop","batch-loop","join-loop"].includes(s.type);
  let h="<div class='card step "+m.cls+(selKind==='step'&&sel&&sel.id===s.id?" sel":"")+"' onclick='select(\""+s.id+"\")'>"+
     "<span class='menu' onclick='event.stopPropagation();removeStep(\""+s.id+"\")'>&#8942;</span>"+
     "<span class='badge' style='background:"+m.color+"'>"+m.icon+"</span>"+
     "<div class='ctype'>"+m.name.toUpperCase()+"</div>"+
     "<div class='cref'>"+esc(s.ref)+"</div></div>";
  if(isLoop){
    h+="<div class='conn'></div>";
    h+="<div class='loopwrap' data-loop='"+s.id+"'>";
    h+="<div class='loopchev'>&#94;</div>";
    const body=s.body||[];
    body.forEach((c,i)=>{ if(i)h+="<div class='conn'></div>"; h+=renderStep(c); });
    if(!body.length) h+="<div class='loopdrop'>Drop a step here to run it inside the loop</div>";
    const agg=s.aggregation;
    if(agg){
      const faint=agg.deleted?" faint":"";
      h+="<div class='conn'></div><div class='aggbar"+faint+(selKind==='aggregate'&&sel&&sel.id===s.id?" sel":"")+"' onclick='enableAgg(\""+s.id+"\")'>CONFIGURE AGGREGATION"+
         "<span class='aggmenu' onclick='event.stopPropagation();toggleAggMenu(event,\""+s.id+"\")'>&#8943;</span></div>";
    }
    h+="</div>";
  }
  return h;
}
function esc(t){return (t||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
function jv(t){return esc(t).replace(/'/g,"&#39;");}
function pathStr(p){return Array.isArray(p)? p.map(t=>t.v).join("") : (p||"");}
function zoom(d){if(d===0)scale=1;else scale=Math.max(.5,Math.min(1.6,scale+d*.1));render();}

/* drag onto canvas */
document.getElementById("canvasWrap").addEventListener("dragover",e=>e.preventDefault());
document.getElementById("canvasWrap").addEventListener("drop",e=>{e.preventDefault();if(dragType){addStep(dragType);dragType=null;}});

/* ---- select + properties ---- */
function select(id){sel=findStep(ORCH.steps,id);selKind="step";closeAggMenu();render();renderProps();}
function selectAgg(loopId){sel=findStep(ORCH.steps,loopId);selKind="aggregate";closeAggMenu();render();renderProps();}
function enableAgg(id){const l=findStep(ORCH.steps,id);if(l&&l.aggregation)l.aggregation.deleted=false;selectAgg(id);save(true);}
function deselect(){sel=null;selKind="step";document.getElementById("props").classList.remove("show");render();}
function setRef(v){sel.ref=v;render();}
function setp(k,v){sel.props[k]=v;}

function renderProps(){
  if(!sel)return;
  if(selKind==="aggregate"){renderAggProps();return;}
  const m=typeMeta(sel.type);
  document.getElementById("pIcon").innerHTML="<span style='display:inline-flex;width:26px;height:26px;border-radius:7px;align-items:center;justify-content:center;background:"+m.color+"'>"+m.icon+"</span>";
  document.getElementById("pType").textContent=m.name;
  let h="<div class='fld'><label>Reference Name <span class='req'>*</span></label>"+
        "<input value='"+esc(sel.ref)+"' oninput='setRef(this.value)' onchange='save(true)'></div>";
  if(sel.type==="send-workday-raas-request"){
    sel.props.path = pathStr(sel.props.path);
    h+="<div class='reqrow'>"+
       "<select onchange='setp(\"method\",this.value);save(true)'>"+opts(['GET','POST','PUT','DELETE'],sel.props.method)+"</select>"+
       "<input class='urlp' value='"+jv(sel.props.urlPrefix)+"' placeholder='http://127.0.0.1:8443/task/view-report?name=' "+
       "oninput='setp(\"urlPrefix\",this.value)' onchange='save(true)'>"+
       "<input class='urlp pathin' value='"+jv(sel.props.path)+"' placeholder='report name' "+
       "oninput='setp(\"path\",this.value)' onchange='save(true)'></div>";
    h+="<div class='tabs'><a class='active'>General</a><a>Headers</a><a>Query Parameters</a><a>Settings</a></div>";
    h+="<p class='hint'>Both fields are editable (no hardcoding). Base URL + report name, e.g. "+
       "<code>http://127.0.0.1:8443/task/view-report?name=</code> + <code>CRT_INT01_Raas</code>. "+
       "<b>Run</b> / <b>Launch</b> fetches that URL live and feeds the result into the next step.</p>";
    h+="<p class='hint'>Select a saved credential. To create a new authentication credential, <a href='#'>open settings</a>.</p>";
    h+="<div class='fld'><label>Authentication</label><select onchange='setp(\"auth\",this.value);save(true)'>"+
       opts(['Default Workday API Credential','Access Token from Initiating User'],sel.props.auth)+"</select></div>";
    h+="<div class='fld'><label>Content Type</label><select onchange='setp(\"contentType\",this.value);save(true)'>"+
       opts(['Any','application/json','text/xml'],sel.props.contentType)+"</select></div>";
  } else if(sel.type==="store-document"){
    h+="<div class='tabs'><a class='active'>General</a><a>Settings</a></div>";
    h+=tokField("Document to Store","documentToStore",true);
    h+=tokField("Document Title","documentTitle",true);
    h+=tokField("Description","description",false);
    h+=tokField("Collection to Store Document In","collection",false);
    h+="<p class='hint'>Collection will default to Integration System WID if not overwritten.</p>";
    h+="<div class='fld'><label>Storage Expires In</label><div style='display:flex;gap:8px'>"+
       "<input style='width:90px' value='"+esc(sel.props.expiresIn)+"' oninput='setp(\"expiresIn\",this.value)'>"+
       "<select onchange='setp(\"expiresUnit\",this.value)'>"+opts(['Days','Hours','Weeks'],sel.props.expiresUnit)+"</select></div></div>";
    h+="<div class='fld'><label>Attach document to integration event <span class='req'>*</span></label>"+
       "<select onchange='setp(\"attachToEvent\",this.value)'>"+opts(['true','false'],sel.props.attachToEvent)+"</select></div>";
    h+="<div class='fld'><label>Deliver from associated delivery services <span class='req'>*</span></label>"+
       "<select onchange='setp(\"deliver\",this.value)'>"+opts(['true','false'],sel.props.deliver)+"</select></div>";
  } else if(sel.type==="create-text-template"){
    h+="<div class='fld'><label>Content Type <span class='req'>*</span></label>"+
       "<input value='"+jv(sel.props.contentType||'')+"' oninput='setp(\"contentType\",this.value)' onchange='save(true)'></div>";
    h+="<div class='fld'><label>Message</label><textarea class='code' spellcheck='false' oninput='setp(\"message\",this.value)' onchange='save(true)'>"+esc(sel.props.message||'')+"</textarea></div>";
  } else if(["loop","batch-loop","join-loop"].includes(sel.type)){
    h+=loopPropsHtml();
  } else if(sel.type==="log"){
    h+=logPropsHtml();
  } else if(sel.type==="send-http-request"){
    h+="<div class='fld'><label style='display:inline-flex;align-items:center;gap:8px;font-weight:600'>"+
       "<input type='checkbox' "+(sel.props.advancedMode?'checked':'')+" onchange='setp(\"advancedMode\",this.checked);save(true)'> Advanced Mode</label></div>";
    h+="<div class='reqrow'>"+
       "<select onchange='setp(\"method\",this.value);save(true)'>"+opts(['GET','POST','PUT','DELETE','PATCH'],sel.props.method||'GET')+"</select>"+
       "<input class='urlp' value='"+esc(sel.props.url||'')+"' placeholder='https://api.example.com/v3/...' "+
       "oninput='setp(\"url\",this.value)' onchange='save(true)'></div>";
    h+="<div class='tabs'><a class='active'>Auth</a><a>Body</a><a>Headers</a><a>Query Parameters</a><a>Settings</a></div>";
    h+="<p class='hint'><b>Specify Authentication.</b> Pick a saved credential, or <b>No Auth</b> for public APIs. "+
       "<b>Run</b> fires a real GET to this URL and feeds the JSON into the next step.</p>";
    h+="<div class='fld'><label>Authentication</label><select onchange='setp(\"auth\",this.value);save(true)'>"+
       opts(['No Auth','Default Workday API Credential','Access Token from Initiating User'],sel.props.auth||'No Auth')+"</select></div>";
    sel.props.queryParams=sel.props.queryParams||[];
    h+="<div style='margin-top:18px;font-weight:700'>Query Parameters</div>";
    h+="<p class='hint'>Key/Value pairs appended to the URL after <code>?</code> and separated by <code>&amp;</code>.</p>";
    h+="<table class='aggtbl'><tr><th>Parameter</th><th>Value</th><th></th></tr>";
    sel.props.queryParams.forEach(function(q,i){
      h+="<tr><td><input value='"+jv(q.key)+"' placeholder='apiKey' oninput='setQP("+i+",\"key\",this.value)' onchange='save(true)'></td>"+
         "<td><input value='"+jv(q.value)+"' placeholder='Enter a value' oninput='setQP("+i+",\"value\",this.value)' onchange='save(true)'></td>"+
         "<td style='text-align:center'><span class='trash' onclick='rmQP("+i+")'>&#128465;</span></td></tr>";
    });
    h+="</table><a class='addlink' onclick='addQP()'>+ Add Parameter</a>";
    h+="<p class='hint'>Self-contained demo endpoint: <code>http://127.0.0.1:8443/orchestrate/mock-api/stock?ticker=AAPL</code>. "+
       "Swap in a real API (Polygon, Alpha Vantage) anytime.</p>";
  } else if(sel.type==="create-values"||sel.type==="create-json"){
    sel.props.values=sel.props.values||[];
    h+="<p class='hint'>Extract data points from a previous step using JSON path. "+
       "e.g. <code>SendHTTPRequest.response</code> + <code>$.results[0].o</code> for the daily open price.</p>";
    h+="<table class='aggtbl'><tr><th>Name</th><th>Source (Step.response)</th><th>JSON Path</th><th></th></tr>";
    sel.props.values.forEach(function(v,i){
      h+="<tr><td><input value='"+jv(v.name)+"' oninput='setCV("+i+",\"name\",this.value)' onchange='save(true)'></td>"+
         "<td><input value='"+jv(v.sourceRef)+"' placeholder='SendHTTPRequest.response' oninput='setCV("+i+",\"sourceRef\",this.value)' onchange='save(true)'></td>"+
         "<td><input value='"+jv(v.jsonPath)+"' placeholder='$.results[0].o' oninput='setCV("+i+",\"jsonPath\",this.value)' onchange='save(true)'></td>"+
         "<td style='text-align:center'><span class='trash' onclick='rmCV("+i+")'>&#128465;</span></td></tr>";
    });
    h+="</table><a class='addlink' onclick='addCV()'>+ Add Value</a>";
  } else {
    h+="<div class='reqrow'><select onchange='setp(\"method\",this.value)'>"+opts(['GET','POST','PUT','DELETE'],sel.props.method||'GET')+"</select>"+
       "<input class='urlp' value='"+esc(sel.props.url||'')+"' placeholder='https://...' oninput='setp(\"url\",this.value)' onchange='save(true)'></div>";
    h+="<div class='fld' style='margin-top:14px'><label>Authentication</label><select onchange='setp(\"auth\",this.value)'>"+
       opts(['Default Workday API Credential','Access Token from Initiating User'],sel.props.auth||'Default Workday API Credential')+"</select></div>";
  }
  const pb=document.getElementById("pBody");pb.innerHTML=h;
  document.getElementById("props").classList.add("show");
  if(sel.type==="store-document"){["documentToStore","documentTitle","description","collection"].forEach(k=>tfRefresh(k));}
  document.querySelectorAll(".tabs a").forEach(t=>t.onclick=function(){
    this.parentNode.querySelectorAll("a").forEach(x=>x.classList.remove("active"));this.classList.add("active");});
}
function opts(arr,cur){return arr.map(o=>"<option"+(o===cur?" selected":"")+">"+o+"</option>").join("");}

/* ---- token fields + expression builder picker ---- */
function tokField(label,key,req){
  return "<div class='fld'><label>"+label+(req?" <span class='req'>*</span>":"")+"</label>"+
         "<div class='tokfield' id='tf_"+key+"'></div></div>";
}
function renderTok(elId,key,inline){
  const el=document.getElementById(elId)||document.getElementById("tf_"+key);
  if(!el)return;
  const toks=sel.props[key]||[];
  let h="";
  toks.forEach((t,i)=>{h+="<span class='tok "+(t.t==='ref'?'ref':'string')+"'>"+esc(t.v)+
    " <span class='rm' onclick='rmTok(\""+key+"\","+i+")'>&#10005;</span></span>";});
  h+="<button class='addbtn' onclick='openPicker(event,\""+key+"\")'>+</button>";
  if(!inline)h+="<button class='insbtn' onclick='openPicker(event,\""+key+"\",true)'>&#8599;</button>";
  el.innerHTML=h;
}
function tfRefresh(key){renderTok("tf_"+key,key,false);}
function rmTok(key,i){sel.props[key].splice(i,1);(key==='path'?renderTok("tw_path",key,true):tfRefresh(key));}
function openPicker(ev,key,refOnly){
  ev.stopPropagation();
  closePicker();
  const wrap=ev.target.closest(".tokfield")||ev.target.closest(".tokwrap");
  const steps=ORCH.steps.filter(s=>s.id!==(sel?sel.id:''));
  let subs="";
  steps.forEach(s=>{
    const m=typeMeta(s.type);
    subs+="<div class='grp'>&#9660; <span class='stepname' style='color:"+m.color+"'>"+m.name.toUpperCase()+"</span> "+esc(s.ref)+"</div>";
    subs+="<div class='sub' onclick='pickRef(\""+key+"\",\""+s.ref+".response\")'><b>response</b><i>Data</i></div>";
    subs+="<div class='sub' onclick='pickRef(\""+key+"\",\""+s.ref+".responseHeaders\")'><b>responseHeaders</b><i>Headers</i></div>";
    subs+="<div class='sub' onclick='pickRef(\""+key+"\",\""+s.ref+".responseStatusCode\")'><b>responseStatusCode</b><i>Number</i></div>";
  });
  const p=document.createElement("div");p.className="picker";p.id="picker";
  p.innerHTML="<div class='typ'><input id='pickType' placeholder='Type here' oninput='pickTyping(\""+key+"\",this.value)'></div>"+
    "<div id='pickResults'><div class='grp'>{ } Data from Orchestration Steps</div>"+subs+
    "<div class='grp'><i>fx</i> Global Functions <span style='margin-left:auto'>&#8250;</span></div></div>"+
    "<div class='add'>&#129518; Explore All Functions</div>";
  wrap.style.position="relative";wrap.appendChild(p);
  setTimeout(()=>document.getElementById("pickType").focus(),0);
}
function pickTyping(key,val){
  const r=document.getElementById("pickResults");if(!r)return;
  if(val.trim()){r.innerHTML="<div class='add' onclick='pickStr(\""+key+"\",\""+val.replace(/\\/g,"").replace(/\"/g,"")+"\")'>+ Add string \""+esc(val)+"\"</div>"+
    "<div style='padding:14px 12px;color:#8a909a'>No Results Found.</div>";}
}
function pickStr(key,val){sel.props[key]=sel.props[key]||[];sel.props[key].push({t:"string",v:val});afterPick(key);}
function pickRef(key,ref){sel.props[key]=sel.props[key]||[];sel.props[key].push({t:"ref",v:ref});afterPick(key);}
function afterPick(key){closePicker();(key==='path'?renderTok("tw_path",key,true):tfRefresh(key));save(true);}
function closePicker(){const p=document.getElementById("picker");if(p)p.remove();}
document.addEventListener("click",e=>{if(!e.target.closest(".picker")&&!e.target.closest(".addbtn")&&!e.target.closest(".insbtn"))closePicker();});

/* ---- actions: save / validate / build / deploy / run ---- */
function toast(m){const t=document.getElementById("toast");t.textContent=m;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),1600);}
function save(silent){fetch("/orchestrate/api/save",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({appId:APPID,orch:ORCH})}).then(r=>r.json()).then(d=>{
    if(!silent){toast("Saved");}document.getElementById("saved").textContent="Saved to session less than a minute ago.";});}
function validate(){fetch("/orchestrate/api/validate",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({orch:ORCH})}).then(r=>r.json()).then(d=>{
    const b=document.getElementById("errBadge");
    if(d.ok){b.style.display="none";showConsole("build","<div class='ok'>&#10003; Validation passed.</div>");}
    else{b.style.display="flex";document.getElementById("errCount").textContent=d.issues.length;
      showConsole("build",d.issues.map(i=>"<div class='er'>&#9888; "+esc(i)+"</div>").join(""));}});}
function onDeploy(){
  const btn=document.getElementById("deployBtn");
  btn.textContent="Building";btn.classList.add("disabled");
  fetch("/orchestrate/api/build",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({appId:APPID,orch:ORCH})}).then(r=>r.json()).then(d=>{
      builtNo=d.buildNo;isBuilt=true;
      btn.innerHTML="Built &#10004;";btn.classList.remove("disabled");
      document.getElementById("saveAll").classList.add("disabled");
      document.getElementById("bn").textContent=d.buildNo;
      let h="";d.tenants.forEach(t=>{h+="<div class='trow'><b>"+t+"</b>"+
        "<button class='btn' onclick='doDeploy(\""+t+"\")'>Deploy</button></div>";});
      document.getElementById("tenantList").innerHTML=h;
      document.getElementById("deploy").classList.add("show");
    });
}
function doDeploy(tenant){
  fetch("/orchestrate/api/deploy",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({appId:APPID,orch:ORCH,tenant:tenant})}).then(r=>r.json()).then(d=>{
      document.getElementById("deploy").classList.remove("show");
      toast("Deployed to "+tenant);
      showConsole("build","<div class='ok'>&#10003; Deployed '"+ORCH.name+"' to "+tenant+
        ".</div><div class='mut'>Tenant Integration System created: "+d.isId+
        "</div><div><a style='color:#7fb4ff' href='/orchestrate/tenant/integration-system/"+d.isId+
        "'>Open View Integration System &#8594;</a> &nbsp; then Actions &#8250; Integration &#8250; Launch/Schedule to produce RAAS DATA.</div>");
    });
}
function run(){fetch("/orchestrate/api/run",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({orch:ORCH})}).then(r=>r.json()).then(d=>{
    let h="<div><b>"+d.status.toUpperCase()+"</b> &middot; "+d.durationMs+" ms</div>";
    d.trace.forEach(e=>{h+="<div><span class='"+(e.status==='Error'?'er':'ok')+"'>["+e.status+"]</span> "+esc(e.step)+" <span class='mut'>"+esc(e.message)+"</span></div>";});
    d.outputFiles.forEach(f=>{h+="<div class='mut'>output file: "+esc(f.title)+" ("+f.type+")</div>";});
    showConsole("run",h);});}
function showConsole(kind,html){const c=document.getElementById("console");
  document.getElementById("consoleBody").innerHTML=(kind==='run'?"<div class='mut'>RUN LOGS</div>":"<div class='mut'>BUILD LOGS</div>")+html;
  c.classList.add("show");}
function toggleConsole(kind){if(kind==='run')run();else{const c=document.getElementById("console");c.classList.toggle("show");}}

/* ---- loop / log / aggregate property panels ---- */
function loopPropsHtml(){
  const p=sel.props;
  let h="<div class='fld'><label>Data Type <span class='req'>*</span></label>"+
    "<select onchange='setp(\"dataType\",this.value);save(true)'>"+
    opts(['AutoType Iterator','JSON Iterator','Text Iterator','Number Range'],p.dataType)+"</select></div>";
  h+="<div class='fld'><label>Data Set <span class='req'>*</span></label><div class='chiprow'>"+
     "<input class='chip cref' value='"+jv(p.dataSetRef)+"' placeholder='Step.field' oninput='setp(\"dataSetRef\",this.value)' onchange='save(true)'>"+
     "<span class='chip cfn'>iterator</span>"+
     "<input class='chip cjp' value='"+jv(p.dataSetPath)+"' placeholder='$.path[*]' oninput='setp(\"dataSetPath\",this.value)' onchange='save(true)'></div></div>";
  h+="<div class='fld'><label>Filter</label><div class='chiprow'>"+
     "<span class='chip citem'>Loop.item</span><span class='chip cfn'>booleanAtJsonPath</span>"+
     "<input class='chip cjp' value='"+jv(p.filterPath)+"' placeholder='$.active' oninput='setp(\"filterPath\",this.value)' onchange='save(true)'></div></div>";
  h+="<div class='fld'><label>Sort By</label>";
  (p.sortBy||[]).forEach((sb,i)=>{
    h+="<div class='chiprow'><span class='chip citem'>Loop.item</span><span class='chip cfn'>jsonDataAtJsonPath</span>"+
       "<input class='chip cjp' value='"+jv(sb.path)+"' placeholder='$.role' oninput='setSort("+i+",this.value)' onchange='save(true)'>"+
       "<span class='chip cfn'>toString</span>"+
       "<span class='sortdir' title='direction' onclick='toggleSort("+i+")'>"+(sb.dir==='desc'?'&#8595;':'&#8593;')+"</span>"+
       "<span class='chiprm' onclick='rmSort("+i+")'>&#10005;</span></div>";
  });
  h+="<a class='addlink' onclick='addSort()'>+ Add Sort By</a></div>";
  h+="<div class='fld'><label>Locale</label><div class='chiprow'>"+
     "<input class='chip cjp' style='min-width:140px' value='"+jv(p.locale)+"' placeholder='(optional)' oninput='setp(\"locale\",this.value)' onchange='save(true)'></div></div>";
  return h;
}
function setSort(i,v){sel.props.sortBy[i].path=v;}
function toggleSort(i){sel.props.sortBy[i].dir=(sel.props.sortBy[i].dir==='desc'?'asc':'desc');renderProps();save(true);}
function rmSort(i){sel.props.sortBy.splice(i,1);renderProps();save(true);}
function addSort(){sel.props.sortBy=sel.props.sortBy||[];sel.props.sortBy.push({path:"",dir:"asc"});renderProps();save(true);}

function logPropsHtml(){
  const p=sel.props;
  let h="<div class='fld'><label>Message <span class='req'>*</span></label><div class='chiprow'>"+
    "<input class='chip' style='flex:1' value='"+jv(p.message!=null?p.message:'')+"' placeholder='USER ADDED - ORCHESTRATION HIT' oninput='setp(\"message\",this.value)' onchange='save(true)'></div></div>";
  h+="<div class='fld'><label>Or reference a step value</label><div class='chiprow'>"+
    "<input class='chip cref' value='"+jv(p.messageRef||'')+"' placeholder='Loop.item' oninput='setp(\"messageRef\",this.value)' onchange='save(true)'>"+
    "<span class='chip cfn'>toString</span></div></div>";
  h+="<div class='fld'><label>Condition <span class='req'>*</span></label><div class='chiprow'>"+
    "<input class='chip cbool' value='"+jv(p.condition||'true')+"' oninput='setp(\"condition\",this.value)' onchange='save(true)'></div></div>";
  return h;
}

function renderAggProps(){
  const agg=sel.aggregation;
  document.getElementById("pIcon").innerHTML="<span style='display:inline-flex;width:26px;height:26px;border-radius:7px;align-items:center;justify-content:center;background:#e3472a'>"+SVG_BRANCH+"</span>";
  document.getElementById("pType").textContent="Aggregate";
  let h="<div class='fld'><label>Reference Name <span class='req'>*</span></label>"+
    "<input value='"+esc(agg.ref)+"' oninput='sel.aggregation.ref=this.value' onchange='save(true)'></div>";
  h+="<p class='hint'>Add outputs from the data to aggregate.</p>";
  h+="<table class='aggtbl'><tr><th>Name</th><th>Strategy</th><th>Delete</th><th>Errors</th></tr>";
  (agg.outputs||[]).forEach((o,i)=>{
    h+="<tr><td><input value='"+jv(o.name)+"' oninput='setAgg("+i+",\"name\",this.value)' onchange='save(true)'></td>"+
       "<td><select onchange='setAgg("+i+",\"strategy\",this.value);save(true)'>"+opts(['JSON','Text','Count'],o.strategy)+"</select></td>"+
       "<td style='text-align:center'><span class='trash' onclick='rmAgg("+i+")'>&#128465;</span></td><td></td></tr>";
  });
  h+="</table><a class='addlink' onclick='addAgg()'>+ Add Output</a>";
  h+="<div class='aggopt'><label>Fail When No Inputs</label>"+
     "<input type='checkbox' "+(agg.failWhenNoInputs?'checked':'')+" onchange='sel.aggregation.failWhenNoInputs=this.checked;save(true)'></div>";
  if(agg.earlyStop!=null){
    h+="<div class='fld'><label>Early Stop Condition (booleanAtJsonPath on item)</label>"+
       "<input value='"+jv(agg.earlyStop)+"' placeholder='$.stop' oninput='sel.aggregation.earlyStop=this.value' onchange='save(true)'></div>";
  }
  if(agg.errorHandler){h+="<p class='hint'>Error Handler attached to this aggregation.</p>";}
  if(!(agg.outputs||[]).length){
    h+="<div class='aggempty'><b>No Output Strategy Selected</b><br>Configuration options will appear once an output with a strategy is added.</div>";
  }
  document.getElementById("pBody").innerHTML=h;
  document.getElementById("props").classList.add("show");
}
function setAgg(i,k,v){sel.aggregation.outputs[i][k]=v;}
function rmAgg(i){sel.aggregation.outputs.splice(i,1);renderProps();save(true);}
function addAgg(){sel.aggregation.outputs.push({name:"Output"+(sel.aggregation.outputs.length+1),strategy:"JSON"});renderProps();save(true);}

/* ---- create values (JSON path extraction) ---- */
function setCV(i,k,v){sel.props.values[i][k]=v;}
function rmCV(i){sel.props.values.splice(i,1);renderProps();save(true);}
function addCV(){sel.props.values=sel.props.values||[];sel.props.values.push({name:"Value"+(sel.props.values.length+1),sourceRef:"SendHTTPRequest.response",jsonPath:"$."});renderProps();save(true);}

/* ---- query parameters (Send HTTP Request) ---- */
function setQP(i,k,v){sel.props.queryParams[i][k]=v;}
function rmQP(i){sel.props.queryParams.splice(i,1);renderProps();save(true);}
function addQP(){sel.props.queryParams=sel.props.queryParams||[];sel.props.queryParams.push({key:"",value:""});renderProps();save(true);}

/* ---- aggregation context menu ---- */
function toggleAggMenu(ev,loopId){
  if(document.getElementById("aggmenupop")){closeAggMenu();return;}
  const items=[["Delete","removeStep('"+loopId+"')"],["Rename","selectAgg('"+loopId+"')"],
    ["Duplicate",""],["Open Node","selectAgg('"+loopId+"')"],["Delete Aggregation","delAgg('"+loopId+"')"],
    ["Add Early Stop Condition","addEarlyStop('"+loopId+"')"],["Add Error Handler","addErrHandler('"+loopId+"')"],["Disable",""]];
  const m=document.createElement("div");m.className="aggmenupop";m.id="aggmenupop";
  m.innerHTML=items.map(it=>"<div class='ami' onclick=\"closeAggMenu();"+it[1]+"\">"+it[0]+"</div>").join("");
  document.body.appendChild(m);
  const r=ev.target.getBoundingClientRect();
  m.style.left=Math.min(r.left,window.innerWidth-220)+"px";m.style.top=(r.bottom+4)+"px";
}
function closeAggMenu(){const m=document.getElementById("aggmenupop");if(m)m.remove();}
function delAgg(id){const l=findStep(ORCH.steps,id);if(l&&l.aggregation)l.aggregation.deleted=true;if(sel&&sel.id===id&&selKind==="aggregate")deselect();render();save(true);}
function addEarlyStop(id){const l=findStep(ORCH.steps,id);if(l&&l.aggregation){l.aggregation.deleted=false;if(l.aggregation.earlyStop==null)l.aggregation.earlyStop="$.stop";}selectAgg(id);save(true);}
function addErrHandler(id){const l=findStep(ORCH.steps,id);if(l&&l.aggregation){l.aggregation.deleted=false;l.aggregation.errorHandler=true;}selectAgg(id);save(true);}
document.addEventListener("click",function(e){if(!e.target.closest(".aggmenupop")&&!e.target.closest(".aggmenu"))closeAggMenu();});

/* ---- drop steps into a loop ---- */
function attachLoopDnD(){
  document.querySelectorAll(".loopwrap").forEach(w=>{
    w.ondragover=function(e){e.preventDefault();e.stopPropagation();w.classList.add("over");};
    w.ondragleave=function(){w.classList.remove("over");};
    w.ondrop=function(e){e.preventDefault();e.stopPropagation();w.classList.remove("over");
      if(dragType){addToLoop(w.dataset.loop,dragType);dragType=null;}};
  });
}

buildPalette();render();
</script>
</body></html>
"""
