# Mock Workday Tenant (Local Practice Environment)

A local "fake Workday tenant" you run on your own machine. No tenant access needed.
It mimics the parts of Workday that integrations actually talk to.

## Recent additions

- **Integration Maps are now field-level.** Configure Integration Maps maps each
  **internal Workday field to an external field name** (the XML tag / CSV header) -
  one row per field, e.g. `First_Name -> First`. It no longer lists every person's
  value. The external name flows through to the generated output.
- **Workday-style report grid.** Running a custom report now shows clickable column
  headers (caret on each) with **Sort Ascending / Sort Descending / Remove Sort** and
  a **Filter** (select a value + Filter button, or Clear Filter), with a live item
  count and a sort arrow on the active column - matching the real Workday grid.

- **Edit Custom Report & Edit Calculated Field.** View Custom Report now has an
  **Edit** link per report (change columns, filter, subfilter, prompts, web service).
  New **View Calculated Field** task lists every calc field with an **Edit** link
  (change the function or its JSON parameters). You can now change definitions instead
  of only creating them.
- **Advanced report Subfilter + Prompts.** Create/Edit Custom Report now has a
  **Subfilter** (secondary filter, applied after the main filter) and **Prompts**
  (choose up to 3 fields to prompt on, mark each Required). A required prompt becomes a
  mandatory launch parameter: running the report asks for values first and will not run
  until they are entered.
- **Mandatory EIB launch parameters.** The Launch / Schedule Integration page now has a
  **Launch Parameters** group in the Integration Criteria grid (e.g. Effective Date,
  required). The integration will not launch until every required launch parameter has a
  value - exactly like a prompted Workday integration. The values are shown in the
  process detail.

- **Report calculated fields render like real Workday.** New report `PS_Advanced_11`
  (open via View Custom Report) showcases Concatenate Text, **Substring Text** (now
  supports After / Before / Between a Delimiter, Direction, and Remove Leading/Trailing
  Spaces - not just fixed position), Arithmetic (add and divide -> base pay per month),
  and Convert Currency (INR). Workers now carry `Total_Compensation` and
  `Total_Base_Pay_Annualized`.
- **Workday Studio: Assembly Debug.** Right-click any component on the canvas to
  **Toggle Assembly Breakpoint** (red dot), then press **Debug**. Execution suspends at
  each breakpoint and shows the Assembly Debug view - Message Root Part, Content-Type,
  Length, Variables (vars) and Properties (props) - with **Resume (F8)** to advance to
  the next breakpoint and **Terminate** to stop. The shipped demo project
  `INT_Demo_Inbound_Studio` has two breakpoints pre-set so you can Debug immediately.

## What it simulates

| Real Workday | This mock |
|---|---|
| Human_Resources SOAP web service (`Get_Workers`) | `POST /ccx/service/SUPER_TENANT/Human_Resources/v42.0` |
| `Response_Filter` Page/Count pagination | Fully working: 23 workers, 3 pages at Count=10 |
| `Response_Results` (`Total_Pages`, `Total_Results`) | Returned exactly like real Workday |
| RaaS custom report (XML / JSON) | `GET /ccx/service/customreport2/SUPER_TENANT/ISU_Demo/Worker_Report?format=xml` or `?format=json` |
| SOAP Fault on bad request | Returns a Workday-style validation fault |

## Files

- `mock_workday_server.py` - the fake tenant (Flask): Get_Workers SOAP, RaaS report, AND inbound Request_One_Time_Payment (Compensation service)
- `get_workers_request.xml` - sample SOAP request with Response_Filter
- `workers_to_psv.xsl` - XSLT transform (SOAP response -> pipe-delimited file), classic EIB/Studio outbound pattern
- `run_integration.py` - OUTBOUND: Studio-style client - reads Total_Pages from page 1, loops all pages, aggregates, applies XSLT, writes `workers_output.psv`
- `inbound_eib.py` - INBOUND EIB simulation mirroring the wizard: Get Data (Attach File at Launch = CSV) -> Transform (row -> Request_One_Time_Payment SOAP) -> Deliver (Compensation web service) -> Summary (per-line status, "Completed with Errors" handling)
- `one_time_payments.csv` - spreadsheet-template-style input (includes one intentionally bad Employee_ID so you see a Workday-style validation fault)

