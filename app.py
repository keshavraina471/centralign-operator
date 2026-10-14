import json, sqlite3, time
from pathlib import Path
from datetime import datetime
import streamlit as st

ROOT = Path(__file__).parent
INVOICE_DIR = ROOT / "sample_data" / "invoices"
DB_PATH = ROOT / "finance.db"

st.set_page_config(page_title="CentrAlign Operator", page_icon="🤖", layout="wide")

def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT UNIQUE,
            vendor TEXT NOT NULL,
            amount REAL NOT NULL,
            due_date TEXT,
            source_file TEXT,
            flagged INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """)

def load_invoices():
    rows = []
    for p in sorted(INVOICE_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            d["_source_file"] = p.name
            rows.append(d)
        except Exception:
            continue
    return rows

def execute_tool(name, args):
    """Small allowlisted tool registry. All actions are local to this demo."""
    if name == "search_invoices":
        vendor = args.get("vendor", "").strip().lower()
        docs = [d for d in load_invoices() if vendor in d.get("vendor", "").lower()]
        docs.sort(key=lambda d: d.get("invoice_date", ""), reverse=True)
        return {"ok": True, "count": len(docs), "invoices": docs}
    if name == "validate_invoice":
        d = args["invoice"]
        required = ["invoice_number", "vendor", "amount", "due_date", "invoice_date"]
        missing = [k for k in required if d.get(k) in (None, "")]
        try:
            amount = float(d.get("amount", -1))
        except (ValueError, TypeError):
            amount = -1
        if missing or amount < 0:
            return {"ok": False, "error": "Invalid invoice fields", "missing": missing}
        return {"ok": True, "validated": True, "amount": amount}
    if name == "record_invoice":
        d = args["invoice"]
        threshold = float(args.get("threshold", 50000))
        with sqlite3.connect(DB_PATH) as con:
            try:
                cur = con.execute("""INSERT INTO invoices
                (invoice_number, vendor, amount, due_date, source_file, flagged, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (d["invoice_number"], d["vendor"], float(d["amount"]), d["due_date"],
                 d["_source_file"], int(float(d["amount"]) > threshold), datetime.now().isoformat(timespec="seconds")))
                row_id = cur.lastrowid
                return {"ok": True, "row_id": row_id, "invoice_number": d["invoice_number"]}
            except sqlite3.IntegrityError:
                return {"ok": False, "error": "duplicate_invoice", "invoice_number": d["invoice_number"]}
    if name == "verify_invoice":
        number = args["invoice_number"]
        with sqlite3.connect(DB_PATH) as con:
            con.row_factory = sqlite3.Row
            row = con.execute("SELECT * FROM invoices WHERE invoice_number=?", (number,)).fetchone()
            return {"ok": bool(row), "record": dict(row) if row else None}
    if name == "list_records":
        with sqlite3.connect(DB_PATH) as con:
            con.row_factory = sqlite3.Row
            return {"ok": True, "records": [dict(r) for r in con.execute("SELECT * FROM invoices ORDER BY id DESC")]}
    return {"ok": False, "error": f"Tool not allowlisted: {name}"}

