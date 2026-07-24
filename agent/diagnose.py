"""
agent/diagnose.py -- AI Diagnostic Agent for Workday-style integration pipelines.
Agents of SigNoz hackathon | Track 01: AI & Agent Observability.

Pipeline:
  1. signoz_search_traces      -> newest ERROR trace for the target service
  2. signoz_get_trace_details  -> full span tree
  3. locate failing span(s), extract attributes + events
  4. rule-table diagnosis mapped to Workday semantics
  5. optional: Claude API composes a narrative report (needs ANTHROPIC_API_KEY)

Usage:
  python diagnose.py                 # diagnose newest failed orchestration
  python diagnose.py --trace <id>    # diagnose a specific trace
  python diagnose.py --raw           # also dump raw tool responses (debug)
"""

import asyncio
import json
import os
import re
import sys

MCP_URL = os.environ.get("SIGNOZ_MCP_URL", "http://localhost:8000/mcp")
SERVICE = os.environ.get("AGENT_SERVICE", "mock-workday-orchestrate")
TIME_RANGE = os.environ.get("AGENT_TIME_RANGE", "6h")
RAW = "--raw" in sys.argv


def load_secret(name):
    v = os.environ.get(name)
    if v:
        return v.strip()
    for path in ("secrets.env", "../secrets.env", "../../secrets.env"):
        try:
            with open(path) as f:
                for line in f:
                    if line.startswith(name + "="):
                        return line.split("=", 1)[1].strip()
        except FileNotFoundError:
            continue
    return None


API_KEY = load_secret("SIGNOZ_API_KEY") or sys.exit("SIGNOZ_API_KEY not found")
ANTHROPIC_KEY = load_secret("ANTHROPIC_API_KEY")  # optional

HEADERS = {"SIGNOZ-API-KEY": API_KEY, "Authorization": "Bearer " + API_KEY}

# ---------------------------------------------------------------- diagnosis table
DIAGNOSIS_TABLE = [
    (re.compile(r"HTTP 400|Bad Request", re.I),
     "Malformed request payload or WQL filter",
     "A 400 in Workday integrations usually means a malformed WQL query, often an "
     "unescaped apostrophe in a name-based filter, or an invalid request body.",
     ["Switch WQL filters from name-based matching to ID-based (WID / Reference ID)",
      "Validate and escape user-supplied filter values",
      "Re-run the failed step and confirm a 200 with expected row count"]),
    (re.compile(r"HTTP 401|Unauthorized|token expired", re.I),
     "ISU authentication failure (expired/invalid OAuth token)",
     "The Integration System User's token was rejected. Refresh tokens can be "
     "invalidated when credentials rotate or the API client is re-registered.",
     ["Re-authenticate the ISU and obtain a fresh access token",
      "Verify the refresh token is still valid in the API Client configuration",
      "Confirm client_id/client_secret match the registered API Client"]),
    (re.compile(r"HTTP 403|Forbidden|lacks domain security", re.I),
     "ISSG missing domain security policy permission",
     "The Integration System User authenticated successfully but its security group "
     "(ISSG) lacks Get/Put access on the target domain (e.g. Supervisory Org data).",
     ["Grant the ISU's security group the required domain security policy permission",
      "Activate pending security policy changes in the tenant",
      "Re-run the step; a 200/201 confirms the grant took effect"]),
    (re.compile(r"HTTP 404|Not Found", re.I),
     "Target object reference not found in tenant",
     "The referenced object (e.g. supervisory organization) does not exist. A prior "
     "step may have produced a wrong or stale reference ID.",
     ["Validate the reference ID produced by the upstream step",
      "Check whether the object exists in the tenant (or was recently inactivated)",
      "Add an existence check step before the failing call"]),
    (re.compile(r"HTTP 409|already exists", re.I),
     "Duplicate object conflict (409)",
     "The tenant rejected the create because an object with the same reference ID "
     "already exists.",
     ["Use a new unique reference ID, or switch the call to an update operation",
      "Add a pre-check step (exists?) and branch create-vs-update accordingly"]),
    (re.compile(r"timed out|timeout", re.I),
     "Downstream timeout",
     "The downstream endpoint did not respond within the client limit. For RaaS this "
     "often means a long-running report; for SOAP, an overloaded service.",
     ["Increase the client timeout for this step",
      "For RaaS: filter the report server-side or split it into smaller requests",
      "Check downstream service health/latency in SigNoz service metrics"]),
    (re.compile(r"0 rows|empty result|result_count.?[:=]\s*0", re.I),
     "Empty result set broke downstream extraction",
     "A query returned zero rows and a downstream widget/extraction step assumed at "
     "least one element (e.g. $[0].descriptor).",
     ["Verify the filter values produced by the prior step",
      "Add an empty-result guard before extraction steps",
      "Confirm the queried data exists for the given effective date"]),
]