Inbound run:
```bash
python inbound_eib.py
curl http://localhost:8443/loaded_payments   # see what the "tenant" loaded
```

## Setup (one time)

```bash
pip install flask requests lxml
```

## Run

Terminal 1 (the tenant):
```bash
python mock_workday_server.py
# -> http://localhost:8443
```

Terminal 2 (the integration):
```bash
python run_integration.py
# -> Total_Results=23, Total_Pages=3 ... writes workers_output.psv
```

Quick manual tests:
```bash
# SOAP call
curl -s -X POST http://localhost:8443/ccx/service/SUPER_TENANT/Human_Resources/v42.0 \
     -H "Content-Type: text/xml" --data @get_workers_request.xml

# RaaS report
curl -s "http://localhost:8443/ccx/service/customreport2/SUPER_TENANT/ISU_Demo/Worker_Report?format=json"
```

## Calculated Fields + Custom Reports (RaaS)

- `calculated_fields.json` = your "Create Calculated Field" task. Each entry: Field Name + Business Object (Worker) + Function. Calc fields can reference other calc fields (chaining), like real Workday.

  Supported functions (one working example of each in the file):
  - Text: Text Constant (TC), Concatenate Text (CT), Substring Text (ST, 1-based start/length or split-after), Format Text (FT, with upper/lower case)
  - Lookup/Condition: Lookup Related Value (LRV), Evaluate Expression (EE, if/then/else), True/False Condition (TF, equals/not_equals/greater_than/less_than)
  - Arithmetic Calculation (AC): add/subtract/multiply/divide over fields and constants
  - Date: Date Difference (DD), Increment or Decrement Date (IDD, +/- years/months/days), Build Date (BD, from constants or parts of another date field)
  - Instance (operate on the multi-instance Payments list on each worker): Count Related Instance (CRI), Sum Related Instance (SRI), Extract Multi-Instance (EMI, filtered subset usable by other functions), Extract Single Instance (ESI, sort + first/last + return field)
  - Constants/conversions: Numeric Constant (NC), Date Constant (DC), Text Length (TL), Convert Text to Number (CTN), Format Number (FN, decimals/thousands/prefix), Format Date (FD, MM/dd/yyyy tokens), Convert Currency (CC, static rate table)
  - More lookups/aggregates: Lookup Range Band (LRB, min/max bands + default), Lookup Translated Value (LTV), Aggregate Related Instances (ARI, delimiter-joined values)

  That's 25 of the 29 functions in the standard Workday CF reference. Not simulated (need effective-dating or org hierarchies our flat model lacks): Lookup Value As of Date, Lookup Hierarchy/Rollup, Lookup Organization/Org Roles, Prompt for Value.
  Live demo report with the new functions: CF_Reference_Report (RaaS-enabled).

  Showcase report with every function: `WICT_CalcField_Showcase` (web-service enabled).
  ```bash
  curl "http://localhost:8443/ccx/service/customreport2/SUPER_TENANT/ISU_Demo/WICT_CalcField_Showcase?format=json"
  ```

- `report_definitions.json` = your "Create Custom Report" task. Each report: name, type (Simple/Advanced), data source, columns (base fields AND calculated fields), filter, and `enable_as_web_service`.
- Only reports with `enable_as_web_service: true` are served via the RaaS URL. A report with `false` returns HTTP 403 with a Workday-style message, just like a real report missing the Advanced tab checkbox.

Try it:
```bash
# Advanced report with 6 calculated fields, filtered to ACTIVE workers
curl "http://localhost:8443/ccx/service/customreport2/SUPER_TENANT/ISU_Demo/WICT_Active_Workers_Adv?format=json"

# Report NOT web-service enabled -> 403 error (realistic)
curl "http://localhost:8443/ccx/service/customreport2/SUPER_TENANT/ISU_Demo/WICT_Internal_Only"
```

