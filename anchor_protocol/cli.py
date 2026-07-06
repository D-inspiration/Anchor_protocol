"""CLI commands for Anchor Protocol v0.2."""

import os
import sys
import argparse
import glob
from .sidecar import AnchorSidecar, EditProposal, ROLE_CONTEXT, ROLE_ACTIVE, ROLE_FROZEN


def main():
    parser = argparse.ArgumentParser(description='Anchor Protocol - AI governance sidecar')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    init_parser = subparsers.add_parser('init', help='Initialize anchor session')
    init_parser.add_argument('path', help='Project path')
    init_parser.add_argument('--files', help='Comma-separated file patterns (use "." for all files)')
    init_parser.add_argument('--force', action='store_true', help='Force new session even if one exists')

    status_parser = subparsers.add_parser('status', help='Show session status')
    status_parser.add_argument('path', help='Project path')

    report_parser = subparsers.add_parser('report', help='Generate stability report')
    report_parser.add_argument('path', help='Project path')
    report_parser.add_argument('--format', choices=['text', 'json', 'csv'], default='text')

    history_parser = subparsers.add_parser('history', help='View operation history')
    history_parser.add_argument('path', help='Project path')
    history_parser.add_argument('--limit', type=int, default=50)

    freeze_parser = subparsers.add_parser('freeze', help='Freeze files (read-only)')
    freeze_parser.add_argument('path', help='Project path')
    freeze_parser.add_argument('--files', required=True, help='Comma-separated files')

    reset_parser = subparsers.add_parser('reset', help='Clear session')
    reset_parser.add_argument('path', help='Project path')
    reset_parser.add_argument('--force', action='store_true')

    token_parser = subparsers.add_parser('token-status', help='Show token budget status')
    token_parser.add_argument('path', help='Project path')

    contract_parser = subparsers.add_parser('contract', help='I/O contract management')
    contract_sub = contract_parser.add_subparsers(dest='contract_cmd', help='Contract commands')
    contract_declare = contract_sub.add_parser('declare', help='Declare I/O contract')
    contract_declare.add_argument('path', help='Project path')
    contract_declare.add_argument('--symbol', required=True, help='Function name')
    contract_declare.add_argument('--inputs', required=True, help='JSON: {"param": "type"}')
    contract_declare.add_argument('--output', required=True, help='Return type')
    contract_list = contract_sub.add_parser('list', help='List all contracts')
    contract_list.add_argument('path', help='Project path')
    contract_drift = contract_sub.add_parser('drift', help='Check I/O drift for symbol')
    contract_drift.add_argument('path', help='Project path')
    contract_drift.add_argument('--symbol', required=True, help='Function name')
    contract_drift.add_argument('--file', required=True, help='File path to check')

    trace_parser = subparsers.add_parser('trace', help='Execution trace management')
    trace_sub = trace_parser.add_subparsers(dest='trace_cmd', help='Trace commands')
    trace_record = trace_sub.add_parser('record', help='Record execution trace')
    trace_record.add_argument('path', help='Project path')
    trace_record.add_argument('--symbol', required=True, help='Function name')
    trace_record.add_argument('--inputs', required=True, help='JSON inputs')
    trace_record.add_argument('--output', required=True, help='Output value')
    trace_view = trace_sub.add_parser('view', help='View traces for symbol')
    trace_view.add_argument('path', help='Project path')
    trace_view.add_argument('--symbol', required=True, help='Function name')
    trace_stability = trace_sub.add_parser('stability', help='Check stability for symbol')
    trace_stability.add_argument('path', help='Project path')
    trace_stability.add_argument('--symbol', required=True, help='Function name')

    migrate_parser = subparsers.add_parser('migrate', help='Run database migrations')
    migrate_parser.add_argument('path', help='Project path')
    migrate_parser.add_argument('--create', help='Create new migration with name')

    read_parser = subparsers.add_parser('read', help='Read a file through Guardian mediation')
    read_parser.add_argument('path', help='Project path')
    read_parser.add_argument('--file', required=True, help='File to read (relative to project)')

    decision_parser = subparsers.add_parser('decision', help='Decision records (ADR-lite)')
    decision_sub = decision_parser.add_subparsers(dest='decision_cmd')
    decision_record = decision_sub.add_parser('record', help='Record a decision')
    decision_record.add_argument('path', help='Project path')
    decision_record.add_argument('--actor', required=True)
    decision_record.add_argument('--reason', required=True)
    decision_record.add_argument('--evidence', help='Comma-separated evidence')
    decision_record.add_argument('--consequences', help='Comma-separated consequences')
    decision_record.add_argument('--confidence', type=float, default=1.0)
    decision_record.add_argument('--symbol')
    decision_list = decision_sub.add_parser('list', help='List decisions')
    decision_list.add_argument('path', help='Project path')
    decision_list.add_argument('--symbol')
    decision_list.add_argument('--limit', type=int, default=20)

    assumption_parser = subparsers.add_parser('assumption', help='Assumption tracking')
    assumption_sub = assumption_parser.add_subparsers(dest='assumption_cmd')
    assumption_add = assumption_sub.add_parser('add', help='Record an assumption')
    assumption_add.add_argument('path', help='Project path')
    assumption_add.add_argument('--text', required=True)
    assumption_add.add_argument('--symbol')
    assumption_list = assumption_sub.add_parser('list', help='List active assumptions')
    assumption_list.add_argument('path', help='Project path')
    assumption_list.add_argument('--symbol')
    assumption_violate = assumption_sub.add_parser('violate', help='Flag an assumption as violated')
    assumption_violate.add_argument('path', help='Project path')
    assumption_violate.add_argument('--id', type=int, required=True)
    assumption_violate.add_argument('--evidence', required=True)

    invariant_parser = subparsers.add_parser('invariant', help='Invariant declarations and checks')
    invariant_sub = invariant_parser.add_subparsers(dest='invariant_cmd')
    invariant_declare = invariant_sub.add_parser('declare', help='Declare an invariant')
    invariant_declare.add_argument('path', help='Project path')
    invariant_declare.add_argument('--name', required=True)
    invariant_declare.add_argument('--description', required=True)
    invariant_declare.add_argument('--scope')
    invariant_declare.add_argument('--severity', default='high', choices=['low', 'medium', 'high', 'critical'])
    invariant_declare.add_argument('--check', help='Mechanical check expr, e.g. no_bare_except, must_call:log_event')
    invariant_list = invariant_sub.add_parser('list', help='List invariants')
    invariant_list.add_argument('path', help='Project path')
    invariant_check = invariant_sub.add_parser('check', help='Check a file against declared invariants')
    invariant_check.add_argument('path', help='Project path')
    invariant_check.add_argument('--file', required=True)

    trust_parser = subparsers.add_parser('trust', help='Per-agent trust scores')
    trust_sub = trust_parser.add_subparsers(dest='trust_cmd')
    trust_show = trust_sub.add_parser('show', help='Show trust score for one agent')
    trust_show.add_argument('path', help='Project path')
    trust_show.add_argument('--agent', required=True)
    trust_board = trust_sub.add_parser('leaderboard', help='Rank agents by compliance')
    trust_board.add_argument('path', help='Project path')

    blast_parser = subparsers.add_parser('blast-radius', help='Blast radius analysis for a symbol')
    blast_parser.add_argument('path', help='Project path')
    blast_parser.add_argument('--symbol', required=True)

    scan_deps_parser = subparsers.add_parser('scan-dependencies', help='(Re)build the cross-file dependency graph used by blast-radius')
    scan_deps_parser.add_argument('path', help='Project path')

    replay_parser = subparsers.add_parser('replay', help='Semantic timeline for a symbol/file')
    replay_parser.add_argument('path', help='Project path')
    replay_parser.add_argument('--symbol')
    replay_parser.add_argument('--file')
    replay_parser.add_argument('--limit', type=int, default=20)

    simulate_parser = subparsers.add_parser('simulate', help='Heuristic change-impact simulation')
    simulate_parser.add_argument('path', help='Project path')
    simulate_parser.add_argument('--symbol', required=True)
    simulate_parser.add_argument('--description', default='')

    telemetry_parser = subparsers.add_parser('telemetry', help='Local, opt-in usage telemetry')
    telemetry_sub = telemetry_parser.add_subparsers(dest='telemetry_cmd')
    for sub_name, help_text in (('enable', 'Turn telemetry on'), ('disable', 'Turn telemetry off (default)'),
                                 ('status', 'Show telemetry state')):
        p = telemetry_sub.add_parser(sub_name, help=help_text)
        p.add_argument('path', help='Project path')
    telemetry_export = telemetry_sub.add_parser('export', help='Export recorded events to a JSON file')
    telemetry_export.add_argument('path', help='Project path')
    telemetry_export.add_argument('--out', default='anchor_telemetry_export.json')

    incident_parser = subparsers.add_parser('incident', help='Record/list incident case studies')
    incident_sub = incident_parser.add_subparsers(dest='incident_cmd')
    incident_record = incident_sub.add_parser('record', help='Record an incident')
    incident_record.add_argument('path', help='Project path')
    incident_record.add_argument('--name', required=True)
    incident_record.add_argument('--cause', required=True)
    incident_record.add_argument('--impact', required=True)
    incident_record.add_argument('--detection', required=True)
    incident_record.add_argument('--severity', default='medium', choices=['low', 'medium', 'high', 'critical'])
    incident_list = incident_sub.add_parser('list', help='List incidents')
    incident_list.add_argument('path', help='Project path')

    reachability_parser = subparsers.add_parser('reachability', help='Find orphaned/never-called code')
    reachability_parser.add_argument('path', help='Project path')

    agent_parser = subparsers.add_parser('agent', help='Use an LLM (any provider) as an Anchor-mediated agent')
    agent_parser.add_argument('--provider', choices=['gemini', 'ollama', 'openai', 'anthropic'],
                               help='Override the resolved default (env ANCHOR_AGENT_PROVIDER > .anchor/agent_config.json > gemini)')
    agent_parser.add_argument('--model', help='Override the provider default model')
    agent_sub = agent_parser.add_subparsers(dest='agent_cmd')

    agent_providers = agent_sub.add_parser('providers', help='List available providers')

    agent_set_default = agent_sub.add_parser('set-default', help='Persist a default provider for this project')
    agent_set_default.add_argument('path', help='Project path')
    agent_set_default.add_argument('provider', choices=['gemini', 'ollama', 'openai', 'anthropic'])
    agent_set_default.add_argument('--model', help='Default model for this provider')

    agent_explain = agent_sub.add_parser('explain-report', help='Plain-language summary of the stability report')
    agent_explain.add_argument('path', help='Project path')

    agent_blast = agent_sub.add_parser('explain-blast-radius')
    agent_blast.add_argument('path', help='Project path')
    agent_blast.add_argument('--symbol', required=True)

    agent_fix = agent_sub.add_parser('propose-fix', help='Ask the model to draft a fix (issues a ticket, does not write)')
    agent_fix.add_argument('path', help='Project path')
    agent_fix.add_argument('--file', required=True)
    agent_fix.add_argument('--instruction', required=True)

    # Provider-agnostic mediation for ANY external agent (OpenHands, Openclaw, Cursor,
    # or a bare shell script) that wants to submit edits through Anchor without using
    # the Python integration classes at all -- just shell + files + JSON.
    propose_parser = subparsers.add_parser('propose', help='Submit an edit proposal from files (for external/shell agents)')
    propose_parser.add_argument('path', help='Project path')
    propose_parser.add_argument('--file', required=True, help='Target file, relative to project')
    propose_parser.add_argument('--old-file', required=True, help='Path to a file containing the current content')
    propose_parser.add_argument('--new-file', required=True, help='Path to a file containing the proposed new content')
    propose_parser.add_argument('--reason', default='')
    propose_parser.add_argument('--actor', required=True, help='Identify the calling agent, e.g. openhands, openclaw, phi4-local')
    propose_parser.add_argument('--confidence', type=float, default=1.0)

    execute_parser = subparsers.add_parser('execute', help='Execute a previously issued edit ticket')
    execute_parser.add_argument('path', help='Project path')
    execute_parser.add_argument('--ticket', required=True)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    if args.command == 'agent' and args.agent_cmd == 'providers':
        from .integrations.factory import list_providers
        for name, desc in list_providers().items():
            print(f"  {name:<10} {desc}")
        return

    project_path = os.path.abspath(args.path)

    if args.command == 'init':
        anchor = AnchorSidecar(project_path)
        
        try:
            session_id = anchor.init_session(reuse_existing=not args.force)
            
            # Detect reuse
            is_reuse = False
            if not args.force:
                existing = anchor.db.query(
                    'SELECT session_id FROM sessions WHERE project_root = ? AND session_id = ?',
                    (project_path, session_id)
                )
                is_reuse = len(anchor.active_files) > 0 or (existing and len(existing) > 0)
            
            if is_reuse:
                print(f"Reusing existing session: {session_id}")
            else:
                print(f"Anchor initialized: {session_id}")
                
            print(f"  Database: {os.path.join(project_path, '.anchor', 'anchor.db')}")
            
            if args.files:
                raw_patterns = [f.strip() for f in args.files.split(',')]
                resolved_files = []
                
                for pattern in raw_patterns:
                    if pattern == '.':
                        # Walk entire project, exclude hidden dirs
                        for root, dirs, files in os.walk(project_path):
                            dirs[:] = [
                                d for d in dirs 
                                if not d.startswith('.') 
                                and d not in ('__pycache__', 'node_modules', '.venv', 'venv', '.git', 'build', 'dist')
                            ]
                            for f in files:
                                full = os.path.join(root, f)
                                rel = os.path.relpath(full, project_path)
                                resolved_files.append(rel)
                    else:
                        full_pattern = os.path.join(project_path, pattern)
                        matches = glob.glob(full_pattern, recursive=True)
                        for match in matches:
                            if os.path.isfile(match):
                                rel = os.path.relpath(match, project_path)
                                resolved_files.append(rel)
                
                # Deduplicate
                seen = set()
                unique_files = []
                for f in resolved_files:
                    if f not in seen:
                        seen.add(f)
                        unique_files.append(f)
                
                # Apply tiered scope with token budgeting
                budget = anchor.set_scope(unique_files, project_path)
                
                # Report
                print(f"\n  Context (read-only):  {budget['context_count']} files")
                print(f"  Active (editable):    {budget['active_count']} files")
                print(f"  Frozen (protected):   {budget['frozen_count']} files")
                print(f"  Token budget:         {budget['total_tokens']:,} / {12000:,} ({budget['budget_percent']}%)")
                
                if budget['skipped'] > 0:
                    print(f"  Skipped:              {budget['skipped']} files (budget limit)")
                
                # Show active files (the editable targets)
                if anchor.active_files:
                    print(f"\n  Active targets:")
                    for f in anchor.active_files[:5]:
                        print(f"    - {f}")
                    if len(anchor.active_files) > 5:
                        print(f"    ... and {len(anchor.active_files) - 5} more")
                        
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif args.command == 'status':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        print(f"Project: {project_path}")
        print(f"Session: {anchor.session_id}")
        print(f"  Context:  {len(anchor.context_files)} files (read-only)")
        print(f"  Active:   {len(anchor.active_files)} files (editable)")
        print(f"  Frozen:   {len(anchor.frozen_files)} files (protected)")
        
        # Show token usage
        from .sidecar import estimate_tokens, MAX_CONTEXT_TOKENS
        total = sum(estimate_tokens(os.path.join(project_path, f)) for f in anchor.context_files + anchor.active_files + anchor.frozen_files)
        print(f"\nToken Budget: {total:,} / {MAX_CONTEXT_TOKENS:,} ({round(total/MAX_CONTEXT_TOKENS*100, 1)}%)")
        
        token_status = anchor.token_guard.get_status()
        print(f"  Daily:    {token_status['daily_budget']:,}")
        print(f"  Used:     {token_status['total_used']:,} ({token_status['percent_used']}%)")
        print(f"  Remaining: {token_status['total_remaining']:,}")

    elif args.command == 'report':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        from .reports.stability_report import StabilityReport
        report = anchor.get_stability_report()
        if args.format == 'json':
            print(StabilityReport.json_report(report))
        elif args.format == 'csv':
            print(StabilityReport.csv_export(report))
        else:
            print(StabilityReport.format(report))

    elif args.command == 'history':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        ops = anchor.db.query('SELECT * FROM operations ORDER BY timestamp DESC LIMIT ?', (args.limit,))
        print(f"Last {len(ops)} operations:")
        print("-" * 60)
        for op in ops:
            print(f"{op['timestamp']} | {op['operation']:<6} | {op['path']}")

    elif args.command == 'freeze':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        files = [f.strip() for f in args.files.split(',')]
        # Add to frozen, remove from active
        for f in files:
            abs_f = os.path.join(project_path, f)
            if f in anchor.active_files:
                anchor.active_files.remove(f)
            if f not in anchor.frozen_files:
                anchor.frozen_files.append(f)
        anchor.save_scope()
        print(f"Frozen {len(files)} files: {', '.join(files)}")

    elif args.command == 'reset':
        if not args.force:
            print("Warning: This clears all session data. Use --force to confirm.")
            return
        anchor = AnchorSidecar(project_path)
        db_path = os.path.join(project_path, '.anchor', 'anchor.db')
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"Cleared: {db_path}")
        else:
            print("No session found.")

    elif args.command == 'token-status':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        status = anchor.token_guard.get_status()
        print("Token Budget Status")
        print(f"  Daily:    {status['daily_budget']:,}")
        print(f"  Used:     {status['total_used']:,} ({status['percent_used']}%)")
        print(f"  Remaining: {status['total_remaining']:,}")
        print(f"  Read:     {status['read_used']:,} / {status['read_budget']:,}")
        print(f"  Edit:     {status['edit_used']:,} / {status['edit_budget']:,}")
        print(f"  Cached:   {status['cached_files']} files")

    elif args.command == 'contract':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        if args.contract_cmd == 'declare':
            import json
            inputs = json.loads(args.inputs)
            anchor.io_contracts.declare_contract(args.symbol, inputs, args.output)
            print(f"Contract declared for {args.symbol}")
        elif args.contract_cmd == 'list':
            contracts = anchor.io_contracts.list_all_contracts()
            print(f"Found {len(contracts)} contracts:")
            for c in contracts:
                print(f"  {c['symbol']}: ({', '.join(c['inputs'].keys())}) -> {c['output_type']} [confidence: {c['confidence']:.1f}]")
        elif args.contract_cmd == 'drift':
            with open(os.path.join(project_path, args.file), 'r') as f:
                source = f.read()
            input_drifts = anchor.io_contracts.detect_input_drift(args.symbol, source)
            output_drift = anchor.io_contracts.detect_output_drift(args.symbol, source)
            if input_drifts or output_drift:
                print(f"DRIFT DETECTED for {args.symbol}:")
                for d in input_drifts:
                    print(f"  Input: {d['type']} - {d.get('param', '')}")
                if output_drift:
                    print(f"  Output: {output_drift['type']} - expected {output_drift['expected']}, got {output_drift['actual']}")
            else:
                print(f"No I/O drift detected for {args.symbol}")

    elif args.command == 'trace':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        if args.trace_cmd == 'record':
            import json
            inputs = json.loads(args.inputs)
            call_id = anchor.execution_traces.record_trace(args.symbol, inputs, args.output)
            print(f"Trace recorded: {call_id}")
        elif args.trace_cmd == 'view':
            traces = anchor.execution_traces.get_traces(args.symbol)
            print(f"Last {len(traces)} traces for {args.symbol}:")
            for t in traces:
                print(f"  {t['call_id']} | {t['timestamp']}")
        elif args.trace_cmd == 'stability':
            result = anchor.execution_traces.check_stability(args.symbol)
            print(f"Stability for {args.symbol}:")
            print(f"  Stable: {result['stable']}")
            print(f"  Sample size: {result['sample_size']}")
            print(f"  Mismatch rate: {result['mismatch_rate']:.1%}")

    elif args.command == 'migrate':
        from .data.migrations import MigrationRunner
        db_path = os.path.join(project_path, '.anchor', 'anchor.db')
        runner = MigrationRunner(db_path)
        if args.create:
            filepath = runner.create_migration(args.create)
            print(f"Created migration: {filepath}")
        else:
            ran = runner.run_all()
            print(f"Ran {ran} pending migrations")

    elif args.command == 'read':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        try:
            result = anchor.read_file(args.file)
            print(f"--- {result.path} (sha256:{result.hash[:12]}) ---")
            print(result.content)
        except PermissionError as e:
            print(f"Denied: {e}")
            sys.exit(1)

    elif args.command == 'decision':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        if args.decision_cmd == 'record':
            evidence = [e.strip() for e in args.evidence.split(',')] if args.evidence else []
            consequences = [c.strip() for c in args.consequences.split(',')] if args.consequences else []
            did = anchor.decisions.record_decision(
                actor=args.actor, reason=args.reason, evidence=evidence,
                consequences=consequences, confidence=args.confidence, symbol_name=args.symbol
            )
            print(f"Recorded {did}")
            if args.confidence < 0.6:
                print(f"  Note: low confidence ({args.confidence}). Consider human review.")
        elif args.decision_cmd == 'list':
            decisions = anchor.decisions.list_decisions(symbol_name=args.symbol, limit=args.limit)
            print(f"Found {len(decisions)} decisions:")
            for d in decisions:
                print(f"  [{d['id']}] {d['actor']} (confidence {d['confidence']}): {d['reason']}")
                if d['consequences']:
                    print(f"      -> {', '.join(d['consequences'])}")

    elif args.command == 'assumption':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        if args.assumption_cmd == 'add':
            aid = anchor.assumptions.record_assumption(args.text, symbol_name=args.symbol)
            print(f"Recorded assumption #{aid}")
        elif args.assumption_cmd == 'list':
            items = anchor.assumptions.list_assumptions(symbol_name=args.symbol)
            print(f"Found {len(items)} active assumptions:")
            for a in items:
                scope = f" [{a['symbol_name']}]" if a.get('symbol_name') else ""
                print(f"  #{a['id']}{scope}: {a['text']}")
        elif args.assumption_cmd == 'violate':
            anchor.assumptions.flag_violation(args.id, args.evidence)
            print(f"Assumption #{args.id} flagged as violated.")

    elif args.command == 'invariant':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        if args.invariant_cmd == 'declare':
            iid = anchor.invariants.declare_invariant(
                args.name, args.description, scope=args.scope, severity=args.severity, check_expr=args.check
            )
            print(f"Declared invariant #{iid}: {args.name}")
            if args.check and not anchor.invariants.is_mechanically_checkable(args.check):
                print(f"  Note: '{args.check}' is not a recognized mechanical check; stored as documentation-only.")
        elif args.invariant_cmd == 'list':
            items = anchor.invariants.list_invariants()
            print(f"Found {len(items)} invariants:")
            for i in items:
                kind = 'mechanical' if anchor.invariants.is_mechanically_checkable(i['check_expr']) else 'documentation-only'
                print(f"  [{i['severity']}] {i['name']} ({kind}): {i['description']}")
        elif args.invariant_cmd == 'check':
            with open(os.path.join(project_path, args.file), 'r') as f:
                source = f.read()
            violations = anchor.invariants.check_source(args.file, source)
            if violations:
                print(f"VIOLATIONS in {args.file}:")
                for v in violations:
                    print(f"  [{v['severity']}] {v['invariant']}: {v['detail']}")
            else:
                print(f"No mechanically-checkable invariant violations in {args.file}")

    elif args.command == 'trust':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        if args.trust_cmd == 'show':
            score = anchor.trust.get_trust_score(args.agent)
            print(f"Trust score for {args.agent}:")
            for k, v in score.items():
                print(f"  {k}: {v}")
        elif args.trust_cmd == 'leaderboard':
            board = anchor.trust.leaderboard()
            print(f"Agent leaderboard ({len(board)} agents):")
            for row in board:
                print(f"  {row['agent_name']:<20} compliance={row['compliance_rate']:.1%}  ops={row['total_ops']}")

    elif args.command == 'blast-radius':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        result = anchor.blast_radius.compute(args.symbol)
        if not result.get('found'):
            print(f"No history found for symbol '{args.symbol}'")
        else:
            print(f"Blast radius for '{args.symbol}':")
            print(f"  Modules touched:   {result['modules_touched']}")
            print(f"  Functions touched: {result['functions_touched']}")
            print(f"  Contracts touched: {result['contracts_touched']}")
            print(f"  Historical breaks: {result['historical_breakages']}")
            print(f"  Risk:              {result['risk']}")

    elif args.command == 'scan-dependencies':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        anchor.scan_dependencies()
        count = anchor.db.query('SELECT COUNT(*) as c FROM dependencies')[0]['c']
        print(f"Dependency graph rebuilt: {count} call relationship(s) recorded.")

    elif args.command == 'replay':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        events = anchor.simulation.replay(symbol_name=args.symbol, file_path=args.file, limit=args.limit)
        print(f"Timeline ({len(events)} events):")
        for e in events:
            print(f"  {e.get('ts', '?')} [{e['kind']}] {e.get('reason', '')}")

    elif args.command == 'simulate':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        result = anchor.simulation.simulate_change(args.symbol, args.description)
        print(f"Simulation for '{args.symbol}' (heuristic, not a guarantee):")
        if 'note' in result:
            print(f"  {result['note']}")
        else:
            print(f"  Risk: {result['blast_radius']['risk']}")
            print(f"  Historical project break rate: {result['historical_project_break_rate']}")
            print(f"  Recommendation: {result['recommendation']}")

    elif args.command == 'telemetry':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        if args.telemetry_cmd == 'enable':
            anchor.telemetry.enable()
            print("Telemetry enabled. Nothing is sent anywhere automatically -- use "
                  "'anchor telemetry export' to see exactly what's stored, on your terms.")
        elif args.telemetry_cmd == 'disable':
            anchor.telemetry.disable()
            print("Telemetry disabled (this is also the default for new projects).")
        elif args.telemetry_cmd == 'status':
            status = anchor.telemetry.status()
            print(f"Telemetry: {'ENABLED' if status['enabled'] else 'disabled'}")
            print(f"  Events recorded locally: {status['events_recorded']}")
            print(f"  Config: {status['config_path']}")
        elif args.telemetry_cmd == 'export':
            n = anchor.telemetry.export(args.out)
            print(f"Exported {n} events to {args.out}")

    elif args.command == 'incident':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        if args.incident_cmd == 'record':
            iid = anchor.incidents.record_incident(args.name, args.cause, args.impact, args.detection, args.severity)
            print(f"Recorded incident #{iid}: {args.name}")
        elif args.incident_cmd == 'list':
            items = anchor.incidents.list_incidents()
            print(f"Found {len(items)} incidents:")
            for i in items:
                print(f"  #{i['id']} [{i['severity']}] {i['name']}")
                print(f"      cause: {i['cause']}")
                print(f"      impact: {i['impact']}")
                print(f"      detected via: {i['detection']}")

    elif args.command == 'reachability':
        anchor = AnchorSidecar(project_path)
        result = anchor.reachability.analyze()
        print(f"Scanned {result['files_scanned']} files, {result['symbols_defined']} symbols defined.")
        print(f"Orphaned (defined but never referenced): {result['orphaned_count']}")
        for o in result['orphaned'][:30]:
            print(f"  {o['symbol']}  ({', '.join(o['files'])})")
        if result['orphaned_count'] > 30:
            print(f"  ... and {result['orphaned_count'] - 30} more")

    elif args.command == 'agent':
        from .integrations.factory import get_agent, list_providers, set_default_provider

        if args.agent_cmd == 'set-default':
            set_default_provider(project_path, args.provider, **({'model': args.model} if args.model else {}))
            print(f"Default agent provider for this project set to '{args.provider}'.")
        else:
            anchor = AnchorSidecar(project_path)
            anchor.init_session()
            kwargs = {'model': args.model} if args.model else {}
            try:
                agent = get_agent(anchor, provider=args.provider, **kwargs)
            except ValueError as e:
                print(f"Error: {e}")
                sys.exit(1)
            print(f"Using provider: {agent.provider_name} (actor: {agent.actor_name})")

            try:
                if args.agent_cmd == 'explain-report':
                    print(agent.explain_report())
                elif args.agent_cmd == 'explain-blast-radius':
                    print(agent.explain_blast_radius(args.symbol))
                elif args.agent_cmd == 'propose-fix':
                    ticket = agent.propose_fix(args.file, args.instruction)
                    print(f"Ticket issued: {ticket}")
                    print(f"Nothing written yet. Review, then run: anchor execute {project_path} --ticket {ticket}")
                else:
                    print("Specify a subcommand: providers | set-default | explain-report | explain-blast-radius | propose-fix")
            except Exception as e:
                print(f"Agent error: {e}")
                sys.exit(1)

    elif args.command == 'propose':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        with open(args.old_file, 'r') as f:
            old_content = f.read()
        with open(args.new_file, 'r') as f:
            new_content = f.read()
        proposal = EditProposal(path=args.file, old_content=old_content, new_content=new_content,
                                 reason=args.reason, actor=args.actor, confidence=args.confidence)
        try:
            ticket = anchor.propose_edit(proposal)
            print(f"Ticket issued: {ticket}")
        except PermissionError as e:
            print(f"Denied: {e}")
            sys.exit(1)

    elif args.command == 'execute':
        anchor = AnchorSidecar(project_path)
        anchor.init_session()
        try:
            result = anchor.execute_ticket(args.ticket)
            print(f"Applied: {result['path']} (sha256:{result['hash'][:12]})")
            if result['invariant_violations']:
                print(f"  Invariant violations recorded: {len(result['invariant_violations'])}")
                for v in result['invariant_violations']:
                    print(f"    [{v['severity']}] {v['invariant']}: {v['detail']}")
        except (ValueError, PermissionError) as e:
            print(f"Failed: {e}")
            sys.exit(1)


if __name__ == '__main__':
    main()

