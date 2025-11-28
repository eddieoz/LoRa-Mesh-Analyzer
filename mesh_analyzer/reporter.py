import logging
import time
import os
import json
from datetime import datetime
from .utils import get_val, haversine, get_node_name

from mesh_analyzer.route_analyzer import RouteAnalyzer

import io
import markdown

logger = logging.getLogger(__name__)

class NetworkReporter:
    def __init__(self, report_dir="reports", config=None):
        self.report_dir = report_dir
        self.config = config or {}
        
        # Ensure report directory exists
        os.makedirs(self.report_dir, exist_ok=True)

    def generate_report(self, nodes: dict, test_results: list, analysis_issues: list, local_node: dict = None, router_stats: list = None, analyzer: object = None, override_timestamp: str = None, override_location: str = None, save_json: bool = True, output_filename: str = None) -> str:
        """
        Generates a Markdown and/or HTML report based on collected data.
        Also persists all raw data to JSON format.
        
        Args:
            nodes: Dictionary of nodes
            test_results: List of test results
            analysis_issues: List of analysis issue strings
            local_node: Local node information
            router_stats: Router statistics
            analyzer: NetworkHealthAnalyzer instance with cluster_data and ch_util_data
            override_timestamp: Optional timestamp string to use (for regeneration)
            override_location: Optional location string to use (for regeneration)
            save_json: Whether to save the raw data to JSON (default: True)
            output_filename: Optional custom filename for the report (without extension)
        """
        if override_timestamp:
            timestamp = override_timestamp
            report_date = datetime.strptime(timestamp, "%Y%m%d-%H%M%S").strftime('%Y-%m-%d %H:%M:%S')
        else:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            report_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Determine base filename
        if output_filename:
            base_name = output_filename.replace('.md', '').replace('.html', '')
        else:
            base_name = f"report-{timestamp}"
            
        json_filename = f"{base_name}.json"
        json_filepath = os.path.join(self.report_dir, json_filename)

        logger.info(f"Generating network report: {base_name}")

        # Run Route Analysis
        route_analyzer = RouteAnalyzer(nodes)
        route_analysis = route_analyzer.analyze_routes(test_results)

        try:
            # --- Generate Report Content ---
            # We build the markdown content in memory first
            f = io.StringIO()
            
            # Header
            f.write(f"# Meshtastic Network Report\n")
            f.write(f"**Date:** {report_date}\n\n")

            # Calculate location if not overridden
            if override_location:
                test_location = override_location
            else:
                test_location = self._get_location_string(nodes, local_node)

            # 1. Executive Summary
            self._write_executive_summary(f, nodes, test_results, analysis_issues, test_location)

            # 2. Network Health (Analysis Findings)
            self._write_network_health(f, analysis_issues, analyzer)
            
            # 2.1 Router Performance Table (New)
            if router_stats:
                self._write_router_performance_table(f, router_stats)

            # 3. Route Analysis (New Section)
            self._write_route_analysis(f, route_analysis)

            # 4. Traceroute Results
            self._write_traceroute_results(f, test_results, nodes, local_node)

            # 5. Recommendations
            self._write_recommendations(f, analysis_issues, test_results, analyzer)
            
            # Get the full markdown content
            markdown_content = f.getvalue()
            f.close()

            # --- Output to Files ---
            output_formats = self.config.get('report_output_formats', ['markdown'])
            generated_files = []

            # 1. Markdown Output
            if 'markdown' in output_formats:
                md_filepath = os.path.join(self.report_dir, f"{base_name}.md")
                with open(md_filepath, "w") as md_file:
                    md_file.write(markdown_content)
                generated_files.append(md_filepath)
                logger.info(f"Report generated: {md_filepath}")

            # 2. HTML Output
            if 'html' in output_formats:
                html_filepath = os.path.join(self.report_dir, f"{base_name}.html")
                
                # Basic CSS for better readability
                css = """
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max_width: 960px; margin: 0 auto; padding: 20px; }
                    h1, h2, h3 { color: #2c3e50; margin-top: 1.5em; }
                    h1 { border-bottom: 2px solid #eee; padding-bottom: 10px; }
                    h2 { border-bottom: 1px solid #eee; padding-bottom: 5px; }
                    table { border-collapse: collapse; width: 100%; margin: 20px 0; }
                    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                    th { background-color: #f8f9fa; font-weight: bold; }
                    tr:nth-child(even) { background-color: #f9f9f9; }
                    code { background-color: #f5f5f5; padding: 2px 4px; border-radius: 3px; font-family: monospace; }
                    ul { padding-left: 20px; }
                    li { margin-bottom: 5px; }
                </style>
                """
                
                html_content = markdown.markdown(markdown_content, extensions=['tables', 'fenced_code'])
                full_html = f"<!DOCTYPE html>\n<html>\n<head>\n<meta charset='utf-8'>\n<title>Meshtastic Network Report - {report_date}</title>\n{css}\n</head>\n<body>\n{html_content}\n</body>\n</html>"
                
                with open(html_filepath, "w") as html_file:
                    html_file.write(full_html)
                generated_files.append(html_filepath)
                logger.info(f"Report generated: {html_filepath}")
            
            # --- Persist Raw Data to JSON ---
            if save_json:
                try:
                    self._save_json_data(
                        json_filepath,
                        timestamp,
                        nodes,
                        test_results,
                        analysis_issues,
                        local_node,
                        router_stats,
                        route_analysis,
                        test_location
                    )
                    logger.info(f"Raw data saved to: {json_filepath}")
                except Exception as json_e:
                    logger.error(f"Failed to save JSON data: {json_e}")
            
            # Return the primary file path (prefer markdown if available, else first generated)
            if generated_files:
                return generated_files[0]
            return None
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            return None

    def _serialize_object(self, obj, visited=None):
        """
        Recursively convert objects to JSON-serializable format.
        Handles protobuf objects, custom classes, and nested structures.
        Prevents infinite recursion from circular references.
        """
        if visited is None:
            visited = set()
        
        # Check for None and primitives first (before id check)
        if obj is None:
            return None
        elif isinstance(obj, (str, int, float, bool)):
            return obj
        
        # Check for circular references using object id
        obj_id = id(obj)
        if obj_id in visited:
            # Return a placeholder for circular references
            return "<circular reference>"
        
        # Mark this object as visited
        visited.add(obj_id)
        
        try:
            if isinstance(obj, (list, tuple)):
                return [self._serialize_object(item, visited) for item in obj]
            elif isinstance(obj, dict):
                return {key: self._serialize_object(value, visited) for key, value in obj.items()}
            elif hasattr(obj, '__dict__'):
                # Convert objects with __dict__ to dictionary
                return self._serialize_object(obj.__dict__, visited)
            else:
                # Fallback: convert to string
                return str(obj)
        finally:
            # Remove from visited set when done processing this branch
            visited.discard(obj_id)

    def _save_json_data(self, filepath, timestamp, nodes, test_results, analysis_issues, 
                        local_node, router_stats, route_analysis, test_location):
        """
        Saves all raw data to JSON file with session metadata.
        """
        # Serialize local_node
        local_node_data = None
        if local_node:
            if hasattr(local_node, '__dict__'):
                local_node_data = self._serialize_object(local_node)
            elif isinstance(local_node, dict):
                local_node_data = self._serialize_object(local_node)
            else:
                local_node_data = str(local_node)
        
        # Build the JSON structure
        data = {
            "session": {
                "timestamp": timestamp,
                "generated_at": datetime.now().isoformat(),
                "test_location": test_location,
                "config": self._serialize_object(self.config)
            },
            "data": {
                "nodes": self._serialize_object(nodes),
                "test_results": self._serialize_object(test_results),
                "analysis_issues": analysis_issues,  # Already a list of strings
                "router_stats": self._serialize_object(router_stats),
                "route_analysis": self._serialize_object(route_analysis),
                "local_node": local_node_data
            }
        }
        
        # Write to file with pretty formatting
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def _get_location_string(self, nodes, local_node):
        """
        Determines the location string for the report.
        """
        local_pos_str = "Unknown"
        if local_node:
            # Try to get ID to look up in nodes dict (which has the most up-to-date position including manual overrides)
            local_id = None
            if hasattr(local_node, 'nodeNum'):
                local_id = f"!{local_node.nodeNum:08x}"
            elif isinstance(local_node, dict):
                 # Try to find ID in dict
                 if 'nodeNum' in local_node:
                     try:
                         local_id = f"!{int(local_node['nodeNum']):08x}"
                     except:
                         pass
                 
                 if not local_id:
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
                 if isinstance(local_node, dict):
                     pos = local_node.get('position', {})
                     lat = pos.get('latitude')
                     lon = pos.get('longitude')
                     if lat is not None and lon is not None:
                         local_pos_str = f"{lat:.4f}, {lon:.4f}"
                 elif hasattr(local_node, 'position'):
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
        return local_pos_str

    def _write_executive_summary(self, f, nodes, test_results, analysis_issues, test_location="Unknown"):
        f.write("## 1. Executive Summary\n")
        
        total_nodes = len(nodes)
        total_tests = len(test_results)
        successful_tests = len([r for r in test_results if r.get('status') == 'success'])
        success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
        
        critical_issues = len([i for i in analysis_issues if "Critical" in i or "Congestion" in i])
        
        # Get unique nodes from test results (selected online nodes)
        unique_tested_nodes = len(set([r.get('node_id') for r in test_results]))
        
        f.write(f"- **Test Location:** {test_location}\n")
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

    def _write_network_health(self, f, analysis_issues, analyzer=None):
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
            
            # Add detailed cluster distance information
            if analyzer and hasattr(analyzer, 'cluster_data') and analyzer.cluster_data:
                f.write("\n**Router Cluster Details:**\n\n")
                for cluster in analyzer.cluster_data:
                    f.write(f"**Cluster of {cluster['size']} routers:**\n")
                    f.write(f"  - Best positioned: {cluster['best_router']} ({cluster['best_router_relays']} relays)\n")
                    f.write(f"  - Distances:\n")
                    for dist_info in cluster['distances']:
                        f.write(f"    - {dist_info['router1']} ↔ {dist_info['router2']}: {dist_info['distance_m']/1000:.2f}km\n")
                    f.write("\n")
            
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

        # Get cluster_radius and router_density_threshold from config
        cluster_radius_m = self.config.get('cluster_radius', 3000)
        router_density_m = self.config.get('thresholds', {}).get('router_density_threshold', 2000)
        
        cluster_radius_km = cluster_radius_m / 1000.0
        router_density_km = router_density_m / 1000.0

        f.write(f"| Name | Role | Neighbors ({cluster_radius_km:.1f}km) | Routers ({router_density_km:.1f}km) | ChUtil | Relayed | Status |\n")
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

    def _write_recommendations(self, f, analysis_issues, test_results, analyzer=None):
        f.write("## 4. Recommendations\n")
        
        recs = []  # Format: (priority, emoji, text)
        
        # === CRITICAL PRIORITY ===
        
        # 1.  Router Clusters <500m
        for issue in analysis_issues:
            if "Topology: High Router Density!" in issue:
                # Extract the recommendation part
                if analyzer and hasattr(analyzer, 'cluster_data') and analyzer.cluster_data:
                    # Get threshold from config (default to 2000m if not available)
                    threshold = self.config.get('thresholds', {}).get('router_density_threshold', 2000)
                    
                    for cluster in analyzer.cluster_data:
                        # Check if any distance is less than threshold (CRITICAL)
                        min_distance = min((d['distance_m'] for d in cluster['distances']), default=threshold)
                        has_close_routers = min_distance < threshold
                        
                        if has_close_routers:
                            rec = f"**Router Cluster:** {cluster['size']} routers within {threshold/1000:.1f}km threshold (closest: {min_distance/1000:.2f}km). "
                            rec += f"Best positioned: '{cluster['best_router']}' ({cluster['best_router_relays']} relays). "
                            rec += f"Consider changing others ({', '.join(cluster['other_routers'])}) to CLIENT role."
                            recs.append((1, "🔴", rec))
                        else:
                            rec = f"**Router Cluster:** {cluster['size']} routers detected. "
                            rec += f"Best positioned: '{cluster['best_router']}' ({cluster['best_router_relays']} relays). "
                            rec += f"Review if all routers are needed: {', '.join(cluster['other_routers'])}."
                            recs.append((2, "🟡", rec))
                else:
                    # Fallback if no analyzer data
                    rec = "**Optimize Placement:** Routers are too close together. Convert redundant routers to clients."
                    recs.append((1, "🔴", rec))
        
        # 2. Channel Utilization (Mesh-Wide or Isolated)
        if analyzer and hasattr(analyzer, 'ch_util_data') and analyzer.ch_util_data['type'] != 'none':
            ch_data = analyzer.ch_util_data
            if ch_data['type'] == 'widespread':
                # CRITICAL: Mesh-wide congestion
                rec = f"**Mesh-Wide Congestion:** {ch_data['affected_count']} out of {ch_data['active_count']} active nodes have high channel utilization (>{self.config.get('thresholds', {}).get('channel_utilization', 25)}%). "
                rec += "Consider switching to a faster Meshtastic preset (e.g., LONG_FAST → MEDIUM_FAST or SHORT_FAST). "
                rec += "Note: Faster presets increase throughput but reduce range. Choose based on your deployment area."
                recs.append((1, "🔴", rec))
            else:
                # WARNING: Isolated congestion
                rec = "**High Channel Utilization** on specific nodes:\n"
                for node in ch_data['nodes'][:5]:  # Top 5
                    rec += f"\n  - {node['name']}: {node['util_pct']:.1f}%"
                rec += "\n\nCheck these nodes for message spamming or reduce their broadcast frequency."
                recs.append((2, "🟡", rec))
        elif any("Congestion" in i or "Congested" in i for i in analysis_issues):
            # Fallback if no analyzer data
            recs.append((2, "🟡", "**Reduce Traffic:** High channel utilization detected. Identify spamming nodes, reduce broadcast frequency, or optimize network preset."))
        
        # 3. Ineffective Routers (clients relaying more than routers)
        ineffective_issues = [i for i in analysis_issues if "Router may be ineffective" in i]
        if ineffective_issues:
            for issue in ineffective_issues:
                # Parse the issue to extract router name and ChUtil
                import re
                router_match = re.search(r"Router '([^']+)' has (\d+) relays", issue)
                ch_util_match = re.search(r"Router ChUtil: ([\d.]+)%", issue)
                client_match = re.search(r"client '([^']+)' \([^)]+\) has (\d+) relays", issue)
                
                if router_match and ch_util_match and client_match:
                    router_name = router_match.group(1)
                    router_relays = int(router_match.group(2))
                    router_ch_util = float(ch_util_match.group(1))
                    client_name = client_match.group(1)
                    client_relays = int(client_match.group(2))
                    
                    # Detect mesh-clogging scenario: low relays + high ChUtil
                    ch_util_threshold = self.config.get('thresholds', {}).get('channel_utilization', 25.0)
                    is_mesh_clogger = (router_relays < client_relays / 2) and (router_ch_util > ch_util_threshold)
                    
                    if is_mesh_clogger:
                        # CRITICAL: Router is clogging the mesh
                        rec = f"**Mesh-Clogger Router:** '{router_name}' has high channel utilization ({router_ch_util:.1f}%) but low relay activity ({router_relays} relays), "
                        rec += f"while nearby client '{client_name}' is doing more work ({client_relays} relays). "
                        rec += f"This router is likely clogging the mesh. **Strongly recommend changing '{router_name}' to CLIENT role**."
                        recs.append((1, "🔴", rec))
                    else:
                        # WARNING: Ineffective but not clogging -> Now CRITICAL as per user request
                        rec = f"**Ineffective Router:** '{router_name}' has {router_relays} relays (ChUtil: {router_ch_util:.1f}%), "
                        rec += f"but nearby client '{client_name}' has {client_relays} relays. "
                        rec += f"Consider changing '{router_name}' to CLIENT role or check its antenna/placement."
                        recs.append((1, "🔴", rec))
                else:
                    # Fallback if parsing fails
                    rec = issue.replace("Efficiency: ", "").replace("Router may be ineffective - check antenna, placement, or configuration.", "Consider changing the router to CLIENT role or check its antenna/placement/configuration.")
                    recs.append((1, "🔴", rec))
        
        # === WARNING PRIORITY ===
        
        # 4. Long Paths
        if any("Long path" in i for i in analysis_issues):
            recs.append((2, "🟡", "**Optimize Paths:** Long paths (>3 hops) detected. Consider adding a strategically placed relay to shorten the path."))
        
        # 5. Redundant Routers (not close <500m but still redundant)
        if any("Redundant" in i for i in analysis_issues):
            recs.append((2, "🟡", "**Reduce Redundancy:** Some routers have too many other routers nearby. Evaluate if all are necessary and consider changing some to CLIENT role to save airtime."))
        
        # === INFO PRIORITY ===
        
        # 6. Configuration
        if any("ROUTER_CLIENT" in i for i in analysis_issues):
            recs.append((3, "🟢", "**Fix Roles:** Deprecated `ROUTER_CLIENT` role detected. Change these nodes to `CLIENT` or `CLIENT_MUTE`."))
        
        if any("Network Size" in i for i in analysis_issues):
            recs.append((3, "🟢", "**Adjust Presets:** Network size exceeds recommendations for LONG_FAST preset. Consider switching to a faster preset (e.g., LONG_MODERATE or SHORT_FAST) to reduce collision probability."))
        
        # 7. Signal Quality
        if any("poor SNR" in i or "Weak signal" in i for i in analysis_issues):
            recs.append((3, "🟢", "**Check Hardware/LOS:** Nodes with poor SNR or weak signals may have antenna issues, bad placement, or obstructions."))
        
        if any("Favorite Router" in i for i in analysis_issues):
            recs.append((3, "🟢", "**Check Favorites:** Routes are using 'Favorite Router' nodes. Ensure this is intentional, as it forces specific paths."))
        
        # 8. Connectivity
        failures = [r for r in test_results if r.get('status') != 'success']
        if failures:
            recs.append((3, "🟢", f"**Investigate Connectivity:** {len(failures)} nodes failed traceroute tests. Check if they are online or if the path is broken."))
        
        # Sort by priority (1=CRITICAL first)
        recs.sort(key=lambda x: x[0])
        
        if not recs:
            f.write("Network looks healthy! Keep up the good work.\n")
        else:
            for priority, emoji, rec_text in recs:
                f.write(f"{emoji} {rec_text}\n\n")
        
        f.write("\n")


