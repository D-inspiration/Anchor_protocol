"""
Scores phase2_results.csv (what Anchor actually detected) against a
hand-labeled expected_outcomes.csv (what should have happened), producing
the kind of table from the benchmark suggestion:

    Edit                Structural   IO       Expected   Actual   Correct?
    Rename variable      PASS         PASS     PASS       PASS     YES
    Return string/dict   PASS         FAIL     FAIL       FAIL     YES

This is deliberately a small, honest scorer -- it derives one PASS/FAIL/
MISSING/UNKNOWN summary per axis from the raw JSON Anchor already produced,
it does not re-run any detection itself.

Usage:
    python3 score_benchmark.py phase2_results.csv expected_outcomes.csv
"""
import csv
import json
import sys

STATUS_PRIORITY = ["MISSING", "FAIL", "UNKNOWN", "PASS"]  # worst wins when combining multiple contracts


def summarize_structural(structural_drift_json: str) -> str:
    try:
        drifts = json.loads(structural_drift_json) if structural_drift_json else []
    except (json.JSONDecodeError, TypeError):
        return "UNKNOWN"
    if any(d.get("type") == "missing_symbol" for d in drifts):
        return "FAIL"
    if drifts:  # only silent_drift entries
        return "FAIL"
    return "PASS"


def summarize_io(io_contract_results_json: str) -> str:
    try:
        results = json.loads(io_contract_results_json) if io_contract_results_json else []
    except (json.JSONDecodeError, TypeError):
        return "UNKNOWN"
    if not results:
        return "NOT_CHECKED"  # no contract existed for anything touched -- distinct from PASS
    statuses = [r["status"] for r in results]
    for level in STATUS_PRIORITY:
        if level in statuses:
            return level
    return "PASS"


def _read_csv_skipping_comments(path: str):
    with open(path) as f:
        lines = [line for line in f if not line.lstrip().startswith("#")]
    return list(csv.DictReader(lines))


def score(results_csv: str, expected_csv: str):
    expected = {row["id"]: row for row in _read_csv_skipping_comments(expected_csv)}
    actual = {row["id"]: row for row in _read_csv_skipping_comments(results_csv)}

    print(f"{'ID':<8}{'Structural':<12}{'IO':<14}{'Expected':<10}{'Correct?':<10}Notes")
    print("-" * 80)
    correct_count = 0
    total = 0

    for scenario_id, exp in expected.items():
        if scenario_id not in actual:
            print(f"{scenario_id:<8}{'--':<12}{'--':<14}{exp['expected_overall']:<10}{'NO RUN':<10}not found in results")
            continue
        row = actual[scenario_id]
        actual_structural = summarize_structural(row.get("structural_drift", ""))
        actual_io = summarize_io(row.get("io_contract_results", ""))

        # Overall: worst of structural/io, matching the priority order above
        overall_candidates = [actual_structural, actual_io]
        actual_overall = next((s for s in STATUS_PRIORITY if s in overall_candidates), "PASS")

        expected_overall = exp["expected_overall"].strip().upper()
        is_correct = (actual_overall == expected_overall)
        correct_count += is_correct
        total += 1

        print(f"{scenario_id:<8}{actual_structural:<12}{actual_io:<14}{expected_overall:<10}"
              f"{'YES' if is_correct else 'NO':<10}{exp['change_description'][:40]}")

    print("-" * 80)
    if total:
        print(f"Accuracy: {correct_count}/{total} ({100 * correct_count / total:.0f}%)")
    else:
        print("No scenarios scored -- check that IDs match between the two files.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 score_benchmark.py <phase2_results.csv> <expected_outcomes.csv>")
        sys.exit(1)
    score(sys.argv[1], sys.argv[2])
