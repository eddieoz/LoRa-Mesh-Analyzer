import unittest
import time
from mesh_analyzer.analyzer import NetworkHealthAnalyzer

class TestNetworkSize(unittest.TestCase):
    def setUp(self):
        # Config with small max nodes for testing
        self.config = {
            'max_nodes_for_long_fast': 5,
            'thresholds': {
                'active_threshold_seconds': 3600 # 1 hour
            }
        }
        self.analyzer = NetworkHealthAnalyzer(config=self.config)

    def test_active_nodes_warning(self):
        current_time = time.time()
        nodes = {}
        
        # Add 6 active nodes (should trigger warning since max is 5)
        for i in range(6):
            nodes[f'!active{i}'] = {'lastHeard': current_time - 100}
            
        # Add 10 inactive nodes (should be ignored)
        for i in range(10):
            nodes[f'!inactive{i}'] = {'lastHeard': current_time - 7200} # 2 hours ago
            
        issues = self.analyzer.check_network_size_and_preset(nodes)
        
        print("\nActive Nodes Warning Issues:", issues)
        
        # Should have a warning because 6 active > 5 max
        self.assertTrue(any("Network Size" in i for i in issues))
        self.assertTrue(any("6 active nodes" in i for i in issues))

    def test_no_warning_if_inactive(self):
        current_time = time.time()
        nodes = {}
        
        # Add 3 active nodes (under limit of 5)
        for i in range(3):
            nodes[f'!active{i}'] = {'lastHeard': current_time - 100}
            
        # Add 50 inactive nodes (total > 5, but active < 5)
        for i in range(50):
            nodes[f'!inactive{i}'] = {'lastHeard': current_time - 7200}
            
        issues = self.analyzer.check_network_size_and_preset(nodes)
        
        print("\nNo Warning Issues:", issues)
        
        # Should NOT have a warning
        self.assertFalse(any("Network Size" in i for i in issues))

if __name__ == '__main__':
    unittest.main()
