import unittest
from mesh_monitor.analyzer import NetworkHealthAnalyzer

class TestAnalyzerEnhancements(unittest.TestCase):
    def setUp(self):
        self.config = {
            'thresholds': {
                'channel_utilization': 25.0,
                'air_util_tx': 7.0
            },
            'max_nodes_for_long_fast': 60
        }
        self.analyzer = NetworkHealthAnalyzer(config=self.config)

    def test_channel_utilization(self):
        nodes = {
            '!1': {
                'user': {'id': '!1', 'role': 'CLIENT'},
                'deviceMetrics': {'channelUtilization': 26.0},
                'position': {}
            }
        }
        issues = self.analyzer.analyze(nodes)
        self.assertTrue(any("Congestion" in i and "ChUtil" in i for i in issues))

    def test_air_util_tx(self):
        nodes = {
            '!1': {
                'user': {'id': '!1', 'role': 'CLIENT'},
                'deviceMetrics': {'airUtilTx': 8.0},
                'position': {}
            }
        }
        issues = self.analyzer.analyze(nodes)
        self.assertTrue(any("Congestion" in i and "AirUtilTx" in i for i in issues))

    def test_network_size(self):
        nodes = {}
        for i in range(61):
            nodes[f'!{i}'] = {'user': {'id': f'!{i}'}}
            
        issues = self.analyzer.analyze(nodes)
        self.assertTrue(any("Network Size" in i for i in issues))

    def test_router_density(self):
        # 3 Routers close to each other
        nodes = {
            '!1': {
                'user': {'id': '!1', 'role': 'ROUTER'},
                'position': {'latitude': 40.0, 'longitude': -74.0}
            },
            '!2': {
                'user': {'id': '!2', 'role': 'ROUTER'},
                'position': {'latitude': 40.001, 'longitude': -74.001} # Very close
            },
            '!3': {
                'user': {'id': '!3', 'role': 'ROUTER'},
                'position': {'latitude': 40.002, 'longitude': -74.002} # Very close
            }
        }
        issues = self.analyzer.analyze(nodes)
        self.assertTrue(any("High Router Density" in i for i in issues))

    def test_configurable_router_density(self):
        # Set threshold to 500m
        config = {
            'thresholds': {'router_density_threshold': 500}
        }
        analyzer = NetworkHealthAnalyzer(config=config)
        
        # Routers 1km apart (should NOT trigger warning with 500m threshold)
        nodes = {
            '!1': {
                'user': {'id': '!1', 'role': 'ROUTER'},
                'position': {'latitude': 40.0, 'longitude': -74.0}
            },
            '!2': {
                'user': {'id': '!2', 'role': 'ROUTER'},
                'position': {'latitude': 40.01, 'longitude': -74.01} # Approx 1.4km apart
            }
        }
        issues = analyzer.analyze(nodes)
        self.assertFalse(any("High Router Density" in i for i in issues))
        
        # Routers 200m apart (should trigger warning)
        nodes['!2']['position'] = {'latitude': 40.001, 'longitude': -74.001} # Very close
        issues = analyzer.analyze(nodes)
        self.assertTrue(any("High Router Density" in i for i in issues))

if __name__ == '__main__':
    unittest.main()
