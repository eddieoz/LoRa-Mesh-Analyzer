#!/usr/bin/env python3
"""
Report Generator Tool

Regenerates markdown reports from JSON data files saved by the LoRa Mesh Analyzer.

Usage:
    python report_generate.py <json_file_path> [--output <output_path>]

Example:
    python report_generate.py reports/report-20251128-145548.json
    python report_generate.py reports/report-20251128-145548.json --output custom-report.md
"""

import json
import sys
import os
import argparse
from datetime import datetime

# Add mesh_monitor to path
sys.path.insert(0, os.path.dirname(__file__))

from mesh_monitor.reporter import NetworkReporter
from mesh_monitor.route_analyzer import RouteAnalyzer


def load_json_data(json_filepath):
    """
    Load raw data from JSON file.
    """
    if not os.path.exists(json_filepath):
        print(f"Error: File not found: {json_filepath}")
        sys.exit(1)
    
    try:
        with open(json_filepath, 'r') as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading file: {e}")
        sys.exit(1)


def generate_report_from_json(json_filepath, output_path=None):
    """
    Regenerate markdown report from JSON data.
    """
    print(f"Loading data from: {json_filepath}")
    
    # Load the JSON data
    full_data = load_json_data(json_filepath)
    
    # Extract session and data
    session = full_data.get('session', {})
    data = full_data.get('data', {})
    
    # Extract all the components
    nodes = data.get('nodes', {})
    test_results = data.get('test_results', [])
    analysis_issues = data.get('analysis_issues', [])
    router_stats = data.get('router_stats', [])
    route_analysis = data.get('route_analysis', {})
    local_node = data.get('local_node')
    config = session.get('config', {})
    
    print(f"Session timestamp: {session.get('timestamp', 'Unknown')}")
    print(f"Nodes: {len(nodes)}")
    print(f"Test results: {len(test_results)}")
    print(f"Analysis issues: {len(analysis_issues)}")
    
    # Create a custom reporter that generates the file at the specified location
    if output_path:
        # Use the directory and filename from output_path
        report_dir = os.path.dirname(output_path) or "."
        filename_base = os.path.basename(output_path).replace('.md', '')
    else:
        # Generate new report in reports/ with regenerated timestamp
        report_dir = "reports"
        filename_base = None
    
    reporter = NetworkReporter(report_dir=report_dir, config=config)
    
    # Apply manual positions from config to nodes
    # This ensures that even if the JSON data lacks positions, we use the latest config
    manual_positions = config.get('manual_positions', {})
    if manual_positions:
        print(f"Applying {len(manual_positions)} manual positions from config...")
        for node_id, pos in manual_positions.items():
            if node_id in nodes:
                node = nodes[node_id]
                if 'position' not in node:
                    node['position'] = {}
                
                if 'lat' in pos and 'lon' in pos:
                    node['position']['latitude'] = pos['lat']
                    node['position']['longitude'] = pos['lon']
    
    # Recreate analyzer and re-run analysis to populate cluster_data and ch_util_data
    from mesh_monitor.analyzer import NetworkHealthAnalyzer
    analyzer = NetworkHealthAnalyzer(config=config)
    
    # Re-run analysis to populate analyzer data structures AND get new issues
    new_issues = analyzer.analyze(nodes, packet_history=[], my_node=local_node, test_results=test_results)
    
    # Run additional checks
    if test_results:
        new_issues.extend(analyzer.check_router_efficiency(nodes, test_results=test_results))
        new_issues.extend(analyzer.check_route_quality(nodes, test_results=test_results))
    
    # Use new issues for the report
    analysis_issues = new_issues
    
    # We need to temporarily override the filename generation if custom output is specified
    if output_path:
        # Monkey-patch the generate_report to use custom filename
        original_generate = reporter.generate_report
        
        def custom_generate(nodes, test_results, analysis_issues, local_node=None, router_stats=None, analyzer=None):
            # Temporarily change the method to use custom filename
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            custom_filename = os.path.basename(output_path)
            filepath = os.path.join(report_dir, custom_filename)
            
            from mesh_monitor.route_analyzer import RouteAnalyzer
            route_analyzer = RouteAnalyzer(nodes)
            route_analysis_local = route_analyzer.analyze_routes(test_results)
            
            try:
                with open(filepath, "w") as f:
                    f.write(f"# Meshtastic Network Report\n")
                    f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"**Regenerated from:** {os.path.basename(json_filepath)}\n\n")
                    
                    reporter._write_executive_summary(f, nodes, test_results, analysis_issues, local_node)
                    reporter._write_network_health(f, analysis_issues, analyzer)
                    
                    if router_stats:
                        reporter._write_router_performance_table(f, router_stats)
                    
                    reporter._write_route_analysis(f, route_analysis_local)
                    reporter._write_traceroute_results(f, test_results, nodes, local_node)
                    reporter._write_recommendations(f, analysis_issues, test_results, analyzer)
                
                print(f"✅ Report regenerated successfully: {filepath}")
                return filepath
            except Exception as e:
                print(f"❌ Failed to generate report: {e}")
                return None
        
        reporter.generate_report = custom_generate
    
    # Extract session metadata
    # Use the 'session' variable already extracted from 'full_data'
    original_timestamp = session.get('timestamp')
    test_location = session.get('test_location')
    
    # Generate the report
    result = reporter.generate_report(
        nodes=nodes,
        test_results=test_results,
        analysis_issues=analysis_issues,
        local_node=local_node,
        router_stats=router_stats,
        analyzer=analyzer,  # Pass analyzer parameter
        override_timestamp=original_timestamp,
        override_location=test_location,
        save_json=False # Do not overwrite JSON when regenerating
    )
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Regenerate markdown reports from JSON data files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python report_generate.py reports/report-20251128-145548.json
  python report_generate.py reports/report-20251128-145548.json --output custom-report.md
        """
    )
    
    parser.add_argument(
        'json_file',
        help='Path to the JSON data file'
    )
    
    parser.add_argument(
        '--output', '-o',
        help='Custom output path for the markdown report (optional)',
        default=None
    )
    
    args = parser.parse_args()
    
    # Generate the report
    generate_report_from_json(args.json_file, args.output)


if __name__ == "__main__":
    main()
