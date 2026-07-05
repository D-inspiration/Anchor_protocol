"""StabilityReport - CLI report formatter with I/O contract section."""

from typing import Dict, Any


class StabilityReport:
    @staticmethod
    def format(report: Dict[str, Any]) -> str:
        lines = []
        lines.append("╔" + "═" * 58 + "╗")
        lines.append("║" + " " * 17 + "ANCHOR STABILITY REPORT v0.2" + " " * 13 + "║")
        lines.append("╠" + "═" * 58 + "╣")
        score = report.get('drift_score', 0)
        level = report.get('drift_level', 'UNKNOWN')
        lines.append(f"║  Drift Score: {score:.2f} ({level})" + " " * (37 - len(level)) + "║")
        lines.append("║" + " " * 58 + "║")
        lines.append("║  TOP RISK NODES" + " " * 41 + "║")
        for i, node in enumerate(report.get('top_risk_nodes', [])[:5], 1):
            name = node.get('name', 'unknown')[:20]
            file_path = node.get('file', 'unknown')
            file_name = file_path.split('/')[-1][:15] if '/' in file_path else file_path[:15]
            node_score = node.get('drift_score', 0)
            line = f"║  {i}. {name:<20} [{file_name:<15}] {node_score:.2f}"
            lines.append(line + " " * (59 - len(line)) + "║")
        lines.append("║" + " " * 58 + "║")
        lines.append("║  DETECTED DRIFTS (7 days)" + " " * 31 + "║")
        drifts = report.get('detected_drifts', {})
        if drifts:
            for drift_type, count in drifts.items():
                line = f"║  • {drift_type}: {count}"
                lines.append(line + " " * (59 - len(line)) + "║")
        else:
            lines.append("║  • None detected" + " " * 41 + "║")
        lines.append("║" + " " * 58 + "║")
        silent = report.get('silent_drifts', 0)
        unresolved = report.get('unresolved_drifts', 0)
        lines.append(f"║  Silent: {silent}  |  Unresolved: {unresolved}" + " " * (31 - len(str(silent)) - len(str(unresolved))) + "║")
        lines.append("║" + " " * 58 + "║")
        lines.append(f"║  REPAIR LOOPS" + " " * 44 + "║")
        repair = report.get('repair_stats', {})
        avg_iter = repair.get('avg_iterations', 0)
        max_iter = repair.get('max_iterations', 0)
        lines.append(f"║  • Avg iterations: {avg_iter:.1f}" + " " * (37 - len(f"{avg_iter:.1f}")) + "║")
        lines.append(f"║  • Max iterations: {max_iter}" + " " * (38 - len(str(max_iter))) + "║")
        lines.append("║" + " " * 58 + "║")
        lines.append("║  I/O CONTRACT METRICS" + " " * 35 + "║")
        io = report.get('io_metrics', {})
        lines.append(f"║  • Contracts declared: {io.get('total_contracts', 0)}" + " " * (34 - len(str(io.get('total_contracts', 0)))) + "║")
        lines.append(f"║  • Coverage: {io.get('contract_coverage', 0)*100:.0f}%" + " " * (42 - len(f"{io.get('contract_coverage', 0)*100:.0f}%")) + "║")
        lines.append(f"║  • Input drifts: {io.get('input_drifts', 0)}" + " " * (39 - len(str(io.get('input_drifts', 0)))) + "║")
        lines.append(f"║  • Output drifts: {io.get('output_drifts', 0)}" + " " * (38 - len(str(io.get('output_drifts', 0)))) + "║")
        lines.append("║" + " " * 58 + "║")
        lines.append("║  DRIFT HOTSPOTS" + " " * 42 + "║")
        hotspots = report.get('hotspots', [])
        if hotspots:
            for spot in hotspots[:3]:
                path = spot.get('file_path', 'unknown')
                file_name = path.split('/')[-1][:25] if '/' in path else path[:25]
                count = spot.get('drift_event_count', 0)
                line = f"║  • {file_name:<25} ({count} events)"
                lines.append(line + " " * (59 - len(line)) + "║")
        else:
            lines.append("║  • None detected" + " " * 41 + "║")
        lines.append("║" + " " * 58 + "║")
        entropy = report.get('entropy_analysis', [])
        if entropy:
            lines.append("║  ENTROPY ANALYSIS" + " " * 40 + "║")
            for item in entropy[:3]:
                sym = item.get('symbol', 'unknown')[:15]
                ent = item.get('entropy', 0)
                interp = item.get('interpretation', 'unknown')
                line = f"║  • {sym:<15} entropy={ent:.2f} ({interp})"
                lines.append(line + " " * (59 - len(line)) + "║")
        lines.append("╚" + "═" * 58 + "╝")
        return '\n'.join(lines)

    @staticmethod
    def json_report(report: Dict[str, Any]) -> str:
        import json
        return json.dumps(report, indent=2, default=str)

    @staticmethod
    def csv_export(report: Dict[str, Any]) -> str:
        lines = ["symbol,file,drift_score"]
        for node in report.get('top_risk_nodes', []):
            lines.append(f"{node.get("name","")},{node.get("file","")},{node.get("drift_score",0)}")
        return '\n'.join(lines)