Practice: add your own calculated field (e.g., a Lookup Range Band on P_Tenure_Years -> "0-2","3-5","6+") and a new Advanced report that uses it. Edit the two JSON files, restart the server, hit the new RaaS URL.

## Practice exercises (in order)

1. **Pagination**: Change `Count` to 5 in `run_integration.py` and confirm 5 pages are fetched.
2. **XSLT**: Add a FULL_NAME column (Last, First) to `workers_to_psv.xsl`. Filter out TERMINATED workers.
3. **RaaS**: Write a second client that pulls the RaaS JSON and converts it to CSV.
4. **Retry pattern**: Randomly return HTTP 500 from the server 20% of the time; add retry with backoff in the client (your Studio retry pattern).
5. **Inbound**: Add a `Submit_Payroll_Input`-style POST endpoint to the server that validates and "loads" data; write a client that sends it.
6. **Apache Camel**: Replace `run_integration.py` with a Camel route (timer -> SOAP -> XSLT -> file). Same engine Workday Studio is built on.

## Notes

- Data is fake/generated. Add more workers by editing the FIRST/LAST lists.
- Port 8443 is plain HTTP here. To practice SSL, wrap with `ssl_context='adhoc'` in Flask.
- This is for learning only. It is not affiliated with Workday.

## Workday-style UI

Run `python workday_ui.py` (instead of mock_workday_server.py - it includes all API routes) and open http://localhost:8443/home

- Search bar with task autocomplete: type "create calc", "create eib", "view" etc. Picking a task opens it in a NEW TAB, like the real tenant.
- Create Calculated Field: pick a function, parameters pre-fill, OK saves it to calculated_fields.json (immediately usable in reports).
- Create Custom Report: report type dropdown (Simple/Advanced/Matrix/...), column checkboxes including your calculated fields, optional filter, and "Enable As Web Service" - which is only clickable when type = Advanced, exactly like the real Advanced tab. Saving shows the live RaaS URL.
- Create EIB: Inbound = attach CSV at launch -> loads via Request One-Time Payment, then shows a process-monitor table with per-line COMPLETED/FAILED and faultstrings. Outbound = pick a web-service-enabled report.
- Integration Events: audit what inbound loads wrote. All Workers: browse the data.

## Core Connector: Worker (CCW)

Template-based integration simulation, searchable from the UI:
- Create Integration System: name + template "Core Connector: Worker" pre-loads services, attributes, and field sections.
- Configure Integration Services: enable/disable section services (ESB Service* is the mandatory initial service). Disabling a section removes it from output entirely.
- Configure Integration Attributes: Version (40.0/39.0/38.0), Output Filename (empty = sequence generator), Output Format (XML/CSV), Include Inactive Workers in Full File.
- Configure Integration Field Attributes: per-section "Include in Output" checkboxes, like the real field attribute grid.
- Launch Integration: Full File OR Changes Only. Changes Only diffs against a snapshot of the last run - the signature CCW change-detection behavior. A "Simulate a data change" button mutates one worker so you can watch Changes Only pick up exactly 1 record.
- Process Monitor shows every run with row counts and a link to the generated output file (cc_output/).

## Integration Maps

Per integration system: Configure Integration Maps translates internal Workday values to external values in the CCW output (e.g., Org "Finance" -> "FIN-EXT"), with a default for unmapped values. Pick the field, fill external values per internal value, OK, relaunch.

## ISU / ISSG Security

Full chain, searchable as tasks:
1. Create Integration System User (ISU) - service account, session timeout 0
2. Create Security Group (ISSG) - unconstrained, add the ISU as member
3. Maintain Domain Permissions - grant Get/Put per domain. CHANGES ARE PENDING ONLY.
4. Activate Pending Security Policy Changes - comment required, just like the real task. Until you run this, API calls fail with "not authorized... (Did you Activate Pending Security Policy Changes?)"
5. Security Overview - toggle "Require ISU authentication". When ON:
   - no/wrong credentials -> 401 SOAP fault "invalid username and password"
   - valid ISU without the domain -> 403 SOAP fault naming the missing domain
   - call with: curl -u ISU_NAME:PASSWORD <endpoint>

