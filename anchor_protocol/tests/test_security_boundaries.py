"""Test security boundaries and scope enforcement."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from anchor_protocol.sidecar import AnchorSidecar, EditProposal


class TestSecurityBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.anchor = AnchorSidecar(self.temp_dir)
        self.anchor.init_session()
        self.test_file = os.path.join(self.temp_dir, 'src', 'main.py')
        os.makedirs(os.path.dirname(self.test_file), exist_ok=True)
        with open(self.test_file, 'w') as f:
            f.write("def hello():\n    return 'world'\n")

    def test_path_sandbox(self):
        """AI cannot access outside project root."""
        with self.assertRaises(PermissionError) as ctx:
            self.anchor.read_file('../etc/passwd')
        self.assertIn("SecurityViolation", str(ctx.exception))

    def test_forbidden_patterns(self):
        """AI cannot access forbidden paths."""
        with self.assertRaises(PermissionError) as ctx:
            self.anchor.read_file('.env')
        self.assertIn("SecurityViolation", str(ctx.exception))

    def test_scope_enforcement(self):
        """AI cannot modify files outside active set."""
        self.anchor.set_manual_scope(active_files=['src/other.py'])
        proposal = EditProposal(path='src/main.py', old_content="def hello():\n    return 'world'\n", new_content="def hello():\n    return 'universe'\n", reason='test')
        with self.assertRaises(PermissionError) as ctx:
            self.anchor.propose_edit(proposal)
        self.assertIn("ScopeViolation", str(ctx.exception))

    def test_frozen_files(self):
        """AI cannot modify frozen files."""
        self.anchor.set_manual_scope(active_files=['src/main.py'], frozen_files=['src/main.py'])
        proposal = EditProposal(path='src/main.py', old_content="def hello():\n    return 'world'\n", new_content="def hello():\n    return 'universe'\n", reason='test')
        with self.assertRaises(PermissionError) as ctx:
            self.anchor.propose_edit(proposal)
        self.assertIn("ScopeViolation", str(ctx.exception))

    def test_max_active_files(self):
        """Cannot set more than 5 active files."""
        with self.assertRaises(ValueError):
            self.anchor.set_manual_scope(active_files=[f'f{i}.py' for i in range(6)])

    def test_syntax_validation(self):
        """Invalid Python is rejected."""
        self.anchor.set_manual_scope(active_files=['src/main.py'])
        proposal = EditProposal(path='src/main.py', old_content="def hello():\n    return 'world'\n", new_content="def hello(\n    invalid syntax\n", reason='test')
        ticket = self.anchor.propose_edit(proposal)
        with self.assertRaises(ValueError) as ctx:
            self.anchor.execute_ticket(ticket)
        self.assertIn("Syntax", str(ctx.exception))

    def test_semantic_precondition(self):
        """Stale edits are rejected."""
        self.anchor.set_manual_scope(active_files=['src/main.py'])
        result = self.anchor.read_file('src/main.py')
        with open(self.test_file, 'w') as f:
            f.write("def hello():\n    return 'modified'\n")
        proposal = EditProposal(path='src/main.py', old_content=result.content, new_content="def hello():\n    return 'new'\n", reason='test')
        ticket = self.anchor.propose_edit(proposal)
        with self.assertRaises(ValueError) as ctx:
            self.anchor.execute_ticket(ticket)
        self.assertIn("Semantic", str(ctx.exception))

    def test_auto_rollback(self):
        """Failed operations are auto-rolled back."""
        self.anchor.set_manual_scope(active_files=['src/main.py'])
        result = self.anchor.read_file('src/main.py')
        proposal = EditProposal(path='src/main.py', old_content=result.content, new_content="def hello():\n    return 'success'\n", reason='test')
        ticket = self.anchor.propose_edit(proposal)
        result = self.anchor.execute_ticket(ticket)
        self.assertTrue(result['success'])
        self.assertTrue(os.path.exists(result['backup']))


class TestTokenGuard(unittest.TestCase):
    def test_budget_exhaustion(self):
        """Token budget prevents excessive reads."""
        from anchor_protocol.optimizers.token_guard import TokenGuard
        guard = TokenGuard(daily_budget=1000)
        guard.read_used = 600
        with self.assertRaises(RuntimeError) as ctx:
            guard.check_read_budget('new_file.py')
        self.assertIn("budget", str(ctx.exception).lower())


class TestDriftDetection(unittest.TestCase):
    def test_detect_missing_symbol(self):
        """Detect when symbol is removed."""
        temp_dir = tempfile.mkdtemp()
        anchor = AnchorSidecar(temp_dir)
        anchor.init_session()
        test_file = os.path.join(temp_dir, 'test.py')
        with open(test_file, 'w') as f:
            f.write('def foo():\n    return 1\n')
        anchor.read_file('test.py')
        with open(test_file, 'w') as f:
            f.write('# empty file\n')
        drifts = anchor.detect_drift('test.py')
        self.assertTrue(any(d['type'] == 'missing_symbol' for d in drifts))

    def test_detect_silent_drift(self):
        """Detect silent drift (new symbols)."""
        temp_dir = tempfile.mkdtemp()
        anchor = AnchorSidecar(temp_dir)
        anchor.init_session()
        test_file = os.path.join(temp_dir, 'test.py')
        with open(test_file, 'w') as f:
            f.write('def foo():\n    return 1\n')
        anchor.read_file('test.py')
        with open(test_file, 'w') as f:
            f.write('def foo():\n    return 1\ndef bar():\n    return 2\n')
        drifts = anchor.detect_drift('test.py')
        self.assertTrue(any(d['type'] == 'silent_drift' for d in drifts))


class TestGovernanceLayer(unittest.TestCase):
    """Decision records, assumptions, invariants, trust, blast radius, simulation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.anchor = AnchorSidecar(self.temp_dir)
        self.anchor.init_session()
        self.test_file = os.path.join(self.temp_dir, 'payments.py')
        with open(self.test_file, 'w') as f:
            f.write(
                "def process_payment(amount, provider):\n"
                "    if provider == 'stripe':\n"
                "        return charge_stripe(amount)\n"
                "    return None\n\n"
                "def charge_stripe(amount):\n"
                "    return {'status': 'ok', 'amount': amount}\n"
            )
        self.anchor.read_file('payments.py')

    def test_decision_record_roundtrip(self):
        did = self.anchor.decisions.record_decision(
            actor='claude-code', reason='Avoid circular import', evidence=['tests/x.py'],
            consequences=['moved receipt logic'], confidence=0.9, symbol_name='process_payment'
        )
        self.assertTrue(did.startswith('DEC-'))
        decision = self.anchor.decisions.get_decision(did)
        self.assertEqual(decision['actor'], 'claude-code')
        self.assertEqual(decision['evidence'], ['tests/x.py'])

    def test_decision_confidence_bounds(self):
        with self.assertRaises(ValueError):
            self.anchor.decisions.record_decision(actor='x', reason='bad confidence', confidence=1.5)

    def test_requires_human_approval_policy(self):
        self.assertTrue(self.anchor.decisions.requires_human_approval(0.4, 'HIGH'))
        self.assertFalse(self.anchor.decisions.requires_human_approval(0.9, 'HIGH'))
        self.assertFalse(self.anchor.decisions.requires_human_approval(0.4, 'LOW'))

    def test_assumption_lifecycle(self):
        aid = self.anchor.assumptions.record_assumption(
            'There is only one payment provider', symbol_name='process_payment'
        )
        active = self.anchor.assumptions.list_assumptions(symbol_name='process_payment')
        self.assertEqual(len(active), 1)
        self.anchor.assumptions.flag_violation(aid, 'Paystack added in commit abc123')
        violated = self.anchor.assumptions.get_violated()
        self.assertEqual(len(violated), 1)
        # A violated assumption should no longer show up as active
        still_active = self.anchor.assumptions.list_assumptions(symbol_name='process_payment')
        self.assertEqual(len(still_active), 0)

    def test_invariant_no_bare_except_detects_violation(self):
        self.anchor.invariants.declare_invariant(
            'no_bare_except', 'never swallow exceptions', check_expr='no_bare_except', severity='high'
        )
        bad_source = "def f():\n    try:\n        pass\n    except:\n        pass\n"
        violations = self.anchor.invariants.check_source('bad.py', bad_source)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]['invariant'], 'no_bare_except')

    def test_invariant_must_call_passes_when_present(self):
        self.anchor.invariants.declare_invariant(
            'must_call_charge', 'process_payment must call charge_stripe',
            check_expr='must_call:charge_stripe', severity='medium'
        )
        with open(self.test_file) as f:
            source = f.read()
        violations = self.anchor.invariants.check_source('payments.py', source)
        self.assertEqual(len(violations), 0)

    def test_documentation_only_invariant_is_not_mechanically_checked(self):
        self.anchor.invariants.declare_invariant(
            'order_needs_customer', 'An order cannot exist without a customer', check_expr=None
        )
        violations = self.anchor.invariants.check_source('anything.py', 'x = 1\n')
        self.assertEqual(len(violations), 0)  # can't be mechanically verified, so no false claim of a check

    def test_trust_score_tracks_compliance(self):
        self.anchor.trust.record_operation('claude-code', contract_compliant=True, invariant_compliant=True)
        self.anchor.trust.record_operation('claude-code', contract_compliant=False, invariant_compliant=True)
        score = self.anchor.trust.get_trust_score('claude-code')
        self.assertEqual(score['total_ops'], 2)
        self.assertEqual(score['contract_violations'], 1)
        self.assertAlmostEqual(score['compliance_rate'], 0.5)

    def test_trust_leaderboard_orders_by_compliance(self):
        self.anchor.trust.record_operation('reliable-agent', contract_compliant=True)
        self.anchor.trust.record_operation('reliable-agent', contract_compliant=True)
        self.anchor.trust.record_operation('flaky-agent', contract_compliant=False)
        self.anchor.trust.record_operation('flaky-agent', contract_compliant=True)
        board = self.anchor.trust.leaderboard()
        self.assertEqual(board[0]['agent_name'], 'reliable-agent')

    def test_blast_radius_unknown_symbol(self):
        result = self.anchor.blast_radius.compute('does_not_exist')
        self.assertFalse(result['found'])

    def test_blast_radius_known_symbol(self):
        result = self.anchor.blast_radius.compute('charge_stripe')
        self.assertTrue(result['found'])
        self.assertIn(result['risk'], ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'))

    def test_simulate_change_is_labeled_heuristic(self):
        result = self.anchor.simulation.simulate_change('process_payment', 'add paystack')
        self.assertTrue(result['heuristic'])

    def test_replay_returns_recorded_decision(self):
        self.anchor.decisions.record_decision(
            actor='claude-code', reason='initial payment handling', symbol_name='process_payment'
        )
        timeline = self.anchor.simulation.replay(symbol_name='process_payment')
        self.assertTrue(any(e['kind'] == 'decision' for e in timeline))

    def test_execute_ticket_records_invariant_violation(self):
        self.anchor.set_manual_scope(active_files=['payments.py'])
        self.anchor.invariants.declare_invariant(
            'no_bare_except', 'never swallow exceptions', check_expr='no_bare_except', severity='high'
        )
        with open(self.test_file) as f:
            old_content = f.read()
        new_content = old_content + "\ndef risky():\n    try:\n        pass\n    except:\n        pass\n"
        proposal = EditProposal(path='payments.py', old_content=old_content, new_content=new_content,
                                 reason='add risky handler', actor='claude-code')
        ticket = self.anchor.propose_edit(proposal)
        result = self.anchor.execute_ticket(ticket)
        self.assertTrue(result['success'])  # invariant violations are recorded, not blocking, by design
        self.assertEqual(len(result['invariant_violations']), 1)
        score = self.anchor.trust.get_trust_score('claude-code')
        self.assertEqual(score['invariant_violations'], 1)


    def test_execute_ticket_survives_new_sidecar_instance(self):
        """
        Regression test: propose_edit + execute_ticket used to only work within
        the same AnchorSidecar instance because tickets lived purely in memory.
        Any CLI-driven external agent (propose in one process, execute in a
        later one) would always fail with 'Unknown or expired ticket'.
        """
        self.anchor.set_manual_scope(active_files=['payments.py'])
        with open(self.test_file) as f:
            old_content = f.read()
        new_content = old_content.replace('return None', "return {'status': 'unsupported'}")
        proposal = EditProposal(path='payments.py', old_content=old_content, new_content=new_content,
                                 reason='cross-process test', actor='external-agent')
        ticket = self.anchor.propose_edit(proposal)

        # Simulate a fresh process: brand new AnchorSidecar pointed at the same project.
        fresh = AnchorSidecar(self.temp_dir)
        fresh.init_session()
        result = fresh.execute_ticket(ticket)
        self.assertTrue(result['success'])
        with open(self.test_file) as f:
            self.assertIn('unsupported', f.read())


class TestNewGovernanceModules(unittest.TestCase):
    """Incidents, reachability, telemetry, and the multi-provider agent factory."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.anchor = AnchorSidecar(self.temp_dir)
        self.anchor.init_session()

    def test_incident_record_and_list(self):
        self.anchor.incidents.record_incident(
            name='unreachable_persistence_layer',
            cause='Q.insert()/Q.select() do not exist on the query builder',
            impact='all reads/writes were unreachable',
            detection='end-to-end smoke test',
            severity='critical',
        )
        incidents = self.anchor.incidents.list_incidents()
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]['severity'], 'critical')

    def test_reachability_flags_orphaned_function(self):
        with open(os.path.join(self.temp_dir, 'mod.py'), 'w') as f:
            f.write("def used():\n    return 1\n\ndef never_called():\n    return 2\n\nused()\n")
        result = self.anchor.reachability.analyze()
        orphaned_names = {o['symbol'] for o in result['orphaned']}
        self.assertIn('never_called', orphaned_names)
        self.assertNotIn('used', orphaned_names)

    def test_telemetry_off_by_default(self):
        self.assertFalse(self.anchor.telemetry.is_enabled())
        self.anchor.telemetry.record_event('test_event', {'agent': 'x'})
        self.assertEqual(self.anchor.telemetry.status()['events_recorded'], 0)

    def test_telemetry_scrubs_forbidden_keys(self):
        self.anchor.telemetry.enable()
        self.anchor.telemetry.record_event('test_event', {'agent': 'x', 'source_code': 'print(1)'})
        events = self.anchor.db.query('SELECT payload FROM telemetry_events')
        self.assertNotIn('source_code', events[0]['payload'])

    def test_path_invariant_detects_raw_concatenation(self):
        self.anchor.invariants.declare_invariant(
            'path_invariant', 'paths must use os.path.join', check_expr='path_invariant', severity='high'
        )
        bad_source = "db_path = root + '/.anchor/anchor.db'\n"
        violations = self.anchor.invariants.check_source('db.py', bad_source)
        self.assertEqual(len(violations), 1)

    def test_agent_factory_resolves_saved_default(self):
        from anchor_protocol.integrations.factory import set_default_provider, get_agent
        from anchor_protocol.integrations.ollama_agent import OllamaAgent
        set_default_provider(self.temp_dir, 'ollama', model='phi4')
        agent = get_agent(self.anchor)
        self.assertIsInstance(agent, OllamaAgent)
        self.assertEqual(agent.actor_name, 'ollama-phi4')

    def test_agent_factory_explicit_provider_overrides_saved_default(self):
        from anchor_protocol.integrations.factory import set_default_provider, get_agent
        from anchor_protocol.integrations.gemini_agent import GeminiAgent
        set_default_provider(self.temp_dir, 'ollama')
        agent = get_agent(self.anchor, provider='gemini')
        self.assertIsInstance(agent, GeminiAgent)

    def test_agent_factory_rejects_unknown_provider(self):
        from anchor_protocol.integrations.factory import get_agent
        with self.assertRaises(ValueError):
            get_agent(self.anchor, provider='not-a-real-provider')


if __name__ == '__main__':
    unittest.main()