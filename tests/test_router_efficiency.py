import unittest
from mesh_monitor.analyzer import NetworkHealthAnalyzer

class TestRouterEfficiency(unittest.TestCase):
    def setUp(self):
        self.analyzer = NetworkHealthAnalyzer()

    def test_redundant_routers(self):
        # Create 3 routers very close to each other
        nodes = {
            '!11111111': {
                'user': {'id': '!11111111', 'longName': 'Router1', 'role': 'ROUTER'},
                'position': {'latitude': 40.0, 'longitude': -74.0},
                'deviceMetrics': {'channelUtilization': 10}
            },
            '!22222222': {
                'user': {'id': '!22222222', 'longName': 'Router2', 'role': 'ROUTER'},
                'position': {'latitude': 40.001, 'longitude': -74.001}, # Very close
                'deviceMetrics': {'channelUtilization': 10}
            },
            '!33333333': {
                'user': {'id': '!33333333', 'longName': 'Router3', 'role': 'ROUTER'},
                'position': {'latitude': 40.002, 'longitude': -74.002}, # Very close
                'deviceMetrics': {'channelUtilization': 10}
            }
        }
        
        issues = self.analyzer.check_router_efficiency(nodes)
        print("\nRedundancy Issues:", issues)
        
        # All 3 should be flagged as redundant (each has 2 neighbors)
        self.assertTrue(any("Router1" in i and "Redundant" in i for i in issues))
        self.assertTrue(any("Router2" in i and "Redundant" in i for i in issues))
        self.assertTrue(any("Router3" in i and "Redundant" in i for i in issues))

    def test_congested_router(self):
        nodes = {
            '!44444444': {
                'user': {'id': '!44444444', 'longName': 'BusyRouter', 'role': 'ROUTER'},
                'position': {'latitude': 41.0, 'longitude': -75.0},
                'deviceMetrics': {'channelUtilization': 50} # High Util
            }
        }
        
        issues = self.analyzer.check_router_efficiency(nodes)
        print("\nCongestion Issues:", issues)
        self.assertTrue(any("BusyRouter" in i and "Congested" in i for i in issues))

    def test_ineffective_router(self):
        # Router surrounded by many nodes but not relaying
        nodes = {
            '!55555555': {
                'user': {'id': '!55555555', 'longName': 'LazyRouter', 'role': 'ROUTER'},
                'position': {'latitude': 42.0, 'longitude': -76.0},
                'deviceMetrics': {'channelUtilization': 5}
            }
        }
        
        # Add 6 neighbors
        for i in range(6):
            nodes[f'!neighbor{i}'] = {
                'user': {'id': f'!neighbor{i}', 'role': 'CLIENT'},
                'position': {'latitude': 42.001, 'longitude': -76.001}
            }
            
        # Test results showing NO relaying by LazyRouter
        test_results = [
            {'node_id': '!neighbor0', 'route': [12345, 67890]} # Random IDs, not LazyRouter
        ]
        
        issues = self.analyzer.check_router_efficiency(nodes, test_results)
        print("\nIneffective Issues:", issues)
        self.assertTrue(any("LazyRouter" in i and "Ineffective" in i for i in issues))

    def test_effective_router(self):
        # Router surrounded by nodes AND relaying
        nodes = {
            '!66666666': {
                'user': {'id': '!66666666', 'longName': 'GoodRouter', 'role': 'ROUTER'},
                'position': {'latitude': 43.0, 'longitude': -77.0},
                'deviceMetrics': {'channelUtilization': 5}
            }
        }
        
        # Add 6 neighbors
        for i in range(6):
            nodes[f'!neighbor{i}'] = {
                'user': {'id': f'!neighbor{i}', 'role': 'CLIENT'},
                'position': {'latitude': 43.001, 'longitude': -77.001}
            }
            
        # Test results showing relaying by GoodRouter (ID !66666666 -> 0x66666666)
        # 0x66666666 = 1717986918
        test_results = [
            {'node_id': '!neighbor0', 'route': [1717986918]} 
        ]
        
        issues = self.analyzer.check_router_efficiency(nodes, test_results)
        print("\nEffective Issues (Should be empty):", issues)
        self.assertFalse(any("GoodRouter" in i for i in issues))

    def test_get_router_stats(self):
        nodes = {
            '!77777777': {
                'user': {'id': '!77777777', 'longName': 'StatsRouter', 'role': 'ROUTER'},
                'position': {'latitude': 44.0, 'longitude': -78.0},
                'deviceMetrics': {'channelUtilization': 25}
            }
        }
        # Add 3 router neighbors
        for i in range(3):
            nodes[f'!r_neighbor{i}'] = {
                'user': {'id': f'!r_neighbor{i}', 'role': 'ROUTER'},
                'position': {'latitude': 44.001, 'longitude': -78.001}
            }
        
        """Test that get_router_stats returns correct structure and calculations."""
        # Create a mock route where StatsRouter (!77777777) is used as a relay
        # 0x77777777 = 2004318071
        test_results = [
            {'route': [2004318071], 'status': 'success'} 
        ]
        
        stats = self.analyzer.get_router_stats(nodes, test_results)
        print("\nRouter Stats:", stats)
        
        self.assertEqual(len(stats), 4) # StatsRouter + 3 neighbors
        
        target = next(s for s in stats if s['id'] == '!77777777')
        self.assertEqual(target['neighbors'], 3)
        self.assertEqual(target['routers_nearby'], 3)
        self.assertEqual(target['ch_util'], 25.0)
        self.assertEqual(target['relay_count'], 1) # Should be 1 now
        self.assertIn('Redundant', target['status'])
        self.assertIn('Congested', target['status'])

if __name__ == '__main__':
    unittest.main()
