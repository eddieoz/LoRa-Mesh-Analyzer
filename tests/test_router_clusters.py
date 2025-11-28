import unittest
from unittest.mock import MagicMock
from mesh_analyzer.active_tests import ActiveTester

class TestRouterClusters(unittest.TestCase):
    def setUp(self):
        self.mock_interface = MagicMock()
        self.tester = ActiveTester(
            self.mock_interface,
            analysis_mode='router_clusters',
            cluster_radius=2000,
            auto_discovery_limit=5
        )

    def test_router_identification(self):
        # Setup nodes: 1 Router, 1 Client
        self.mock_interface.nodes = {
            '!router1': {
                'user': {'role': 'ROUTER'},
                'position': {'latitude': 10.0, 'longitude': 10.0},
                'lastHeard': 100
            },
            '!client1': {
                'user': {'role': 'CLIENT'},
                'position': {'latitude': 10.0, 'longitude': 10.0},
                'lastHeard': 100
            }
        }
        
        # We need to mock _get_router_cluster_nodes to NOT be called automatically if we were testing run_next_test
        # But here we are testing _get_router_cluster_nodes directly
        
        # This test just verifies the logic inside _get_router_cluster_nodes
        # It doesn't really test "identification" in isolation because the method does everything.
        # Let's test the whole flow.
        
        selected = self.tester._get_router_cluster_nodes()
        # Client1 is at same location as Router1, so dist is 0 < 2000
        self.assertIn('!client1', selected)
        # Router1 is excluded from its own neighbor list? 
        # The logic says: if node_id == r['id']: continue
        # So Router1 should NOT be in the list unless it's near ANOTHER router.
        self.assertNotIn('!router1', selected)

    def test_radius_check(self):
        # Router at (0,0)
        # Client1 at (0.01, 0) ~ 1.1km (Inside 2km)
        # Client2 at (0.03, 0) ~ 3.3km (Outside 2km)
        self.mock_interface.nodes = {
            '!router1': {
                'user': {'role': 'ROUTER'},
                'position': {'latitude': 0.0, 'longitude': 0.0},
                'lastHeard': 100
            },
            '!client1': {
                'user': {'role': 'CLIENT'},
                'position': {'latitude': 0.01, 'longitude': 0.0},
                'lastHeard': 100
            },
            '!client2': {
                'user': {'role': 'CLIENT'},
                'position': {'latitude': 0.03, 'longitude': 0.0},
                'lastHeard': 100
            }
        }
        
        selected = self.tester._get_router_cluster_nodes()
        self.assertIn('!client1', selected)
        self.assertNotIn('!client2', selected)

    def test_limit_and_sorting(self):
        # Router at (0,0)
        # 3 Clients inside radius
        # Limit is 2
        # Sort by lastHeard
        self.tester.auto_discovery_limit = 2
        self.mock_interface.nodes = {
            '!router1': {
                'user': {'role': 'ROUTER'},
                'position': {'latitude': 0.0, 'longitude': 0.0},
                'lastHeard': 100
            },
            '!client1': {
                'user': {'role': 'CLIENT'},
                'position': {'latitude': 0.01, 'longitude': 0.0},
                'lastHeard': 200 # Newest
            },
            '!client2': {
                'user': {'role': 'CLIENT'},
                'position': {'latitude': 0.01, 'longitude': 0.0},
                'lastHeard': 100 # Oldest
            },
            '!client3': {
                'user': {'role': 'CLIENT'},
                'position': {'latitude': 0.01, 'longitude': 0.0},
                'lastHeard': 150 # Middle
            }
        }
        
        selected = self.tester._get_router_cluster_nodes()
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0], '!client1') # Newest first
        self.assertEqual(selected[1], '!client3') # Then middle
        self.assertNotIn('!client2', selected) # Oldest dropped

    def test_active_node_selection(self):
        # Router at (0,0)
        # Client1: Inside radius, but no lastHeard (inactive/unknown)
        # Client2: Inside radius, lastHeard=0 (inactive)
        # Client3: Inside radius, lastHeard=100 (active)
        self.mock_interface.nodes = {
            '!router1': {
                'user': {'role': 'ROUTER'},
                'position': {'latitude': 0.0, 'longitude': 0.0},
                'lastHeard': 100
            },
            '!client1': {
                'user': {'role': 'CLIENT'},
                'position': {'latitude': 0.01, 'longitude': 0.0}
                # No lastHeard
            },
            '!client2': {
                'user': {'role': 'CLIENT'},
                'position': {'latitude': 0.01, 'longitude': 0.0},
                'lastHeard': 0
            },
            '!client3': {
                'user': {'role': 'CLIENT'},
                'position': {'latitude': 0.01, 'longitude': 0.0},
                'lastHeard': 100
            }
        }
        
        selected = self.tester._get_router_cluster_nodes()
        self.assertIn('!client3', selected)
        self.assertNotIn('!client1', selected)
        self.assertNotIn('!client2', selected)

if __name__ == '__main__':
    unittest.main()
