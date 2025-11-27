import logging
import time
import os
from datetime import datetime

from mesh_monitor.route_analyzer import RouteAnalyzer

logger = logging.getLogger(__name__)

class NetworkReporter:
    def __init__(self, report_dir="."):
        self.report_dir = report_dir

    def generate_report(self, nodes, test_results, analysis_issues, local_node=None):
        """
        Generates a Markdown report based on collected data.
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"report-{timestamp}.md"
        filepath = os.path.join(self.report_dir, filename)

        logger.info(f"Generating network report: {filepath}")

        # Run Route Analysis
        route_analyzer = RouteAnalyzer(nodes)
        route_analysis = route_analyzer.analyze_routes(test_results)

        try:
            with open(filepath, "w") as f:
                # Header
                f.write(f"# Meshtastic Network Report\n")
                f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

                # 1. Executive Summary
                self._write_executive_summary(f, nodes, test_results, analysis_issues)

                # 2. Network Health (Analysis Findings)
                self._write_network_health(f, analysis_issues)

                # 3. Route Analysis (New Section)
                self._write_route_analysis(f, route_analysis)

                # 4. Traceroute Results
                self._write_traceroute_results(f, test_results, nodes, local_node)

                # 5. Recommendations
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
        
        # Get unique nodes from test results (selected online nodes)
        unique_tested_nodes = len(set([r.get('node_id') for r in test_results]))
        
        f.write(f"- **Total Nodes Visible:** {total_nodes}\n")
        f.write(f"- **Selected Online Nodes:** {unique_tested_nodes}\n")
        f.write(f"- **Total Tests Performed:** {total_tests}\n")
        f.write(f"- **Test Success Rate:** {success_rate:.1f}%\n")
        f.write(f"- **Critical Issues Found:** {critical_issues}\n\n")

    def _write_route_analysis(self, f, analysis):
        f.write("## 3. Route Analysis\n")
        
        if not analysis:
            f.write("No route analysis data available (no successful traceroutes).\n\n")
            return

        # 3.1 Relay Usage
        f.write("### 3.1 Top Relays (Backbone Nodes)\n")
        relays = analysis.get('relay_usage', [])
        if relays:
            f.write("| Node ID | Name | Times Used as Relay |\n")
            f.write("|---|---|---|\n")
            for r in relays[:10]: # Top 10
                f.write(f"| `{r['id']}` | {r['name']} | {r['count']} |\n")
            f.write("\n")
        else:
            f.write("No intermediate relays detected in successful traceroutes.\n\n")

        # 3.2 Bottlenecks
        f.write("### 3.2 Potential Bottlenecks (High Centrality)\n")
        bottlenecks = analysis.get('bottlenecks', [])
        if bottlenecks:
            f.write("Nodes that appear in routes to multiple different destinations:\n\n")
            f.write("| Node ID | Name | Destinations Served |\n")
            f.write("|---|---|---|\n")
            for b in bottlenecks:
                f.write(f"| `{b['id']}` | {b['name']} | {b['destinations_served']} |\n")
            f.write("\n")
        else:
            f.write("No significant bottlenecks identified.\n\n")

        # 3.3 Common Paths
        f.write("### 3.3 Most Common Paths\n")
        paths = analysis.get('common_paths', {})
        if paths:
            f.write("| Destination | Most Common Path | Stability |\n")
            f.write("|---|---|---|\n")
            for dest, data in paths.items():
                stability = f"{data['stability']:.1f}%"
                path = data['path'].replace("->", "&rarr;")
                f.write(f"| `{dest}` | {path} | {stability} |\n")
            f.write("\n")
        else:
            f.write("No path data available.\n\n")

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

    def _write_traceroute_results(self, f, test_results, nodes, local_node=None):
        f.write("## 3. Traceroute Results\n")
        if not test_results:
            f.write("No active tests performed in this cycle.\n\n")
            return

        f.write("| Node ID | Name | Status | Distance (km) | RTT (s) | Hops (To/Back) | SNR |\n")
        f.write("|---|---|---|---|---|---|---|\n")

        def get_node_name(node_id):
            node = nodes.get(node_id)
            if node:
                user = node.get('user', {}) if isinstance(node, dict) else getattr(node, 'user', {})
                # Handle nested object/dict for user
                if hasattr(user, 'longName'): return user.longName
                if isinstance(user, dict): return user.get('longName', node_id)
            return node_id
        
        def get_distance(node_id):
            """Calculate distance from local node to target node in km."""
            import math
            
            if not local_node:
                return '-'
            
            # Get local node ID (localNode is a Node object, not in the nodes dict directly)
            # We need to find the local node in the nodes dict
            local_node_id = None
            if hasattr(local_node, 'nodeNum'):
                # Convert node number to hex ID format
                local_node_id = f"!{local_node.nodeNum:08x}"
            
            if not local_node_id:
                return '-'
            
            # Look up local node in nodes dict to get position
            local_node_data = nodes.get(local_node_id)
            if not local_node_data:
                return '-'
            
            # Get local position from nodes dict
            local_pos = local_node_data.get('position', {}) if isinstance(local_node_data, dict) else getattr(local_node_data, 'position', {})
            if isinstance(local_pos, dict):
                my_lat = local_pos.get('latitude')
                my_lon = local_pos.get('longitude')
            else:
                my_lat = getattr(local_pos, 'latitude', None)
                my_lon = getattr(local_pos, 'longitude', None)
            
            if my_lat is None or my_lon is None:
                return '-'
            
            # Get target node position
            node = nodes.get(node_id)
            if not node:
                return '-'
            
            target_pos = node.get('position', {}) if isinstance(node, dict) else getattr(node, 'position', {})
            if isinstance(target_pos, dict):
                target_lat = target_pos.get('latitude')
                target_lon = target_pos.get('longitude')
            else:
                target_lat = getattr(target_pos, 'latitude', None)
                target_lon = getattr(target_pos, 'longitude', None)
            
            if target_lat is None or target_lon is None:
                return '-'
            
            # Haversine formula
            try:
                lon1, lat1, lon2, lat2 = map(math.radians, [float(my_lon), float(my_lat), float(target_lon), float(target_lat)])
                dlon = lon2 - lon1 
                dlat = lat2 - lat1 
                a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
                c = 2 * math.asin(math.sqrt(a)) 
                km = c * 6371  # Earth radius in kilometers
                return f"{km:.2f}"
            except:
                return '-'

        for res in test_results:
            node_id = res.get('node_id')
            name = get_node_name(node_id)
            status = res.get('status', 'unknown')
            distance = get_distance(node_id)
            rtt = res.get('rtt', '-')
            hops_to = res.get('hops_to', '-')
            hops_back = res.get('hops_back', '-')
            snr = res.get('snr', '-')
            
            # Format RTT
            if isinstance(rtt, (int, float)):
                rtt = f"{rtt:.2f}"
            
            # Format hops
            if hops_to != '-' and hops_back != '-':
                hops = f"{hops_to}/{hops_back}"
            else:
                hops = '-'
            
            status_icon = "✅" if status == 'success' else "❌"
            
            f.write(f"| {node_id} | {name} | {status_icon} {status} | {distance} | {rtt} | {hops} | {snr} |\n")
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
