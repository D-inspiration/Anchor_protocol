"""Test analytics engine."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from anchor_protocol.sidecar import AnchorSidecar


class TestAnalytics(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.anchor = AnchorSidecar(self.temp_dir)
        self.anchor.init_session()
        self.test_file = os.path.join(self.temp_dir, 'test.py')
        with open(self.test_file, 'w') as f:
            f.write('def simple():\n    return 1\n\ndef complex_func(x, y, z):\n    if x > 0:\n        if y > 0:\n            for i in range(z):\n                if i % 2 == 0:\n                    print(i)\n    return x + y + z\n\nclass MyClass:\n    def method(self):\n        return self\n')

    def test_symbol_extraction(self):
        """Symbols are extracted correctly."""
        symbols = self.anchor.registry.extract_symbols(self.test_file, open(self.test_file).read())
        names = [s['name'] for s in symbols]
        self.assertIn('simple', names)
        self.assertIn('complex_func', names)
        self.assertIn('MyClass', names)

    def test_complexity_scoring(self):
        """Complex functions have higher scores."""
        symbols = self.anchor.registry.extract_symbols(self.test_file, open(self.test_file).read())
        simple = next(s for s in symbols if s['name'] == 'simple')
        complex_sym = next(s for s in symbols if s['name'] == 'complex_func')
        self.assertLess(simple['complexity_score'], complex_sym['complexity_score'])

    def test_drift_score_range(self):
        """Drift scores are within 0-1 range."""
        symbols = self.anchor.registry.extract_symbols(self.test_file, open(self.test_file).read())
        for sym in symbols:
            score = self.anchor.analytics.calculate_drift_score(sym['id'])
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)

    def test_report_generation(self):
        """Report contains expected fields."""
        report = self.anchor.get_stability_report()
        self.assertIn('drift_score', report)
        self.assertIn('drift_level', report)
        self.assertIn('top_risk_nodes', report)
        self.assertIn('detected_drifts', report)
        self.assertIn('repair_stats', report)
        self.assertIn('hotspots', report)


if __name__ == '__main__':
    unittest.main()