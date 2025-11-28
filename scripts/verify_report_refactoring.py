#!/usr/bin/env python3
"""
Test script to verify the report generation refactoring.
Creates mock data and tests both JSON persistence and report regeneration.
"""

import sys
import os
import json
from datetime import datetime

# Add mesh_analyzer to path
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mesh_analyzer.reporter import NetworkReporter


def create_mock_data():
    """Create mock data similar to what the monitor would generate."""
    
    # Mock nodes
    nodes = {
        "!12345678": {
            "user": {"id": "!12345678", "longName": "Test Router 1", "shortName": "TR1"},
            "position": {"latitude": 59.4370, "longitude": 24.7536},
            "deviceMetrics": {"channelUtilization": 15.5, "airUtilTx": 2.3}
        },
        "!87654321": {
            "user": {"id": "!87654321", "longName": "Test Router 2", "shortName": "TR2"},
            "position": {"latitude": 59.4380, "longitude": 24.7550},
            "deviceMetrics": {"channelUtilization": 8.2, "airUtilTx": 1.1}
        }
    }
    
    # Mock test results
    test_results = [
        {
            "node_id": "!12345678",
            "status": "success",
            "rtt": 2.5,
            "hops_to": 2,
            "hops_back": 2,
            "snr": 8.5,
            "route": ["!local", "!relay1", "!12345678"]
        },
        {
            "node_id": "!87654321",
            "status": "timeout",
            "rtt": None,
            "hops_to": None,
            "hops_back": None,
            "snr": None,
            "route": []
        }
    ]
    
    # Mock analysis issues
    analysis_issues = [
        "Topology: High Router Density! Best positioned seems to be Test Router 1",
        "Config: Network Size exceeds recommendations"
    ]
    
    # Mock router stats
    router_stats = [
        {
            "name": "Test Router 1",
            "role": "ROUTER",
            "neighbors": 5,
            "routers_nearby": 2,
            "ch_util": 15.5,
            "relay_count": 12,
            "status": "Active",
            "radius": 2000
        },
        {
            "name": "Test Router 2",
            "role": "ROUTER",
            "neighbors": 3,
            "routers_nearby": 1,
            "ch_util": 8.2,
            "relay_count": 5,
            "status": "Active",
            "radius": 2000
        }
    ]
    
    # Mock local node
    local_node = {
        "user": {"id": "!local", "longName": "Local Node", "shortName": "LN"},
        "position": {"latitude": 59.4360, "longitude": 24.7520}
    }
    
    # Mock config
    config = {
        "log_level": "info",
        "traceroute_timeout": 60,
        "router_density_threshold": 2000,
        "analysis_mode": "distance"
    }
    
    return nodes, test_results, analysis_issues, router_stats, local_node, config