def run_agent(vendor, threshold, approve):
    events = []
    def log(stage, message, detail=None):
        events.append({"time": datetime.now().strftime("%H:%M:%S"), "stage": stage, "message": message, "detail": detail})
    log("UNDERSTAND", f"Goal: find latest invoice for {vendor}, record it, flag amounts over ₹{threshold:,.0f}, and verify the saved record.")
    plan = [
        "Search sample invoice files for the requested vendor",
        "Select the most recent matching invoice",
        "Validate required fields and amount",
        "Check approval policy",
        "Write to finance database",
        "Read back the record and verify it"
    ]
    log("PLAN", "Generated execution plan", plan)
    result = execute_tool("search_invoices", {"vendor": vendor})
    log("EXECUTE", "Called search_invoices", {"count": result.get("count", 0)})
    if not result["invoices"]:
        log("STOP", "No matching invoice found. No record was written.")
        return events, {"status": "needs_input", "message": "No matching invoice found."}
    invoice = result["invoices"][0]
    log("OBSERVE", "Latest matching invoice selected", {k:v for k,v in invoice.items() if not k.startswith("_")})
    validation = execute_tool("validate_invoice", {"invoice": invoice})
    log("VERIFY INPUT", "Invoice validation result", validation)
    if not validation["ok"]:
        return events, {"status": "failed", "message": "Invoice failed validation."}
    if float(invoice["amount"]) > threshold and not approve:
        log("HUMAN APPROVAL", "Invoice exceeds threshold; waiting for approval before writing.")
        return events, {"status": "approval_required", "message": f"₹{float(invoice['amount']):,.2f} exceeds the threshold. Approve the database write to continue.", "invoice": invoice}
    saved = execute_tool("record_invoice", {"invoice": invoice, "threshold": threshold})
    log("EXECUTE", "Called record_invoice", saved)
    if not saved["ok"] and saved.get("error") == "duplicate_invoice":
        verified = execute_tool("verify_invoice", {"invoice_number": invoice["invoice_number"]})
        log("RECOVERY", "Duplicate detected; did not create a second record and checked existing record.", verified)
    elif not saved["ok"]:
        return events, {"status": "failed", "message": saved.get("error", "Database write failed.")}
    else:
        verified = execute_tool("verify_invoice", {"invoice_number": invoice["invoice_number"]})
        log("VERIFY", "Read-after-write verification", verified)
    rec = verified.get("record")
    expected = {"vendor": invoice["vendor"], "amount": float(invoice["amount"]), "due_date": invoice["due_date"]}
    matches = bool(rec) and rec["vendor"] == expected["vendor"] and abs(float(rec["amount"]) - expected["amount"]) < 0.001 and rec["due_date"] == expected["due_date"]
    log("COMPLETE" if matches else "VERIFY FAILED", "Saved record matches expected fields." if matches else "Saved record missing or fields do not match.", {"expected": expected, "verified_record": rec})
    return events, {"status": "completed" if matches else "failed", "message": "Verified successfully." if matches else "Could not verify the saved record.", "invoice": invoice, "record": rec, "verified": matches}

init_db()
st.title("🤖 CentrAlign Operator")
st.caption("Autonomous company-task prototype · local sandbox · every action is logged")
st.info("Demo workflow: find the latest invoice → validate → apply approval policy → write to SQLite → read back and verify.")

with st.sidebar:
    st.header("Task")
    vendor = st.text_input("Vendor name", "Acme Technologies")
    threshold = st.number_input("Flag / approval threshold (₹)", min_value=0, value=50000, step=5000)
    st.caption("Amounts above the threshold require explicit approval before the write.")
    approve = st.checkbox("Approve write if threshold is exceeded", value=False)
    run = st.button("▶ Run autonomous task", type="primary", use_container_width=True)
    st.divider()
    st.caption("This prototype uses local sample data and an allowlisted tool registry. It does not access real company systems.")

left, right = st.columns([1.15, 0.85])
with left:
    st.subheader("Execution trace")
    if run:
        events, result = run_agent(vendor, threshold, approve)
        st.session_state["events"] = events
        st.session_state["result"] = result
    for e in st.session_state.get("events", []):
        with st.expander(f'{e["time"]} · {e["stage"]} · {e["message"]}', expanded=e["stage"] in ("COMPLETE", "HUMAN APPROVAL", "STOP", "VERIFY FAILED")):
            if e.get("detail") is not None:
                st.json(e["detail"])
with right:
    st.subheader("Outcome")
    result = st.session_state.get("result")
    if result:
        status = result["status"]
        if status == "completed":
            st.success(result["message"])
        elif status == "approval_required":
            st.warning(result["message"])
            st.write("Selected invoice:")
            st.json({k:v for k,v in result["invoice"].items() if not k.startswith("_")})
            st.caption("Check “Approve write…” in the sidebar and run the task again to approve.")
        elif status == "needs_input":
            st.info(result["message"])
        else:
            st.error(result["message"])
        if result.get("record"):
            st.write("Verified finance record")
            st.json(result["record"])
    else:
        st.write("Run a task to see the agent plan, tool calls, observations, and verification evidence.")

st.divider()
st.subheader("Finance system · SQLite records")
records = execute_tool("list_records", {})
if records["records"]:
    st.dataframe(records["records"], use_container_width=True, hide_index=True)
else:
    st.caption("No invoices recorded yet.")

with st.expander("Available sample invoices"):
    st.json([{k:v for k,v in d.items() if not k.startswith("_")} for d in load_invoices()])