Domain -> endpoint mapping: Worker Data: Workers (Get) protects Get_Workers SOAP; Custom Report Web Services (Get) protects RaaS; One-Time Payments (Put) protects the inbound Compensation service.

Enforcement ships OFF so the practice scripts run without auth. Turn it on in Security Overview when you want to practice the security setup.

## Workday Studio (clone)

Palette uses authentic Studio component names: workday-in (Integration Service + Launch Parameters -> props), workday-out-soap (any service/operation; Get_Workers uses the PagedGet Response_Filter pattern; send_message=true posts the current message), workday-out-rest (RaaS), write, copy (save/restore message to a variable), store (snapshot the document on the integration event), csv-to-xml (delimiter-aware), async-mediation (execute-steps-when MVEL condition + dispatches a saved project on a parallel branch; results at /studio/async-results), splitter, aggregator, eval (MVEL), route, xslt, log, put-integration-message (PIM with Info/Warning/Error - Error stops the mediation), and route loop-back for retries.


Search "Workday Studio" in the UI, or open /task/workday-studio. An Eclipse-style IDE in the browser:
- Project Explorer (save/load assemblies), Palette with Studio-like categories (In Transports, Workday Components, Transform, Out Transports, Logging & Eventing)
- Drag a component from the Palette onto the canvas drop zone; click a node to edit its Properties; x to delete; Design/Source tabs (Source shows the assembly XML)
- Toolbar has the tenant connection: enter ISU credentials there if security enforcement is ON
- Run executes the assembly live against the mock tenant with a Studio-style console: per-step OK/FAILED, timings, faultstrings, and links to output files

Components: Launch/Listener, Call Workday Web Service: Get_Workers (paginates via Response_Filter automatically), RaaS Reader, XSLT (stylesheet editor pre-filled with workers_to_psv.xsl), Write File, Submit Workday Web Service (POST current doc, e.g. to Compensation), Console Log.

Example run (verified): Launch -> Get_Workers(Count=5) -> XSLT -> Write File -> Log
  => "Paginated 5 page(s), aggregated 23 workers" -> 1777-byte PSV -> cc_output/studio_run.psv

### MVEL in the Studio clone

The engine follows the MVEL 2.0 Language Guide (mvel.documentnode.com):
- Last value out: scripts return the last statement's value; `return` is optional. The Eval console line shows `[last value out: ...]`.
- Value coercion: `'123' == 123` is true (value-based equality, like MVEL).
- Literals: `true/false`, `null`/`nil`, and `empty` ( `'' == empty` is true; matches null, '', 0, or 0-length collections).
- Inline collections: lists `['Jim','Bob']`, MVEL maps `['Foo':'Bar']` (dot-accessible: `m.Foo`), arrays `{10,20,30}`.
- Flow control: `foreach (x : coll) { ... }` (iterates lists, strings char-by-char, or counts 1..n for an integer), `if / else if / else` blocks, `while` / `until` (with a loop guard).
- Operators: `&& || !`, ternary `? :`, `contains` (`list contains item`), regex `~=` (`'hello' ~= '[a-z]+'`), null-safe navigation `vars.?maybeMissing`.
- Projections: `(name in vars.people)` returns the list of each element's `name`.
- Java string methods: `.toUpperCase() .toLowerCase() .trim() .length() .startsWith() .endsWith() .indexOf()`.
- Helpers: `now() today() size() upper() lower() substring() sleep(ms)` and `isdef x`.
- `@{expr}` orb-tag interpolation in any component property (MVEL templating style).
- Context: `vars` (bare assignments like `count = 0` also land in vars), `props`, `message.text`. Get_Workers sets `vars.totalWorkers` / `vars.totalPages`.

### Retry / loop-back pattern (MVEL)

