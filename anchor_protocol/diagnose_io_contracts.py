"""
Diagnoses the io_contracts_checked=0 mystery in the order proposed:
  1. Is the contract being saved?
  2. Is it loaded before analysis?
  3. Is it matched to the edited symbol's file?
  4. Is it executed (does drift detection actually run)?

Usage: python3 diagnose_io_contracts.py /path/to/project payments.py charge_stripe
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anchor_protocol.sidecar import AnchorSidecar
from anchor_protocol.data import db as db_module
from anchor_protocol.models import registry as registry_module


def diagnose(project_path, target_file, symbol_name):
    print("=== 0. Which code is actually installed/running? ===")
    print(f"  db.py loaded from:       {inspect.getfile(db_module)}")
    print(f"  registry.py loaded from: {inspect.getfile(registry_module)}")
    src = inspect.getsource(registry_module)
    if "def _get_or_create_file(self, path: str) -> int:" in src and "content" not in src.split(
        "_get_or_create_file")[1].split("\n")[0]:
        print("  !! STALE: this registry.py still has the OLD _get_or_create_file(self, path) "
              "signature that re-reads from disk and doesn't accept `content`.")
        print("  !! Fix: re-run `pip install -e . --force-reinstall` from the package you just downloaded, "
              "then delete any __pycache__ folders under the installed anchor_protocol location above.")
    else:
        print("  OK: registry.py has the current _get_or_create_file(self, path, content) signature.")

    anchor = AnchorSidecar(project_path)
    anchor.init_session()

    print("\n=== 1. Is the contract saved? (raw DB query) ===")
    rows = anchor.db.query("SELECT * FROM io_contracts")
    print(f"  {len(rows)} row(s) in io_contracts table: {rows}")

    print("\n=== 2. Is it loaded before analysis? (list_all_contracts) ===")
    contracts = anchor.io_contracts.list_all_contracts()
    print(f"  list_all_contracts() returned {len(contracts)} contract(s):")
    for c in contracts:
        print(f"    symbol={c['symbol']!r}  file={c['file']!r}  output_type={c['output_type']!r}")

    print(f"\n=== 3. Does any contract's file match the target file? ===")
    print(f"  target_file (as used by propose_edit) = {target_file!r}")
    matches = [c for c in contracts if c['file'] == target_file]
    print(f"  {len(matches)} contract(s) match exactly on file path.")
    if contracts and not matches:
        print(f"  !! MISMATCH: stored contract file path {contracts[0]['file']!r} != {target_file!r}")
        print(f"  !! This is the bug: paths are being stored inconsistently (absolute vs relative).")

    print(f"\n=== 4. Does drift detection actually run for '{symbol_name}'? ===")
    with open(os.path.join(project_path, target_file)) as f:
        current_source = f.read()
    input_drift = anchor.io_contracts.detect_input_drift(symbol_name, current_source)
    output_drift = anchor.io_contracts.detect_output_drift(symbol_name, current_source)
    print(f"  detect_input_drift:  {input_drift}")
    print(f"  detect_output_drift: {output_drift}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 diagnose_io_contracts.py <project_path> <target_file> <symbol_name>")
        sys.exit(1)
    diagnose(sys.argv[1], sys.argv[2], sys.argv[3])