def diagnose_text(text):
    for pattern, cause, explanation, fixes in DIAGNOSIS_TABLE:
        if pattern.search(text or ""):
            return cause, explanation, fixes
    return ("Unclassified failure",
            "The failure did not match a known Workday integration pattern.",
            ["Inspect the span events and correlated logs in SigNoz for details"])


# ---------------------------------------------------------------- helpers
def walk(obj):
    """Yield every dict nested anywhere inside obj."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def first_key(d, *names):
    for n in names:
        for k, v in d.items():
            if k.lower() == n.lower():
                return v
    return None


def tool_json(result):
    """Parse MCP tool result content into JSON. Tries each text chunk alone,
    then the joined blob; returns (parsed_or_None, raw_blob)."""
    texts = [getattr(c, "text", "") or "" for c in result.content]
    blob = "\n".join(t for t in texts if t)
    for candidate in texts + [blob]:
        candidate = (candidate or "").strip()
        if not candidate:
            continue
        try:
            return json.loads(candidate), blob
        except Exception:
            continue
    return None, blob


# ---------------------------------------------------------------- agent core
async def run():
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    trace_id_arg = None
    if "--trace" in sys.argv:
        trace_id_arg = sys.argv[sys.argv.index("--trace") + 1]

    async with streamablehttp_client(MCP_URL, headers=HEADERS) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()

            # ---- 1. find the newest ERROR trace ------------------------------
            trace_id = trace_id_arg
            if not trace_id:
                res = await s.call_tool("signoz_search_traces", arguments={
                    "service": SERVICE, "error": True,
                    "limit": 10, "timeRange": TIME_RANGE,
                })
                data, blob = tool_json(res)
                if RAW:
                    print("--- search_traces raw ---\n", blob[:4000], "\n---")
                candidates = []
                seen = set()
                for d in walk(data if data is not None else {}):
                    inner = d.get("data") if isinstance(d.get("data"), dict) else None
                    tid = None
                    ts = None
                    if inner is not None:
                        tid = first_key(inner, "traceID", "trace_id", "traceId")
                        ts = (first_key(d, "timestamp", "startTime", "time")
                              or first_key(inner, "timestamp", "startTime", "time"))
                    if not tid:
                        tid = first_key(d, "traceID", "trace_id", "traceId")
                        ts = ts or first_key(d, "timestamp", "startTime", "time")
                    if tid and tid not in seen:
                        seen.add(tid)
                        candidates.append((str(ts or ""), tid))
                if not candidates:
                    # bulletproof fallback: pull trace ids straight from raw text
                    ids = re.findall(r'"trace_?[iI][dD]"\s*:\s*"([0-9a-fA-F]{16,32})"',
                                     blob or "")
                    times = re.findall(r'"timestamp"\s*:\s*"([^"]+)"', blob or "")
                    for i, tid in enumerate(ids):
                        if tid not in seen:
                            seen.add(tid)
                            candidates.append((times[i] if i < len(times) else "", tid))
                if not candidates:
                    sys.exit("No ERROR traces found for service '%s' in %s. "
                             "Run a chaos-injected flow first." % (SERVICE, TIME_RANGE))
                candidates.sort(reverse=True)
                trace_id = candidates[0][1]

            print("Analyzing trace:", trace_id)

            # ---- 2. full span tree -------------------------------------------
            res = await s.call_tool("signoz_get_trace_details", arguments={
                "traceId": trace_id, "includeSpans": True, "timeRange": TIME_RANGE,
            })
            data, blob = tool_json(res)
            if RAW:
                print("--- trace_details raw ---\n", blob[:6000], "\n---")

            # ---- 3. locate failing spans -------------------------------------
            spans = []
            for d in walk(data if data is not None else {}):
                name = first_key(d, "name", "spanName", "operation")
                if not name:
                    continue
                if not any(k.lower() in ("spanid", "span_id") for k in d):
                    continue
                spans.append(d)

            def span_error(sp):
                status = str(first_key(sp, "statusCode", "status_code_string",
                                       "statusCodeString", "status") or "")
                if "error" in status.lower() or status == "2":
                    return True
                he = first_key(sp, "hasError", "has_error")
                return bool(he)

            failing = [sp for sp in spans if span_error(sp)]
            # prefer the deepest named step (skip the root wrapper)
            failing_named = [sp for sp in failing
                             if "step-" in str(first_key(sp, "name", "spanName") or "")]
            target = (failing_named or failing or [None])[-1]

            evidence_lines = []
            step_name = "unknown"
            chaos = None
            status_message = ""
            if target:
                step_name = str(first_key(target, "name", "spanName"))
                status_message = str(first_key(target, "status_message",
                                               "statusMessage") or "")
                dur = first_key(target, "duration_nano", "durationNano")
                if "(injected)" in status_message:
                    chaos = "yes (marked in span status message)"
                attrs = {}
                for d in walk(target):
                    for k, v in d.items():
                        if k.startswith(("step.", "chaos.", "orchestration.")) and v:
                            attrs[k] = v
                        elif k.startswith("http.") and v not in ("", 0, None):
                            attrs[k] = v
                chaos = attrs.get("chaos.injected", chaos)
                evidence_lines.append("Failing span : %s" % step_name)
                if status_message:
                    evidence_lines.append("Span status  : %s" % status_message[:200])
                if dur:
                    try:
                        evidence_lines.append("Duration     : %.2f ms" % (float(dur) / 1e6))
                    except Exception:
                        pass
                for k in sorted(attrs):
                    evidence_lines.append("  %s = %s" % (k, attrs[k]))

            # pipeline context: every named step span in this trace, in order
            step_spans = sorted(
                {str(first_key(sp, "name", "spanName")) for sp in spans
                 if "step-" in str(first_key(sp, "name", "spanName") or "")})
            if step_spans:
                evidence_lines.append("Pipeline steps observed:")
                for nm in step_spans:
                    marker = "  [FAILED] " if nm == step_name else "  [ok]     "
                    evidence_lines.append(marker + nm)

            # fall back to whole-trace text for pattern matching
            searchable = "\n".join(evidence_lines) + "\n" + (blob or "")[:8000]
            cause, explanation, fixes = diagnose_text(searchable)

            # ---- 4. report ----------------------------------------------------
            print("\n" + "=" * 70)
            print("INTEGRATION DIAGNOSIS")
            print("=" * 70)
            print("Service      :", SERVICE)
            print("Trace ID     :", trace_id)
            print("Failing step :", step_name)
            if chaos:
                print("Note         : failure was INJECTED for demonstration "
                      "(chaos.injected=%s)" % chaos)
            print("\nRoot cause   :", cause)
            print("\nExplanation  :", explanation)
            print("\nFix steps:")
            for i, f in enumerate(fixes, 1):
                print("  %d. %s" % (i, f))
            print("\nEvidence:")
            for line in evidence_lines[:25]:
                print("  " + line)
            print("=" * 70)

            # ---- 5. optional Claude narrative ---------------------------------
            if ANTHROPIC_KEY:
                try:
                    import urllib.request
                    prompt = (
                        "You are an integration support engineer for Workday-style HRIS "
                        "pipelines. Using ONLY the evidence below, write a concise "
                        "diagnosis report with sections: Summary, Root Cause (in Workday "
                        "terms: ISU, ISSG, domain security, WQL), Evidence, Fix Steps, "
                        "Verification. Never invent telemetry.\n\nCandidate diagnosis: "
                        + cause + "\n\nEvidence:\n" + "\n".join(evidence_lines))
                    req = urllib.request.Request(
                        "https://api.anthropic.com/v1/messages",
                        data=json.dumps({
                            "model": os.environ.get("AGENT_MODEL", "claude-sonnet-4-6"),
                            "max_tokens": 800,
                            "messages": [{"role": "user", "content": prompt}],
                        }).encode(),
                        headers={"Content-Type": "application/json",
                                 "x-api-key": ANTHROPIC_KEY,
                                 "anthropic-version": "2023-06-01"})
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        out = json.load(resp)
                    print("\nAI NARRATIVE REPORT")
                    print("-" * 70)
                    for block in out.get("content", []):
                        if block.get("type") == "text":
                            print(block["text"])
                except Exception as e:
                    print("\n(Claude narrative skipped: %s)" % e)
            else:
                print("\n(Set ANTHROPIC_API_KEY in secrets.env for the AI narrative report)")


if __name__ == "__main__":
    asyncio.run(run())
