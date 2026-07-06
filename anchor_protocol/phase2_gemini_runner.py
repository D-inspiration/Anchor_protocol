"""
Phase 2 runner: have Gemini (via Anchor's mediated propose_fix) actually perform
each manual-drift scenario, then check whether Anchor's detectors notice.

Usage:
    export GEMINI_API_KEY="your-key"
    python3 phase2_gemini_runner.py /path/to/project target_file.py

Designed for the 'gemini-3.1-flash-lite' free tier (15 RPM / 500 RPD as of
this writing -- verify your current quota at
https://aistudio.google.com/apikey before a long run). Sleeps between calls
to stay under RPM; every proposed edit is shown to you before it's executed,
so nothing gets written to disk without a look first.

Results are appended to phase2_results.csv in the same schema as
PHASE1_TEST_MATRIX.md so both phases feed the same dataset.
"""

import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anchor_protocol.sidecar import AnchorSidecar
from anchor_protocol.integrations.factory import get_agent

SCENARIOS = [
    {"id": "P2-1", "change": "Rename every local variable to a different but still readable name. Do not change behavior.",
     "category": "manual_drift", "severity": "low"},
    {"id": "P2-2", "change": "Inline the charge_stripe function directly into process_payment so charge_stripe no longer exists as a separate function.",
     "category": "manual_drift", "severity": "medium"},
    {"id": "P2-3", "change": "Split process_payment into two smaller functions that together do exactly the same thing.",
     "category": "manual_drift", "severity": "medium"},
    {"id": "P2-4", "change": "Delete all comments and docstrings in the file. Do not change any logic.",
     "category": "manual_drift", "severity": "low"},
    {"id": "P2-5", "change": "Remove the input validation (the 'if not user_id: raise ValueError' check) from get_user.",
     "category": "manual_drift", "severity": "high"},
    {"id": "P2-6", "change": "Change charge_stripe's return value from a dict to a plain string describing the result.",
     "category": "manual_drift", "severity": "high"},
    {"id": "P2-7", "change": "Reorder the statements inside process_payment while keeping the exact same external behavior and function signature.",
     "category": "manual_drift", "severity": "low"},
]

RESULTS_CSV = None  # set inside run() once project_path is known
CSV_FIELDS = ["id", "change", "category", "severity", "ticket", "executed",
              "structural_drift", "io_contract_results", "invariant_violations",
              "reachability_orphans_delta", "notes"]


def run(project_path: str, target_file: str, model: str = "gemini-3.1-flash-lite",
        sleep_seconds: float = 5.0, auto_confirm: bool = False,
        contract_symbol: str = "charge_stripe", contract_inputs: dict = None,
        contract_output: str = "dict"):
    global RESULTS_CSV
    RESULTS_CSV = os.path.join(os.path.abspath(project_path), "phase2_results.csv")

    anchor = AnchorSidecar(project_path)
    anchor.init_session()
    anchor.set_manual_scope(active_files=[target_file])
    anchor.read_file(target_file)  # populate the symbol registry before declaring a contract on it

    # Without this, I/O contract drift can never be detected -- there's nothing
    # to compare against. This was the actual reason "return string instead of
    # dict" went unnoticed last run: no contract existed for that symbol at all.
    try:
        anchor.io_contracts.declare_contract(
            symbol_name=contract_symbol, inputs=contract_inputs or {"amount": "int"}, output_type=contract_output
        )
        print(f"Declared I/O contract: {contract_symbol}({contract_inputs or {'amount': 'int'}}) -> {contract_output}")
    except ValueError as e:
        print(f"Could not declare contract on '{contract_symbol}': {e}")

    agent = get_agent(anchor, provider="gemini", model=model, thinking_level="low")
    print(f"Using {agent.provider_name} / {agent.actor_name}")

    before_orphans = len(anchor.reachability.analyze()["orphaned"])
    results = []

    for scenario in SCENARIOS:
        print(f"\n=== {scenario['id']}: {scenario['change']} ===")
        row = {"id": scenario["id"], "change": scenario["change"], "category": scenario["category"],
               "severity": scenario["severity"], "ticket": "", "executed": False,
               "structural_drift": "", "io_contract_results": "", "invariant_violations": "",
               "reachability_orphans_delta": "", "notes": ""}

        try:
            ticket = agent.propose_fix(target_file, scenario["change"])
            row["ticket"] = ticket
        except Exception as e:
            row["notes"] = f"propose_fix failed: {e}"
            results.append(row)
            _append_csv(row)
            time.sleep(sleep_seconds)
            continue

        proposal = anchor.db.get_proposal(ticket)[0]
        print("--- proposed new content (first 800 chars) ---")
        print(proposal.new_content[:800])
        print("--- end preview ---")

        proceed = "y" if auto_confirm else input("Execute this change? [y/N] ").strip().lower()
        if proceed != "y":
            row["notes"] = "skipped by user"
            results.append(row)
            _append_csv(row)
            time.sleep(sleep_seconds)
            continue

        try:
            exec_result = anchor.execute_ticket(ticket)
            row["executed"] = True
        except Exception as e:
            row["notes"] = f"execute_ticket rejected it: {e}"
            results.append(row)
            _append_csv(row)
            time.sleep(sleep_seconds)
            continue

        # Pull the real evidence straight from execute_ticket's own result --
        # no need to recompute drift separately, and no risk of the "compare
        # against a registry that was already updated" bug that produces false
        # negatives if you call detect_drift() again after the fact.
        row["structural_drift"] = json.dumps(exec_result.get("structural_drift", []))
        row["io_contract_results"] = json.dumps(exec_result.get("io_contract_results", []))
        row["invariant_violations"] = json.dumps(exec_result.get("invariant_violations", []))

        after_orphans = len(anchor.reachability.analyze()["orphaned"])
        row["reachability_orphans_delta"] = after_orphans - before_orphans
        before_orphans = after_orphans

        results.append(row)
        _append_csv(row)
        print(f"Detected: structural_drift={row['structural_drift']}, "
              f"io_contract_results={row['io_contract_results']}, "
              f"orphan_delta={row['reachability_orphans_delta']}")

        time.sleep(sleep_seconds)  # stay under free-tier RPM

    print(f"\nDone. {len(results)} scenarios logged to {RESULTS_CSV}")
    print("Cross-reference these against what you EXPECTED for each scenario -- "
          "that comparison is Phase 3's dataset, not this raw log.")


def _append_csv(row: dict):
    file_exists = os.path.exists(RESULTS_CSV)
    with open(RESULTS_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 phase2_gemini_runner.py <project_path> <target_file>")
        sys.exit(1)
    run(sys.argv[1], sys.argv[2])
