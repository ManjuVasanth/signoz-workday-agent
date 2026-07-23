"""
run_integration.py - "Studio-style" outbound integration against the mock tenant.

Pattern (same as Workday Studio pagination):
  1. Call Get_Workers page 1 with Response_Filter Count=10
  2. Read Total_Pages from Response_Results
  3. Loop pages 2..Total_Pages, injecting Page into the request
  4. Aggregate all workers, apply XSLT, write pipe-delimited output file

Run (with the mock server already running):
  pip install requests lxml
  python run_integration.py
"""

import requests
from lxml import etree

ENDPOINT = "http://127.0.0.1:8443/ccx/service/SUPER_TENANT/Human_Resources/v42.0"
COUNT = 10
NS = {"env": "http://schemas.xmlsoap.org/soap/envelope/",
      "wd": "urn:com.workday/bsvc"}

REQUEST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
              xmlns:wd="urn:com.workday/bsvc">
  <env:Body>
    <wd:Get_Workers_Request wd:version="v42.0">
      <wd:Response_Filter>
        <wd:Page>{page}</wd:Page>
        <wd:Count>{count}</wd:Count>
      </wd:Response_Filter>
    </wd:Get_Workers_Request>
  </env:Body>
</env:Envelope>"""


def call_page(page):
    body = REQUEST_TEMPLATE.format(page=page, count=COUNT)
    r = requests.post(ENDPOINT, data=body,
                      headers={"Content-Type": "text/xml"}, timeout=10)
    r.raise_for_status()
    return etree.fromstring(r.content)


def main():
    # --- Page 1: discover Total_Pages (Studio pattern) ---
    doc = call_page(1)
    total_pages = int(doc.xpath("string(//wd:Total_Pages)", namespaces=NS))
    total_results = int(doc.xpath("string(//wd:Total_Results)", namespaces=NS))
    print(f"Total_Results={total_results}, Total_Pages={total_pages}")

    all_workers = doc.xpath("//wd:Worker", namespaces=NS)

    # --- Loop remaining pages, inject Page into request ---
    for page in range(2, total_pages + 1):
        page_doc = call_page(page)
        workers = page_doc.xpath("//wd:Worker", namespaces=NS)
        print(f"Page {page}: {len(workers)} workers")
        all_workers.extend(workers)

    # --- Aggregate into one Response_Data document ---
    agg = etree.Element("{urn:com.workday/bsvc}Response_Data", nsmap={"wd": NS["wd"]})
    for w in all_workers:
        agg.append(w)

    # --- Apply XSLT (your Studio transform step) ---
    xslt = etree.XSLT(etree.parse("workers_to_psv.xsl"))
    result = str(xslt(agg))

    out_file = "workers_output.psv"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(result)

    print(f"\nWrote {len(all_workers)} workers to {out_file}")
    print("--- preview ---")
    print("\n".join(result.splitlines()[:5]))


if __name__ == "__main__":
    main()