The engine supports the classic Studio retry pattern:
- Submit Workday Web Service has an "On error" property: stop (default) or continue. With continue, a failure sets vars.lastStatus='FAILED' and vars.lastError=<faultstring> and the mediation keeps going (your error handler).
- Route: Loop Back (retry) component (Error Handlers category): if its MVEL condition is true, the mediation jumps back N steps. A 100-iteration guard stops runaway loops.
- sleep(ms) MVEL helper (capped at 1000ms) for backoff: sleep(100 * vars.retryCount).
- The tenant has a practice endpoint /ccx/service/SUPER_TENANT/Unstable_Service/v1.0 that fails twice and succeeds on every 3rd call.

Working retry assembly (verified - succeeds on attempt 3 with increasing backoff):
  Launch
  Eval:        vars.retryCount = 0; vars.maxRetries = 3
  Submit WS:   path=/ccx/service/SUPER_TENANT/Unstable_Service/v1.0, on_error=continue
  Eval:        vars.retryCount = vars.retryCount + 1; sleep(100 * vars.retryCount)
  Route Back:  vars.lastStatus == 'FAILED' && vars.retryCount < vars.maxRetries  (steps_back=2)
  Route:       vars.lastStatus == 'OK'
  Log:         delivered after @{vars.retryCount} attempt(s)

## Module coverage: Core HCM, Benefits, Compensation, Payroll

Each worker now carries module data: Base_Salary/Currency/Comp_Plan (Compensation), Pay_Group (Payroll), and a Benefits enrollments list (Medical/Dental/401k with coverage levels and employee costs).

**Web services per module** (all on the mock tenant):
- Core HCM: Get_Workers (Human_Resources, paginated)
- Benefits: Get_Benefit_Enrollments (Benefits_Administration)
- Compensation: Get_Compensation, Request_Compensation_Change (updates Base_Salary), Request_One-Time_Payment
- Payroll: Import_Payroll_Input (bulk, ONE call per file, returns Loaded/Failed counts), Submit_Payroll_Input (single, synchronous - bad row fails the call), Get_Payroll_Results (computes gross / additional earnings from loaded inputs / benefit deductions / net per pay group). Put_Payroll_Input returns a deprecation fault telling you to use Import or Submit - exactly the distinction on the resume.

**Create EIB** now has a Deliver operation dropdown: One-Time Payment, Submit Payroll Input, Import Payroll Input (bulk), Request Compensation Change. Sample file: payroll_inputs.csv (Employee_ID, Pay_Component, Amount; one bad row).

**Studio components**: Get_Benefit_Enrollments and Get_Payroll_Results, plus two production-pattern XSLTs:
- benefits_carrier_file.xsl -> 834-style carrier CSV (one row per enrollment)
- payroll_interface.xsl -> ADP-style PI extract (the Workday-to-ADP scenario)

**Reports**: WICT_Compensation_Report and WICT_Benefits_Enrollments (both RaaS-enabled).

**Security**: new domains "Worker Data: Benefits Elections" (Get) and "Payroll Inputs and Results" (Put) gate the new endpoints when enforcement is on.

## W24/W31 training-doc patterns (4 reference docs)

1. Cloud Connect: Benefits template (Create Integration System): carrier connector emitting one Enrollment_Record per benefit enrollment (Subscriber Data + Enrollment Data sections), with full-file vs changes-only and integration maps.
2. Document Transformation template: a DT system has no data services - configure a Source Integration System + attached XSLT (default dt_generic_csv.xsl flattens any connector XML to CSV) + output filename. Launching it runs the source connector full-file, then applies the XSLT - both events appear in the Process Monitor, the standard CCW/CCB -> DT chain.
3. Outbound EIB enhancements: Get Data (web-service-enabled report) -> optional Transform (paste XSLT) -> Deliver (filename in cc_output) -> Schedule (Run Now / Daily / Weekly / Monthly, recorded by a simulated scheduler).
4. Advanced Studio: Splitter (by element local name) + Aggregator components. Steps between them run once per split part (xslt, post_ws, eval supported), with root xmlns declarations carried into each part; the Aggregator wraps results. Verified: split 23 workers -> per-worker XSLT -> 23 individual Request_One_Time_Payment calls -> aggregated responses.
