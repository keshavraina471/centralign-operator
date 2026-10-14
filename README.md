# CentrAlign Operator — Autonomous AI Employee Prototype

A narrow, runnable proof of concept for the CentrAlign AI Founding Engineer hiring task. It completes a concrete enterprise workflow instead of only generating an answer.

## What it demonstrates

- Natural-language-style task parameters (vendor, threshold)
- Explicit goal and execution plan
- Tool registry with allowlisted operations
- Local file search over invoice JSON documents
- Selecting the latest matching invoice
- Input validation before side effects
- Human approval gate for invoices over a configurable threshold
- Persistent SQLite write with a unique invoice-number constraint
- Duplicate detection and safe recovery by checking the existing record
- Read-after-write verification against expected fields
- Timestamped audit trace and evidence shown in the UI

## Architecture

`Streamlit UI → Task runner → Allowlisted tool registry → JSON invoice files / SQLite → verification → audit trace`

The current planner is deterministic rather than LLM-generated. This is intentional for a reliable first prototype: the workflow is reproducible and the execution/verification mechanisms are inspectable. An LLM planner can be added behind a structured-plan interface without allowing the model to execute arbitrary code.

## Run locally

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

The app creates `finance.db` locally on first run. Sample invoice JSON files are in `sample_data/invoices/`.

## Demo script (60–90 seconds)

1. Run the task for `Acme Technologies` with a ₹50,000 threshold and approval unchecked.
2. Show that the agent selects the latest invoice and pauses before a high-value write.
3. Enable approval and run again.
4. Show the SQLite record and the read-after-write verification in the execution trace.
5. Run again to demonstrate duplicate detection: it does not create a duplicate and checks the existing record.
6. Change vendor to `Northstar Supplies` to demonstrate generalization across data.

## Important design decisions

- **Safe side effects:** all tools are explicitly allowlisted; the demo has no arbitrary shell/browser access.
- **Approval boundary:** high-value records require approval before writing.
- **Idempotency:** invoice number is unique in SQLite; repeat runs do not create duplicate records.
- **Verification:** success is not declared just because a write call returned. The system reads the record back and compares critical fields.
- **Evidence:** each stage records a timestamp and structured details.

## Known limitations

- Uses local sample invoices, not live email, cloud drives, or an ERP.
- The planner and extraction are deterministic; this is not yet an LLM-powered general-purpose operator.
- It supports one workflow and a small tool set.
- Retries are not yet implemented for transient I/O failures.
- Authentication, multi-user permissions, background queues, and deployment hardening are out of scope for this proof of concept.

## Next steps

1. Add a structured LLM planner with a strict JSON schema and plan validation.
2. Add retry/backoff for transient tool failures and bounded step budgets.
3. Add an approval inbox and durable task state.
4. Add connectors behind the same tool interface.
5. Add evaluation scenarios for missing fields, malformed files, duplicates, threshold boundaries, and tool failures.

## Assumptions

- Invoice data is provided as local JSON documents in a sandbox.
- “Latest” means the greatest ISO-formatted `invoice_date`.
- Flagging and approval are triggered when amount is strictly greater than the threshold.
- The app is a demonstration environment; no real credentials or company data are used.
