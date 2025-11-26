import logging
import time
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class NetworkReporter:
    def __init__(self, report_dir="."):
        self.report_dir = report_dir

    def generate_report(self, nodes, test_results, analysis_issues):
        """
        Generates a Markdown report based on collected data.
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"report-{timestamp}.md"
        filepath = os.path.join(self.report_dir, filename)

        logger.info(f"Generating network report: {filepath}")

        try:
            with open(filepath, "w") as f:
                # Header
                f.write(f"# Meshtastic Network Report\n")
                f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

                # 1. Executive Summary
                self._write_executive_summary(f, nodes, test_results, analysis_issues)

                # 2. Network Health (Analysis Findings)
                self._write_network_health(f, analysis_issues)

                # 3. Traceroute Results
                self._write_traceroute_results(f, test_results, nodes)

                # 4. Recommendations
                self._write_recommendations(f, analysis_issues, test_results)

            logger.info(f"Report generated successfully: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            return None

    def _write_executive_summary(self, f, nodes, test_results, analysis_issues):
        f.write("## 1. Executive Summary\n")
        
        total_nodes = len(nodes)
        total_tests = len(test_results)
        successful_tests = len([r for r in test_results if r.get('status') == 'success'])
        success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
        
        critical_issues = len([i for i in analysis_issues if "Critical" in i or "Congestion" in i])
        
        f.write(f"- **Total Nodes Visible:** {total_nodes}\n")
        f.write(f"- **Nodes Tested:** {total_tests}\n")
        f.write(f"- **Test Success Rate:** {success_rate:.1f}%\n")
        f.write(f"- **Critical Issues Found:** {critical_issues}\n\n")

    def _write_network_health(self, f, analysis_issues):
        f.write("## 2. Network Health Analysis\n")
        if not analysis_issues:
            f.write("No significant network issues detected.\n\n")
            return

        # Group issues by type
        congestion = []
        config = []
        topology = []
        other = []

        for issue in analysis_issues:
            if "Congestion" in issue or "Spam" in issue:
                congestion.append(issue)
            elif "Config" in issue or "Role" in issue:
                config.append(issue)
            elif "Topology" in issue or "Density" in issue or "hops away" in issue:
                topology.append(issue)
            else:
                other.append(issue)

        if congestion:
            f.write("### Congestion & Airtime\n")
            for i in congestion: f.write(f"- {i}\n")
            f.write("\n")
        
        if config:
            f.write("### Configuration Issues\n")
            for i in config: f.write(f"- {i}\n")
            f.write("\n")

        if topology:
            f.write("### Topology & Placement\n")
            for i in topology: f.write(f"- {i}\n")
            f.write("\n")

        if other:
            f.write("### Other Findings\n")
            for i in other: f.write(f"- {i}\n")
            f.write("\n")

    def _write_traceroute_results(self, f, test_results, nodes):
        f.write("## 3. Traceroute Results\n")
        if not test_results:
            f.write("No active tests performed in this cycle.\n\n")
            return

        f.write("| Node ID | Name | Status | RTT (s) | Hops | SNR |\n")
        f.write("|---|---|---|---|---|---|\n")

        def get_node_name(node_id):
            node = nodes.get(node_id)
            if node:
                user = node.get('user', {}) if isinstance(node, dict) else getattr(node, 'user', {})
                # Handle nested object/dict for user
                if hasattr(user, 'longName'): return user.longName
                if isinstance(user, dict): return user.get('longName', node_id)
            return node_id

        for res in test_results:
            node_id = res.get('node_id')
            name = get_node_name(node_id)
            status = res.get('status', 'unknown')
            rtt = res.get('rtt', '-')
            hops = res.get('hops', '-')
            snr = res.get('snr', '-')
            
            # Format RTT
            if isinstance(rtt, (int, float)):
                rtt = f"{rtt:.2f}"
            
            status_icon = "✅" if status == 'success' else "❌"
            
            f.write(f"| {node_id} | {name} | {status_icon} {status} | {rtt} | {hops} | {snr} |\n")
        f.write("\n")

    def _write_recommendations(self, f, analysis_issues, test_results):
        f.write("## 4. Recommendations\n")
        
        recs = []
        
        # Analyze issues for recommendations
        if any("Congestion" in i for i in analysis_issues):
            recs.append("- **Reduce Traffic:** High channel utilization detected. Identify spamming nodes or reduce broadcast frequency.")
        
        if any("ROUTER_CLIENT" in i for i in analysis_issues):
            recs.append("- **Fix Roles:** Deprecated `ROUTER_CLIENT` role detected. Change these nodes to `CLIENT` or `CLIENT_MUTE`.")
            
        if any("High Density" in i for i in analysis_issues):
            recs.append("- **Optimize Placement:** Routers are too close together. Convert redundant routers to clients to reduce noise.")
            
        if any("poor SNR" in i for i in analysis_issues):
            recs.append("- **Check Hardware:** Nodes with poor SNR at close range may have antenna issues or bad placement.")

        # Analyze test results
        failures = [r for r in test_results if r.get('status') != 'success']
        if failures:
            recs.append(f"- **Investigate Connectivity:** {len(failures)} nodes failed traceroute tests. Check if they are online or if the path is broken.")

        if not recs:
            f.write("Network looks healthy! Keep up the good work.\n")
        else:
            for r in recs:
                f.write(f"{r}\n")
        f.write("\n")
