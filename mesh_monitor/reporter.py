import logging
import time
import os
from datetime import datetime
from .utils import get_val, haversine, get_node_name

from mesh_monitor.route_analyzer import RouteAnalyzer

logger = logging.getLogger(__name__)

class NetworkReporter:
    def __init__(self, report_dir="."):
        self.report_dir = report_dir

    def generate_report(self, nodes, test_results, analysis_issues, local_node=None, router_stats=None):
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
                self._write_executive_summary(f, nodes, test_results, analysis_issues, local_node)

                # 2. Network Health (Analysis Findings)
                self._write_network_health(f, analysis_issues)
                
                # 2.1 Router Performance Table (New)
                if router_stats:
                    self._write_router_performance_table(f, router_stats)

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

    def _write_executive_summary(self, f, nodes, test_results, analysis_issues, local_node=None):
        f.write("## 1. Executive Summary\n")
        
        total_nodes = len(nodes)
        total_tests = len(test_results)
        successful_tests = len([r for r in test_results if r.get('status') == 'success'])
        success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
        
        critical_issues = len([i for i in analysis_issues if "Critical" in i or "Congestion" in i])
        
        # Get unique nodes from test results (selected online nodes)
        unique_tested_nodes = len(set([r.get('node_id') for r in test_results]))
        
        # Get Local Position
        local_pos_str = "Unknown"
        if local_node:
            # Try to get ID to look up in nodes dict (which has the most up-to-date position including manual overrides)
            local_id = None
            if hasattr(local_node, 'nodeNum'):
                local_id = f"!{local_node.nodeNum:08x}"
            elif isinstance(local_node, dict):
                 # Try to find ID in dict
                 user = local_node.get('user', {})
                 if 'id' in user:
                     local_id = user['id']
            
            if local_id and local_id in nodes:
                pos = get_val(nodes[local_id], 'position', {})
                lat = get_val(pos, 'latitude')
                lon = get_val(pos, 'longitude')
                if lat is not None and lon is not None:
                    local_pos_str = f"{lat:.4f}, {lon:.4f}"
            
            # Fallback to local_node object if not found in dict or no ID
            if local_pos_str == "Unknown":
                 if hasattr(local_node, 'position'):
                     # Check if it's a dict or object
                     pos = local_node.position
                     if isinstance(pos, dict):
                         lat = pos.get('latitude')
                         lon = pos.get('longitude')
                     else:
                         lat = getattr(pos, 'latitude', None)
                         lon = getattr(pos, 'longitude', None)
                     
                     if lat is not None and lon is not None:
                         local_pos_str = f"{lat:.4f}, {lon:.4f}"

        f.write(f"- **Test Location:** {local_pos_str}\n")
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

        # Helper to clean issue strings (remove recommendations)
        def clean_issue(issue):
            # Topology: High Router Density
            if "Best positioned seems to be" in issue:
                return issue.split("Best positioned seems to be")[0].strip()
            if "Consider changing" in issue:
                return issue.split("Consider changing")[0].strip()
            
            # Network Size
            if "If using" in issue:
                return issue.split("If using")[0].strip()
            
            # Efficiency
            if "Consolidate?" in issue:
                return issue.split("Consolidate?")[0].strip()
                
            return issue

        # Group issues by type
        congestion = []
        config = []
        topology = []
        other = []

        for issue in analysis_issues:
            # Clean the issue string first
            cleaned_issue = clean_issue(issue)
            
            if "Congestion" in issue or "Spam" in issue:
                congestion.append(cleaned_issue)
            elif "Config" in issue or "Role" in issue:
                config.append(cleaned_issue)
            elif "Topology" in issue or "Density" in issue or "hops away" in issue:
                topology.append(cleaned_issue)
            elif "Efficiency" in issue or "Route Quality" in issue:
                pass # Handled in separate sections
            else:
                other.append(cleaned_issue)

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

        # Separate section for Efficiency
        efficiency = [clean_issue(i) for i in analysis_issues if "Efficiency" in i]
        if efficiency:
            f.write("### Router Efficiency Analysis\n")
            f.write("Analysis of router placement, congestion, and relay performance.\n\n")
            for i in efficiency:
                clean_msg = i.replace("Efficiency: ", "")
                f.write(f"- {clean_msg}\n")
            f.write("\n")

        # Separate section for Route Quality
        quality = [clean_issue(i) for i in analysis_issues if "Route Quality" in i]
        if quality:
            f.write("### Route Quality Analysis\n")
            f.write("Analysis of path efficiency and stability.\n\n")
            for i in quality:
                clean_msg = i.replace("Route Quality: ", "")
                f.write(f"- {clean_msg}\n")
            f.write("\n")

    def _write_router_performance_table(self, f, router_stats):
        f.write("### Router Performance Table\n")
        if not router_stats:
            f.write("No routers found.\n\n")
            return

        # Get radius from first stat entry (default to 2000m if missing)
        radius_m = router_stats[0].get('radius', 2000)
        radius_km = radius_m / 1000.0

        f.write(f"| Name | Role | Neighbors ({radius_km:.1f}km) | Routers ({radius_km:.1f}km) | ChUtil | Relayed | Status |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        
        for s in router_stats:
            # Handle backward compatibility if keys are missing
            neighbors = s.get('neighbors', s.get('neighbors_2km', 0))
            routers_nearby = s.get('routers_nearby', s.get('routers_2km', 0))
            
            f.write(f"| {s['name']} | {s['role']} | {neighbors} | {routers_nearby} | {s['ch_util']:.1f}% | {s['relay_count']} | {s['status']} |\n")
        f.write("\n")



    def _write_traceroute_results(self, f, test_results, nodes, local_node=None):
        f.write("## 3. Traceroute Results\n")
        if not test_results:
            f.write("No active tests performed in this cycle.\n\n")
            return

        f.write("| Node ID | Name | Status | Distance (km) | RTT (s) | Hops (To/Back) | SNR |\n")
        f.write("|---|---|---|---|---|---|---|\n")

        def get_distance(node_id):
            """Calculate distance from local node to target node in km."""
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
            local_pos = get_val(local_node_data, 'position', {})
            my_lat = get_val(local_pos, 'latitude')
            my_lon = get_val(local_pos, 'longitude')
            
            if my_lat is None or my_lon is None:
                return '-'
            
            # Get target node position
            node = nodes.get(node_id)
            if not node:
                return '-'
            
            target_pos = get_val(node, 'position', {})
            target_lat = get_val(target_pos, 'latitude')
            target_lon = get_val(target_pos, 'longitude')
            
            if target_lat is None or target_lon is None:
                return '-'
            
            # Haversine formula
            dist_meters = haversine(my_lat, my_lon, target_lat, target_lon)
            if dist_meters > 0:
                return f"{dist_meters/1000:.2f}"
            return '-'

        for res in test_results:
            node_id = res.get('node_id')
            node = nodes.get(node_id, {})
            name = get_node_name(node, node_id)
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
        
        # 1. Topology & Placement (Consolidated from Analysis)
        # Extract "Best positioned..." recommendations
        topology_recs = []
        for issue in analysis_issues:
            if "Topology: High Router Density!" in issue:
                # Extract the recommendation part
                if "Best positioned seems to be" in issue:
                    # Find where the recommendation starts
                    start_idx = issue.find("Best positioned seems to be")
                    if start_idx != -1:
                        topology_recs.append(f"- **Optimize Cluster:** {issue[start_idx:]}")
                else:
                    # Fallback if format is different
                    topology_recs.append(f"- **Optimize Placement:** {issue}")
            elif "Topology: Node" in issue and "hops away" in issue:
                 # "Topology: Node 'X' is 4 hops away."
                 topology_recs.append(f"- **Improve Coverage:** {issue.replace('Topology: ', '')}")

        if topology_recs:
            recs.extend(topology_recs)
        elif any("High Density" in i for i in analysis_issues):
             # Fallback for generic density issue if not caught above
             recs.append("- **Optimize Placement:** Routers are too close together. Convert redundant routers to clients.")

        # 2. Efficiency (Router Performance)
        if any("Ineffective" in i for i in analysis_issues):
            recs.append("- **Review Ineffective Routers:** Some routers have neighbors but aren't relaying packets. Consider repositioning them or checking their antenna/LOS.")
        
        if any("Redundant" in i for i in analysis_issues):
             # This might overlap with Topology, but good to have specific advice
             recs.append("- **Reduce Redundancy:** Routers marked as 'Redundant' have too many other routers nearby. Change their role to CLIENT to save airtime.")

        # 3. Congestion
        if any("Congestion" in i or "Congested" in i for i in analysis_issues):
            recs.append("- **Reduce Traffic:** High channel utilization detected. Identify spamming nodes, reduce broadcast frequency, or increase channel speed (if possible).")

        # 4. Configuration
        if any("ROUTER_CLIENT" in i for i in analysis_issues):
            recs.append("- **Fix Roles:** Deprecated `ROUTER_CLIENT` role detected. Change these nodes to `CLIENT` or `CLIENT_MUTE`.")
        
        if any("Network Size" in i for i in analysis_issues):
            recs.append("- **Adjust Presets:** Network size exceeds recommendations for the current estimated preset. Consider switching to a faster preset (e.g. LONG_MODERATE or SHORT_FAST).")

        # 5. Route Quality / Signal
        if any("poor SNR" in i or "Weak signal" in i for i in analysis_issues):
            recs.append("- **Check Hardware/LOS:** Nodes with poor SNR or weak signals may have antenna issues, bad placement, or obstructions.")
            
        if any("Long path" in i for i in analysis_issues):
            recs.append("- **Optimize Paths:** Long paths (>3 hops) detected. Consider adding a strategically placed relay to shorten the path.")
            
        if any("Favorite Router" in i for i in analysis_issues):
            recs.append("- **Check Favorites:** Routes are using 'Favorite Router' nodes. Ensure this is intentional, as it forces specific paths.")

        # 6. Connectivity (Traceroute Failures)
        failures = [r for r in test_results if r.get('status') != 'success']
        if failures:
            recs.append(f"- **Investigate Connectivity:** {len(failures)} nodes failed traceroute tests. Check if they are online or if the path is broken.")

        if not recs:
            f.write("Network looks healthy! Keep up the good work.\n")
        else:
            # Deduplicate recommendations
            unique_recs = sorted(list(set(recs)))
            for r in unique_recs:
                f.write(f"{r}\n")
        f.write("\n")
