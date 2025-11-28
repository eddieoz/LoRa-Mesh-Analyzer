
import logging
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)

class RouteAnalyzer:
    """
    Analyzes traceroute history to identify network topology, bottlenecks, and stability.
    """
    def __init__(self, nodes_db=None):
        self.nodes_db = nodes_db or {}

    def analyze_routes(self, test_results):
        """
        Main entry point for route analysis.
        Returns a dictionary containing various analysis metrics.
        """
        if not test_results:
            return {}

        # Filter only successful traceroutes
        successful_tests = [r for r in test_results if r.get('status') == 'success']
        
        analysis = {
            'total_routes': len(successful_tests),
            'relay_usage': self._analyze_relay_usage(successful_tests),
            'common_paths': self._analyze_common_paths(successful_tests),
            'link_quality': self._analyze_link_quality(successful_tests),
            'bottlenecks': self._identify_bottlenecks(successful_tests)
        }
        
        return analysis

    def _analyze_relay_usage(self, results):
        """
        Counts how often each node appears as a relay (excluding source and destination).
        """
        relay_counts = Counter()
        
        for res in results:
            # Combine route to and route back
            # Route lists usually exclude source but include destination (or intermediate hops)
            # We want strictly intermediate relays
            
            # Route To: [hop1, hop2, dest]
            route_to = res.get('route', [])
            target_id = res.get('node_id')
            
            for node in route_to:
                # Normalize ID
                node_hex = f"!{node:08x}" if isinstance(node, int) else node
                if node_hex != target_id: # Don't count the destination as a relay
                    relay_counts[node_hex] += 1
            
            # Route Back: [hop1, hop2, source]
            # Route back usually ends at us, so we exclude us (which is implicit)
            route_back = res.get('route_back', [])
            for node in route_back:
                node_hex = f"!{node:08x}" if isinstance(node, int) else node
                # We assume we are not in the list, but just in case
                relay_counts[node_hex] += 1
                
        # Convert to list of dicts for easier reporting
        usage_stats = []
        for node_id, count in relay_counts.most_common():
            name = self._get_node_name(node_id)
            usage_stats.append({
                'id': node_id,
                'name': name,
                'count': count
            })
            
        return usage_stats

    def _analyze_common_paths(self, results):
        """
        Identifies the most common path to each destination.
        """
        paths_by_dest = defaultdict(Counter)
        
        for res in results:
            target_id = res.get('node_id')
            route = res.get('route', [])
            
            # Convert to tuple of hex IDs for hashing
            route_hex = tuple(f"!{n:08x}" if isinstance(n, int) else n for n in route)
            
            if route_hex:
                paths_by_dest[target_id][route_hex] += 1
        
        # Format for report
        common_paths = {}
        for dest, counter in paths_by_dest.items():
            most_common = counter.most_common(1)[0] # (path_tuple, count)
            path_str = " -> ".join(most_common[0])
            common_paths[dest] = {
                'path': path_str,
                'count': most_common[1],
                'total': sum(counter.values()),
                'stability': (most_common[1] / sum(counter.values())) * 100
            }
            
        return common_paths

    def _analyze_link_quality(self, results):
        """
        Aggregates SNR values for specific links (A -> B).
        """
        link_stats = defaultdict(list)
        
        for res in results:
            # We need SNR values which correspond to hops
            # This is tricky because 'route' is just IDs. 
            # We need the 'snr_towards' list if available (which we haven't fully implemented capturing yet)
            # For now, we can only analyze the final SNR (Us -> First Hop -> ... -> Dest)
            pass
            
        return {}

    def _identify_bottlenecks(self, results):
        """
        Identifies nodes that appear in routes to MANY different destinations.
        High 'betweenness'.
        """
        node_destinations = defaultdict(set)
        
        for res in results:
            target_id = res.get('node_id')
            route = res.get('route', [])
            
            for node in route:
                node_hex = f"!{node:08x}" if isinstance(node, int) else node
                if node_hex != target_id:
                    node_destinations[node_hex].add(target_id)
        
        # Sort by number of unique destinations served
        bottlenecks = []
        for node, dests in node_destinations.items():
            bottlenecks.append({
                'id': node,
                'name': self._get_node_name(node),
                'destinations_served': len(dests),
                'destinations': list(dests)
            })
            
        bottlenecks.sort(key=lambda x: x['destinations_served'], reverse=True)
        return bottlenecks[:5] # Top 5

    def _get_node_name(self, node_id):
        """Helper to get node name from DB"""
        if node_id in self.nodes_db:
            user = self.nodes_db[node_id].get('user', {})
            return user.get('longName') or user.get('shortName') or node_id
        return node_id
