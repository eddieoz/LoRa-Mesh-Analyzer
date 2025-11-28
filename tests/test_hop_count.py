import unittest
from unittest.mock import Mock
from mesh_analyzer.active_tests import ActiveTester


class TestHopCountCalculation(unittest.TestCase):
    """
    Tests to verify that hop counts are correctly calculated.
    A hop count should equal the number of intermediate nodes (excluding source and destination).
    """

    def setUp(self):
        # Mock interface
        self.mock_interface = Mock()
        self.tester = ActiveTester(
            interface=self.mock_interface,
            local_node_id="!42bb5074"
        )

    def test_user_example_forward_route(self):
        """
        Test with the exact example from the user:
        Route to destination: !42bb5074 --> !433c9a58 --> !51165eae --> !433f0ea4
        Intermediate hops: !433c9a58, !51165eae = 2 hops
        
        The route array excludes the source (!42bb5074) but includes destination (!433f0ea4)
        So route = [!433c9a58, !51165eae, !433f0ea4] (3 elements)
        Expected hops = len(route) - 2 = 3 - 2 = 1... wait that's wrong
        
        Actually, checking the log output format more carefully:
        "Route to !433f0ea4: !433c9a58 -> !51165eae (1 hops)"
        
        This suggests the route array does NOT include the source or destination,
        only the intermediate nodes. So:
        route = [!433c9a58, !51165eae] (2 elements)
        
        But user says it should be 2 hops, and currently shows 1 hop.
        With len(route) - 1, we get: 2 - 1 = 1 hop ✓ (matches current wrong output)
        With len(route) - 2, we get: 2 - 2 = 0 hops ✗ (wrong!)
        
        Wait, let me re-read the logs more carefully:
        "Route traced towards destination:"
        "!42bb5074 --> !433c9a58 (-19.5dB) --> !51165eae (-14.0dB) --> !433f0ea4 (-14.75dB)"
        
        This shows the FULL path including source and destination.
        
        "Route to !433f0ea4: !433c9a58 -> !51165eae (1 hops)"
        
        This shows only intermediate nodes in the route array: [!433c9a58, !51165eae]
        But user says it should be 2 hops.
        
        Hmm, let me count the intermediate nodes:
        - From !42bb5074 to !433c9a58: 1st hop
        - From !433c9a58 to !51165eae: 2nd hop  
        - From !51165eae to !433f0ea4: 3rd hop (to destination)
        
        So there are 2 intermediate NODES (!433c9a58, !51165eae).
        But wait - the number of hops is the number of links, not nodes.
        
        Actually, re-reading the user's clarification:
        "where: Route to !433f0ea4: !433c9a58 -> !51165eae (1 hops) should be 2 hops"
        
        Ah! The route shows [!433c9a58, !51165eae] which represents the path.
        The destination !433f0ea4 is NOT in this array.
        
        So to count hops:
        - Source (!42bb5074) to !433c9a58: 1 hop
        - !433c9a58 to !51165eae: 1 hop
        - !51165eae to !433f0ea4: 1 hop
        Total: 3 hops
        
        But user says it should be 2 hops. Let me check the "Route back":
        "Route back: !9ea09e84 -> !51165eae -> !7b778173 (2 hops) should be 3 hops"
        
        Route back has 3 nodes [!9ea09e84, !51165eae, !7b778173]
        Currently shows 2 hops (len - 1 = 3 - 1 = 2)
        Should be 3 hops
        
        So with len - 2, we'd get: 3 - 2 = 1 hop (wrong!)
        
        Wait, I think I'm confusing myself. Let me think about what "hops" means.
        
        Looking at "Route traced back to us:"
        "!433f0ea4 --> 9ea09e84 (-5.75dB) --> !51165eae (-5.25dB) --> !7b778173 (1.75dB) --> !42bb5074 (6.5dB)"
        
        This is the FULL route with 5 nodes total.
        Source: !433f0ea4
        Destination: !42bb5074
        Intermediate: 9ea09e84, !51165eae, !7b778173
        
        The log says "Route back: !9ea09e84 -> !51165eae -> !7b778173 (2 hops)"
        
        So route_back array = [9ea09e84, !51165eae, !7b778173, !42bb5074] (includes destination)
        Or route_back array = [9ea09e84, !51165eae, !7b778173] (excludes destination)
        
        With current calculation len - 1:
        If array has 4 elements: 4 - 1 = 3 hops
        If array has 3 elements: 3 - 1 = 2 hops ✓ (matches current output)
        
        User says it should be 3 hops (the number of intermediate nodes).
        
        So the array must have 4 elements: [9ea09e84, !51165eae, !7b778173, !42bb5074]
        With len - 2: 4 - 2 = 2 hops ✗
        With len - 1: 4 - 1 = 3 hops ✓
        
        But wait, that would make the current code correct...
        
        Actually, I think the issue is that the route array includes the DESTINATION but not the SOURCE.
        
        Let me verify with the forward route:
        Full path: !42bb5074 --> !433c9a58 --> !51165eae --> !433f0ea4
        Route array (excluding source, including dest): [!433c9a58, !51165eae, !433f0ea4]
        Current calculation: len - 1 = 3 - 1 = 2 hops
        
        But the log shows: "Route to !433f0ea4: !433c9a58 -> !51165eae (1 hops)"
        
        This means the route array does NOT include the destination!
        Route array: [!433c9a58, !51165eae]
        Current calculation: len - 1 = 2 - 1 = 1 hop ✓ (matches log)
        User says it should be 2 hops
        
        If we use len (no subtraction): 2 - 0 = 2 hops ✓
        
        So the correct formula is just `len(route)`!
        Not `len(route) - 1` and not `len(route) - 2`.
        
        Let me verify with route back:
        Full path: !433f0ea4 --> 9ea09e84 --> !51165eae --> !7b778173 --> !42bb5074
        Route array (intermediate nodes only): [9ea09e84, !51165eae, !7b778173]
        Current: len - 1 = 3 - 1 = 2 hops ✓ (matches log)
        User: should be 3 hops
        With len: 3 - 0 = 3 hops ✓
        
        So the route array contains ONLY the intermediate relay nodes, not the source or destination!
        The hop count should just be `len(route)`.
        """
        # Simulate a traceroute packet with the exact data from the user's example
        # Route forward: !42bb5074 -> !433c9a58 -> !51165eae -> !433f0ea4
        # Intermediate nodes (what goes in route array): [!433c9a58, !51165eae]
        
        # Convert hex IDs to integers for route array
        node_433c9a58 = 0x433c9a58
        node_51165eae = 0x51165eae
        node_433f0ea4 = 0x433f0ea4
        
        packet = {
            'fromId': '!433f0ea4',
            'decoded': {
                'traceroute': {
                    'route': [node_433c9a58, node_51165eae],  # Intermediate nodes only
                    'routeBack': []
                }
            },
            'rxSnr': -14.75
        }
        
        # Record the result
        self.tester.record_result('!433f0ea4', packet)
        
        # Check that hop count was calculated correctly
        results = self.tester.test_results
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['hops_to'], 2, 
                        "Forward route should have 2 hops (2 intermediate nodes)")

    def test_user_example_return_route(self):
        """
        Route back: !433f0ea4 -> 9ea09e84 -> !51165eae -> !7b778173 -> !42bb5074
        Intermediate hops: 9ea09e84, !51165eae, !7b778173 = 3 hops
        Route array: [9ea09e84, !51165eae, !7b778173]
        """
        # Create fresh tester for this test
        fresh_tester = ActiveTester(
            interface=self.mock_interface,
            local_node_id="!42bb5074"
        )
        
        node_9ea09e84 = 0x9ea09e84
        node_51165eae = 0x51165eae
        node_7b778173 = 0x7b778173
        
        packet = {
            'fromId': '!433f0ea4',
            'decoded': {
                'traceroute': {
                    'route': [],
                    'routeBack': [node_9ea09e84, node_51165eae, node_7b778173]
                }
            },
            'rxSnr': 6.5
        }
        
        fresh_tester.record_result('!433f0ea4', packet)
        
        results = fresh_tester.test_results
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['hops_back'], 3,
                        "Return route should have 3 hops (3 intermediate nodes)")

    def test_direct_connection(self):
        """
        Test direct connection with no intermediate hops.
        Route: Source -> Destination (no intermediate nodes)
        Route array: []
        Expected hops: 0
        """
        packet = {
            'fromId': '!11111111',
            'decoded': {
                'traceroute': {
                    'route': [],  # Direct connection, no intermediate nodes
                    'routeBack': []
                }
            },
            'rxSnr': 8.0
        }
        
        self.tester.record_result('!11111111', packet)
        
        results = self.tester.test_results
        self.assertEqual(results[0]['hops_to'], 0, "Direct connection should have 0 hops")
        self.assertEqual(results[0]['hops_back'], 0, "Direct connection should have 0 hops")

    def test_single_intermediate_node(self):
        """
        Test single intermediate hop.
        Route: Source -> Relay -> Destination
        Route array: [relay_node]
        Expected hops: 1
        """
        relay_node = 0x22222222
        
        packet = {
            'fromId': '!33333333',
            'decoded': {
                'traceroute': {
                    'route': [relay_node],  # One intermediate node
                    'routeBack': [relay_node]
                }
            },
            'rxSnr': 5.0
        }
        
        self.tester.record_result('!33333333', packet)
        
        results = self.tester.test_results
        self.assertEqual(results[0]['hops_to'], 1, "Route with 1 intermediate node should have 1 hop")
        self.assertEqual(results[0]['hops_back'], 1, "Route with 1 intermediate node should have 1 hop")


if __name__ == '__main__':
    unittest.main()
