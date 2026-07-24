"""Run from the agent folder: python patch_evidence.py"""
import re, sys
path = 'diagnose.py'
src = open(path).read()
if 'Pipeline steps observed' in src:
    print('Already patched.'); sys.exit(0)
start = src.find('            evidence_lines = []')
end = src.find('            # fall back to whole-trace text')
if start < 0 or end < 0 or end <= start:
    sys.exit('Markers not found; file differs from expected.')
new_block = '            evidence_lines = []\n            step_name = "unknown"\n            chaos = None\n            status_message = ""\n            if target:\n                step_name = str(first_key(target, "name", "spanName"))\n                status_message = str(first_key(target, "status_message",\n                                               "statusMessage") or "")\n                dur = first_key(target, "duration_nano", "durationNano")\n                if "(injected)" in status_message:\n                    chaos = "yes (marked in span status message)"\n                attrs = {}\n                for d in walk(target):\n                    for k, v in d.items():\n                        if k.startswith(("step.", "chaos.", "orchestration.")) and v:\n                            attrs[k] = v\n                        elif k.startswith("http.") and v not in ("", 0, None):\n                            attrs[k] = v\n                chaos = attrs.get("chaos.injected", chaos)\n                evidence_lines.append("Failing span : %s" % step_name)\n                if status_message:\n                    evidence_lines.append("Span status  : %s" % status_message[:200])\n                if dur:\n                    try:\n                        evidence_lines.append("Duration     : %.2f ms" % (float(dur) / 1e6))\n                    except Exception:\n                        pass\n                for k in sorted(attrs):\n                    evidence_lines.append("  %s = %s" % (k, attrs[k]))\n\n            # pipeline context: every named step span in this trace, in order\n            step_spans = sorted(\n                {str(first_key(sp, "name", "spanName")) for sp in spans\n                 if "step-" in str(first_key(sp, "name", "spanName") or "")})\n            if step_spans:\n                evidence_lines.append("Pipeline steps observed:")\n                for nm in step_spans:\n                    marker = "  [FAILED] " if nm == step_name else "  [ok]     "\n                    evidence_lines.append(marker + nm)\n\n'
open(path, 'w').write(src[:start] + new_block + src[end:])
src2 = open(path).read()
old = 'for line in evidence_lines[:15]:'
if old in src2:
    open(path,'w').write(src2.replace(old, 'for line in evidence_lines[:25]:'))
import ast; ast.parse(open(path).read())
print('PATCHED OK - evidence section upgraded')