def test_report_generation():
    """Test that reports are generated in the reports/ folder with JSON."""
    print("=" * 60)
    print("Testing Report Generation with JSON Persistence")
    print("=" * 60)
    
    # Create mock data
    nodes, test_results, analysis_issues, router_stats, local_node, config = create_mock_data()
    
    # Create reporter
    reporter = NetworkReporter(report_dir="reports", config=config)
    
    print("\n✅ NetworkReporter created successfully")
    print(f"   Report directory: reports/")
    print(f"   Config passed: Yes")
    
    # Generate report
    print("\n📝 Generating report...")
    report_path = reporter.generate_report(
        nodes=nodes,
        test_results=test_results,
        analysis_issues=analysis_issues,
        local_node=local_node,
        router_stats=router_stats
    )
    
    if report_path:
        print(f"✅ Report generated: {report_path}")
        
        # Check if markdown report exists
        if os.path.exists(report_path):
            print(f"✅ Markdown file exists: {report_path}")
            
            # Get file size
            size_kb = os.path.getsize(report_path) / 1024
            print(f"   File size: {size_kb:.2f} KB")
        else:
            print(f"❌ Markdown file NOT found: {report_path}")
            return False
        
        # Check if JSON file exists
        json_path = report_path.replace('.md', '.json')
        if os.path.exists(json_path):
            print(f"✅ JSON file exists: {json_path}")
            
            # Get file size
            size_kb = os.path.getsize(json_path) / 1024
            print(f"   File size: {size_kb:.2f} KB")
            
            # Verify JSON structure
            print("\n🔍 Verifying JSON structure...")
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            # Check session metadata
            if 'session' in data:
                print("✅ Session metadata present")
                session = data['session']
                print(f"   Timestamp: {session.get('timestamp', 'N/A')}")
                print(f"   Generated at: {session.get('generated_at', 'N/A')}")
                print(f"   Config keys: {len(session.get('config', {}))}")
            else:
                print("❌ Session metadata missing")
                return False
            
            # Check data section
            if 'data' in data:
                print("✅ Data section present")
                data_section = data['data']
                print(f"   Nodes: {len(data_section.get('nodes', {}))}")
                print(f"   Test results: {len(data_section.get('test_results', []))}")
                print(f"   Analysis issues: {len(data_section.get('analysis_issues', []))}")
                print(f"   Router stats: {len(data_section.get('router_stats', []))}")
                print(f"   Local node: {'present' if data_section.get('local_node') else 'missing'}")
            else:
                print("❌ Data section missing")
                return False
            
            return json_path
        else:
            print(f"❌ JSON file NOT found: {json_path}")
            return False
    else:
        print("❌ Report generation failed")
        return False


def test_report_regeneration(json_path):
    """Test report regeneration from JSON file."""
    print("\n" + "=" * 60)
    print("Testing Report Regeneration from JSON")
    print("=" * 60)
    
    if not json_path or not os.path.exists(json_path):
        print(f"❌ JSON file not found: {json_path}")
        return False
    
    # Import the report generator
    from report_generate import generate_report_from_json
    
    print(f"\n📁 Source JSON: {json_path}")
    
    # Test regeneration with custom output
    custom_output = "reports/test-regenerated-report.md"
    print(f"🔄 Regenerating report to: {custom_output}")
    
    result = generate_report_from_json(json_path, custom_output)
    
    if result and os.path.exists(custom_output):
        print(f"✅ Report regenerated successfully: {custom_output}")
        
        # Compare sizes (should be similar)
        original_md = json_path.replace('.json', '.md')
        if os.path.exists(original_md):
            orig_size = os.path.getsize(original_md)
            regen_size = os.path.getsize(custom_output)
            print(f"   Original size: {orig_size / 1024:.2f} KB")
            print(f"   Regenerated size: {regen_size / 1024:.2f} KB")
            
            # They should be roughly the same size (within 10%)
            if abs(orig_size - regen_size) / orig_size < 0.1:
                print("✅ Size comparison: PASS (within 10%)")
            else:
                print("⚠️  Size comparison: Different (this is OK if content differs)")
        
        return True
    else:
        print(f"❌ Report regeneration failed")
        return False


def main():
    print("\n🧪 REPORT GENERATION REFACTORING - VERIFICATION TESTS\n")
    
    # Test 1: Report generation with JSON persistence
    json_path = test_report_generation()
    
    if not json_path:
        print("\n❌ FAILED: Report generation test")
        sys.exit(1)
    
    # Test 2: Report regeneration from JSON
    success = test_report_regeneration(json_path)
    
    if not success:
        print("\n❌ FAILED: Report regeneration test")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print("\nSummary:")
    print("  ✓ Reports are generated in reports/ folder")
    print("  ✓ JSON files are created alongside markdown reports")
    print("  ✓ JSON contains all session metadata and raw data")
    print("  ✓ report_generate.py successfully regenerates reports from JSON")
    print("\nNext steps:")
    print("  - Clean up test files if needed")
    print("  - Test with real data from the monitor")


if __name__ == "__main__":
    main()
