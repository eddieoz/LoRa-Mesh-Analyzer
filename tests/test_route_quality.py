import unittest
from mesh_analyzer.analyzer import NetworkHealthAnalyzer

class TestRouteQuality(unittest.TestCase):
    def setUp(self):
        self.analyzer = NetworkHealthAnalyzer()

    def test_long_path(self):
        nodes = {
            '!11111111': {'user': {'longName': 'FarNode'}}
        }
        test_results = [
            {'node_id': '!11111111', 'hops_to': 4, 'route': []}
        ]
        
        issues = self.analyzer.check_route_quality(nodes, test_results)
        print("\nLong Path Issues:", issues)
        self.assertTrue(any("Long path" in i for i in issues))

    def test_favorite_router_usage(self):
        nodes = {
            '!22222222': {'user': {'longName': 'TargetNode'}},
            '!33333333': {'user': {'longName': 'FavRouter'}, 'is_favorite': True}
        }
        # Route uses FavRouter (ID !33333333 -> 0x33333333 = 858993459)
        test_results = [
            {'node_id': '!22222222', 'hops_to': 2, 'route': [858993459]}
        ]
        
        issues = self.analyzer.check_route_quality(nodes, test_results)
        print("\nFavorite Router Issues:", issues)
        self.assertTrue(any("Favorite Router" in i for i in issues))

    def test_weak_signal(self):
        nodes = {
            '!44444444': {'user': {'longName': 'WeakNode'}}
        }
        test_results = [
            {'node_id': '!44444444', 'snr': -15}
        ]
        
        issues = self.analyzer.check_route_quality(nodes, test_results)
        print("\nWeak Signal Issues:", issues)
        self.assertTrue(any("Weak signal" in i for i in issues))

if __name__ == '__main__':
    unittest.main()
