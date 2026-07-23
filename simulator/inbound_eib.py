"""
inbound_eib.py - Simulates an Inbound EIB run, mirroring the Workday wizard:

  General Settings : Name = PS_EIB_Inbound_Sampl, Direction = Inbound
  Get Data         : Retrieval Method = Attach File at Launch (reads the CSV)
  Transform        : Spreadsheet template row -> Request_One_Time_Payment SOAP
  Deliver          : Workday Web Service Operation = Request One-Time Payment
                     (Compensation web service on the mock tenant)
  Summary          : Per-row results, like the EIB process monitor

Run (mock server must be running):
  python inbound_eib.py
Then check what loaded:
  curl http://127.0.0.1:8443/loaded_payments
"""

import csv
import requests

ENDPOINT = "http://127.0.0.1:8443/ccx/service/SUPER_TENANT/Compensation/v42.0"
INPUT_FILE = "one_time_payments.csv"

# --- Transform step: spreadsheet row -> Workday SOAP request ----------------
SOAP_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
              xmlns:wd="urn:com.workday/bsvc">
  <env:Body>
    <wd:Request_One_Time_Payment_Request wd:version="v42.0">
      <wd:One_Time_Payment_Data>
        <wd:Employee_Reference>
          <wd:ID wd:type="Employee_ID">{employee_id}</wd:ID>
        </wd:Employee_Reference>
        <wd:One_Time_Payment_Plan>{plan}</wd:One_Time_Payment_Plan>
        <wd:Amount>{amount}</wd:Amount>
        <wd:Currency>{currency}</wd:Currency>
        <wd:Comment>{comment}</wd:Comment>
      </wd:One_Time_Payment_Data>
    </wd:Request_One_Time_Payment_Request>
  </env:Body>
</env:Envelope>"""


def main():
    print("=== Inbound EIB: PS_EIB_Inbound_Sampl ===")
    print("Get Data  : Attach File at Launch ->", INPUT_FILE)
    print("Deliver   : Request One-Time Payment (Web Service)\n")

    results = []

    # --- Get Data step: read the attached spreadsheet ---
    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # --- Per-row: Transform + Deliver (one web service call per line) ---
    for i, row in enumerate(rows, start=1):
        soap = SOAP_TEMPLATE.format(
            employee_id=row["Employee_ID"],
            plan=row["One_Time_Payment_Plan"],
            amount=row["Amount"],
            currency=row["Currency"],
            comment=row["Comment"],
        )
        try:
            r = requests.post(ENDPOINT, data=soap,
                              headers={"Content-Type": "text/xml"}, timeout=10)
            if r.status_code == 200:
                results.append((i, row["Employee_ID"], "COMPLETED", ""))
            else:
                # Pull faultstring like the EIB error report does
                fault = "SOAP Fault"
                m = r.text.split("<faultstring>")
                if len(m) > 1:
                    fault = m[1].split("</faultstring>")[0]
                results.append((i, row["Employee_ID"], "FAILED", fault))
        except requests.RequestException as e:
            results.append((i, row["Employee_ID"], "FAILED", str(e)))

    # --- Summary step: process monitor style output ---
    completed = sum(1 for r in results if r[2] == "COMPLETED")
    failed = len(results) - completed
    print(f"{'Line':<6}{'Employee_ID':<14}{'Status':<12}Error")
    print("-" * 70)
    for line, emp, status, err in results:
        print(f"{line:<6}{emp:<14}{status:<12}{err}")
    print("-" * 70)
    overall = "Completed" if failed == 0 else "Completed with Errors"
    print(f"Overall Status: {overall}  ({completed} loaded, {failed} failed)")


if __name__ == "__main__":
    main()
