import logging
import time
from .utils import get_val, haversine, get_node_name
from . import constants

logger = logging.getLogger(__name__)

class NetworkHealthAnalyzer:
    def __init__(self, config=None, ignore_no_position=False):
        self.config = config or {}
        self.ignore_no_position = ignore_no_position
        
        # Load thresholds from config or use defaults
        thresholds = self.config.get('thresholds', {})
        self.ch_util_threshold = thresholds.get('channel_utilization', constants.DEFAULT_CHANNEL_UTILIZATION_THRESHOLD)
        self.air_util_threshold = thresholds.get('air_util_tx', constants.DEFAULT_AIR_UTIL_TX_THRESHOLD)
        self.router_density_threshold = thresholds.get('router_density_threshold', constants.DEFAULT_ROUTER_DENSITY_THRESHOLD)
        self.active_threshold_seconds = thresholds.get('active_threshold_seconds', constants.DEFAULT_ACTIVE_THRESHOLD_SECONDS)
        self.max_nodes_long_fast = self.config.get('max_nodes_for_long_fast', constants.DEFAULT_MAX_NODES_LONG_FAST)
        
        # Data storage for detailed analysis
        self.cluster_data = []  # Router cluster details with distances
        self.ch_util_data = {}  # Channel utilization analysis

    def analyze(self, nodes: dict, packet_history: list = None, my_node: dict = None, test_results: list = None) -> list:
        """
        Analyzes the node DB and packet history for potential issues.
        Returns a list of issue strings.
        """
        issues = []
        packet_history = packet_history or []
        
        # --- Node DB Analysis ---
        for node_id, node in nodes.items():
            user = get_val(node, 'user', {})
            metrics = get_val(node, 'deviceMetrics', {})
            position = get_val(node, 'position', {})
            
            node_name = get_node_name(node, node_id)
            
            # 1. Check Channel Utilization
            ch_util = get_val(metrics, 'channelUtilization', 0)
            if ch_util > self.ch_util_threshold:
                issues.append(f"Congestion: Node '{node_name}' reports ChUtil {ch_util:.1f}% (Threshold: {self.ch_util_threshold}%)")

            # 2. Check Airtime Usage
            air_util = get_val(metrics, 'airUtilTx', 0)
            if air_util > self.air_util_threshold:
                issues.append(f"Congestion: Node '{node_name}' AirUtilTx {air_util:.1f}% (Threshold: {self.air_util_threshold}%)")

            # 3. Check Roles
            role = get_val(user, 'role', 'CLIENT')
            
            # Handle role enum conversion if needed
            if isinstance(role, int):
                try:
                    from meshtastic.protobuf import config_pb2
                    role_name = config_pb2.Config.DeviceConfig.Role.Name(role)
                    if role_name == 'ROUTER_CLIENT':
                         issues.append(f"Config: Node '{node_name}' is using deprecated role 'ROUTER_CLIENT'.")
                    role = role_name # Normalize to string for later checks
                except ImportError:
                    pass
            elif role == 'ROUTER_CLIENT':
                issues.append(f"Config: Node '{node_name}' is using deprecated role 'ROUTER_CLIENT'.")

            # 4. Check for 'Router' role without GPS/Position
            if not self.ignore_no_position and (role == 'ROUTER' or role == 'REPEATER'):
                lat = get_val(position, 'latitude')
                lon = get_val(position, 'longitude')
                if lat is None or lon is None:
                     issues.append(f"Config: Node '{node_name}' is '{role}' but has no position. Verify placement.")

            # 5. Battery
            battery_level = get_val(metrics, 'batteryLevel', 100)
            if (role == 'ROUTER' or role == 'REPEATER') and battery_level < 20:
                 issues.append(f"Health: Critical Node '{node_name}' ({role}) has low battery: {battery_level}%")
                 
            # 6. Firmware
            hw_model = get_val(user, 'hwModel', 'UNKNOWN')

        # --- Packet History Analysis ---
        if packet_history:
            issues.extend(self.check_duplication(packet_history, nodes))
            issues.extend(self.check_hop_counts(packet_history, nodes))

        # --- Geospatial Analysis ---
        density_issues, self.cluster_data = self.check_router_density(nodes, test_results)
        issues.extend(density_issues)
        issues.extend(self.check_network_size_and_preset(nodes))
        if my_node:
            issues.extend(self.check_signal_vs_distance(nodes, my_node))
        
        # --- Advanced Analysis ---
        self.analyze_channel_utilization(nodes)  # Stores data in self.ch_util_data
        issues.extend(self.check_client_relaying_over_router(nodes, test_results))

        return issues


        return issues


    def _calculate_router_distances(self, router: dict, nodes: dict, radius: float) -> tuple:
        """
        Helper to calculate neighbors and nearby routers for a given router.
        Returns: (total_neighbors, nearby_routers_count)
        """
        nearby_routers = 0
        total_neighbors = 0
        
        for node_id, node in nodes.items():
            if node_id == router['id']: continue
            pos = get_val(node, 'position', {})
            lat = get_val(pos, 'latitude')
            lon = get_val(pos, 'longitude')
            
            if lat and lon:
                dist = haversine(router['lat'], router['lon'], lat, lon)
                if dist < radius:
                    total_neighbors += 1
                    # Check if it's also a router
                    user = get_val(node, 'user', {})
                    role = get_val(user, 'role')
                    
                    is_router_role = False
                    if isinstance(role, int):
                         if role in [2, 3, 9]: # ROUTER_CLIENT, ROUTER, ROUTER_LATE
                             is_router_role = True
                    elif role in ['ROUTER', 'ROUTER_CLIENT', 'ROUTER_LATE']:
                         is_router_role = True
                         
                    if is_router_role:
                        nearby_routers += 1
        
        return total_neighbors, nearby_routers

    def get_router_stats(self, nodes: dict, test_results: list = None) -> list:
        """
        Calculates detailed statistics for each router.
        Returns a list of dictionaries.
        """
        stats = []
        routers = []
        
        # 1. Identify Routers
        for node_id, node in nodes.items():
            user = get_val(node, 'user', {})
            role = get_val(user, 'role')
            
            is_router = False
            if isinstance(role, int):
                # 2=ROUTER_CLIENT, 3=ROUTER, 4=REPEATER, 5=TRACKER, 6=SENSOR, 7=TAK, 8=CLIENT_MUTE, 9=ROUTER_LATE
                if role in [2, 3, 9]: 
                    is_router = True
            elif role in ['ROUTER', 'ROUTER_CLIENT', 'ROUTER_LATE']:
                is_router = True
            
            if is_router:
                pos = get_val(node, 'position', {})
                lat = get_val(pos, 'latitude')
                lon = get_val(pos, 'longitude')
                
                if lat is not None and lon is not None:
                    routers.append({
                        'id': node_id,
                        'name': get_node_name(node, node_id),
                        'role': 'ROUTER' if role in [3, 'ROUTER'] else ('ROUTER_LATE' if role in [9, 'ROUTER_LATE'] else 'ROUTER_CLIENT'),
                        'lat': lat,
                        'lon': lon,
                        'metrics': get_val(node, 'deviceMetrics', {})
                    })

        # 2. Analyze Each Router
        for r in routers:
            # A. Neighbors (within configured radius)
            radius = self.router_density_threshold
            total_neighbors, nearby_routers = self._calculate_router_distances(r, nodes, radius)

            # B. Relay Count
            relay_count = 0
            if test_results:
                for res in test_results:
                    route = res.get('route', [])
                    # Normalize route IDs to hex strings for comparison
                    route_hex = [f"!{n:08x}" if isinstance(n, int) else n for n in route]
                    
                    if r['id'] in route_hex:
                        relay_count += 1
                    
                    # Check return path as well
                    route_back = res.get('route_back', [])
                    route_back_hex = [f"!{n:08x}" if isinstance(n, int) else n for n in route_back]
                    if r['id'] in route_back_hex:
                        relay_count += 1
            
            # C. Channel Util
            ch_util = get_val(r['metrics'], 'channelUtilization', 0)
            
            # D. Status / Issues
            status_issues = []
            if nearby_routers >= 2:
                status_issues.append("Redundant")
            if ch_util > 20:
                status_issues.append("Congested")
            if total_neighbors > 5 and relay_count == 0:
                status_issues.append("Ineffective")
            
            stats.append({
                'id': r['id'],
                'name': r['name'],
                'lat': r['lat'],
                'lon': r['lon'],
                'role': r['role'],
                'neighbors': total_neighbors,
                'routers_nearby': nearby_routers,
                'radius': radius,
                'ch_util': ch_util,
                'relay_count': relay_count,
                'status': ", ".join(status_issues) if status_issues else "OK"
            })
            
        return stats

    def check_router_efficiency(self, nodes: dict, test_results: list = None) -> list:
        """
        Analyzes router placement and efficiency.
        Returns a list of issue strings.
        """
        issues = []
        stats = self.get_router_stats(nodes, test_results)
        
        for s in stats:
            if "Redundant" in s['status']:
                issues.append(f"Efficiency: Router '{s['name']}' is Redundant. Has {s['routers_nearby']} other routers within {s['radius']/1000:.1f}km. Consolidate?")
            if "Congested" in s['status']:
                issues.append(f"Efficiency: Router '{s['name']}' is Congested (ChUtil {s['ch_util']:.1f}% > 20%).")
            if "Ineffective" in s['status']:
                issues.append(f"Efficiency: Router '{s['name']}' is Ineffective. Has {s['neighbors']} neighbors but relayed 0 packets in tests.")

        return issues

    def analyze_channel_utilization(self, nodes: dict) -> None:
        """
        Analyzes channel utilization across the network.
        Determines if congestion is mesh-wide or isolated to specific nodes.
        Returns detailed data for reporting.
        """
        high_util_nodes = []
        active_node_count = 0
        current_time = time.time()
        
        for node_id, node in nodes.items():
            # Check if node is active
            last_heard = get_val(node, 'lastHeard', 0) or 0
            if current_time - last_heard < self.active_threshold_seconds:
                active_node_count += 1
            else:
                continue  # Skip inactive nodes
            
            # Check channel utilization
            metrics = get_val(node, 'deviceMetrics', {})
            ch_util = get_val(metrics, 'channelUtilization', 0)
            
            if ch_util > self.ch_util_threshold:
                node_name = get_node_name(node, node_id)
                high_util_nodes.append({
                    'id': node_id,
                    'name': node_name,
                    'util_pct': ch_util
                })
        
        # Determine if widespread or isolated
        if not high_util_nodes:
            self.ch_util_data = {'type': 'none', 'nodes': []}
            return
        
        # If >30% of active nodes have high util, it's mesh-wide
        is_widespread = len(high_util_nodes) / active_node_count > 0.30 if active_node_count > 0 else False
        
        self.ch_util_data = {
            'type': 'widespread' if is_widespread else 'isolated',
            'nodes': high_util_nodes,
            'active_count': active_node_count,
            'affected_count': len(high_util_nodes)
        }

    def check_client_relaying_over_router(self, nodes: dict, test_results: list) -> list:
        """
        Detects ineffective routers by checking if nearby CLIENT nodes
        are relaying more frequently than the router itself.
        Uses router_density_threshold as the radius to check.
        """
        issues = []
        
        if not test_results:
            return issues
        
        from mesh_analyzer.route_analyzer import RouteAnalyzer
        route_analyzer = RouteAnalyzer(nodes)
        relay_usage = route_analyzer._analyze_relay_usage(
            [r for r in test_results if r.get('status') == 'success']
        )
        
        # Build relay count lookup
        relay_counts = {item['id']: item['count'] for item in relay_usage}
        
        # Find all routers
        routers = []
        for node_id, node in nodes.items():
            user = get_val(node, 'user', {})
            role = get_val(user, 'role')
            
            is_router = False
            if isinstance(role, int):
                if role in [2, 3, 4, 9]: # ROUTER, ROUTER_CLIENT, REPEATER, ROUTER_LATE
                    is_router = True
            elif role in ['ROUTER', 'REPEATER', 'ROUTER_CLIENT', 'ROUTER_LATE']:
                is_router = True
            
            if is_router:
                pos = get_val(node, 'position', {})
                lat = get_val(pos, 'latitude')
                lon = get_val(pos, 'longitude')
                metrics = get_val(node, 'deviceMetrics', {})
                ch_util = get_val(metrics, 'channelUtilization', 0)
                
                if lat is not None and lon is not None:
                    routers.append({
                        'id': node_id,
                        'name': get_node_name(node, node_id),
                        'lat': lat,
                        'lon': lon,
                        'relay_count': relay_counts.get(node_id, 0),
                        'ch_util': ch_util
                    })
        
        # For each router, check nearby clients
        for router in routers:
            router_relays = router['relay_count']
            router_ch_util = router['ch_util']
            nearby_clients = []
            
            for node_id, node in nodes.items():
                if node_id == router['id']:
                    continue
                
                user = get_val(node, 'user', {})
                role = get_val(user, 'role')
                
                # Check if it's a client
                is_client = False
                if role is None:
                    is_client = True # Assume client if role is unknown
                elif isinstance(role, int):
                    if role in [0, 1, 8]: # CLIENT, CLIENT_MUTE, etc
                        is_client = True
                elif role in ['CLIENT', 'CLIENT_MUTE', 'TRACKER', 'SENSOR']:
                    is_client = True
                
                if not is_client:
                    continue
                
                # Check distance
                pos = get_val(node, 'position', {})
                lat = get_val(pos, 'latitude')
                lon = get_val(pos, 'longitude')
                
                if lat is not None and lon is not None:
                    dist = haversine(router['lat'], router['lon'], lat, lon)
                        
                    if dist <= self.router_density_threshold:
                        client_relays = relay_counts.get(node_id, 0)
                        if client_relays >= router_relays * 2 and client_relays > 0:
                            nearby_clients.append({
                                'name': get_node_name(node, node_id),
                                'relay_count': client_relays,
                                'distance_km': dist / 1000
                            })
            
            # Report if clients are relaying more than router
            if nearby_clients:
                for client in nearby_clients:
                    msg = f"Efficiency: Router '{router['name']}' has {router_relays} relays, "
                    msg += f"but nearby client '{client['name']}' ({client['distance_km']:.2f}km away) has {client['relay_count']} relays. "
                    msg += f"Router ChUtil: {router_ch_util:.1f}%. "
                    msg += f"Router may be ineffective - check antenna, placement, or configuration."
                    issues.append(msg)
        
        return issues


    def check_route_quality(self, nodes: dict, test_results: list) -> list:
        """
        Analyzes the quality of routes found in traceroute tests.
        Checks for Hop Efficiency and Favorite Router usage.
        """
        issues = []
        
        if not test_results:
            return issues

        for res in test_results:
            node_id = res.get('node_id')
            node = nodes.get(node_id, {})
            node_name = get_node_name(node, node_id)
            
            # 1. Hop Efficiency
            hops_to = res.get('hops_to')
            if isinstance(hops_to, int):
                if hops_to > 3:
                     issues.append(f"Route Quality: Long path to '{node_name}' ({hops_to} hops). Latency risk.")

            # 2. Favorite Router Usage
            route = res.get('route', [])
            used_favorite = False
            for hop_id in route:
                # Normalize ID
                hop_hex = f"!{hop_id:08x}" if isinstance(hop_id, int) else hop_id
                hop_node = nodes.get(hop_hex)
                if hop_node:
                    is_fav = get_val(hop_node, 'is_favorite', False)
                    if is_fav:
                        used_favorite = True
                        fav_name = get_node_name(hop_node, hop_hex)
                        issues.append(f"Route Quality: Route to '{node_name}' uses Favorite Router '{fav_name}'. Range Extended.")
            
            # 3. SNR Check
            snr = res.get('snr')
            if snr is not None and snr < -10:
                 issues.append(f"Route Quality: Weak signal to '{node_name}' (SNR {snr}dB). Link unstable.")

        return list(set(issues))

    def check_duplication(self, history: list, nodes: dict) -> list:
        """
        Detects if the same message ID is being received multiple times.
        """
        issues = []
        # Group by packet ID
        packet_counts = {}
        for pkt in history:
            pkt_id = pkt.get('id')
            if pkt_id:
                packet_counts[pkt_id] = packet_counts.get(pkt_id, 0) + 1
        
        # Threshold: If we see the same packet ID > 3 times in our short history window
        for pkt_id, count in packet_counts.items():
            if count > 3:
                issues.append(f"Spam: Detected {count} duplicates for Packet ID {pkt_id}. Possible routing loop or aggressive re-broadcasting.")
        return issues

    def check_hop_counts(self, history: list, nodes: dict) -> list:
        """
        Checks if packets are arriving with high hop counts.
        """
        issues = []
        
        for pkt in history:
            sender_id = pkt.get('fromId')
            if sender_id:
                node = nodes.get(sender_id)
                if node:
                    hops_away = get_val(node, 'hopsAway', 0)
                    if hops_away > 3:
                         node_name = get_node_name(node, sender_id)
                         issues.append(f"Topology: Node '{node_name}' is {hops_away} hops away. (Ideally <= 3)")
        return list(set(issues))



    def check_network_size_and_preset(self, nodes: dict) -> list:
        """
        Checks if network size exceeds recommendations for the current preset.
        Note: We can't easily know the *current* preset of the network just from node DB,
        but we can warn based on size.
        """
        issues = []
        issues = []
        
        # Filter for active nodes
        current_time = time.time()
        active_nodes = 0
        
        for node in nodes.values():
            last_heard = get_val(node, 'lastHeard', 0) or 0
            # Some nodes might use 'last_heard' or other keys, but standard is usually lastHeard in the node dict
            # If it's 0, it might be very old or unknown.
            
            if current_time - last_heard < self.active_threshold_seconds:
                active_nodes += 1
        
        if active_nodes > self.max_nodes_long_fast:
             issues.append(f"Network Size: {active_nodes} active nodes detected (seen in last {self.active_threshold_seconds/3600:.1f}h). If using LONG_FAST, consider switching to a faster preset (e.g. LONG_MODERATE or SHORT_FAST) to reduce collision probability.")
             
        return issues

    def check_router_density(self, nodes: dict, test_results: list = None) -> tuple:
        """
        Checks for high density of routers.
        Identifies clusters of routers within 'router_density_threshold'.
        Recommends keeping the most effective router (highest relay count) and demoting others.
        Returns: (issues, cluster_data)
        """
        issues = []
        cluster_data = []  # New: detailed cluster information
        
        # 1. Get Router Stats (includes relay counts)
        stats = self.get_router_stats(nodes, test_results)
        # Map ID to stat for easy lookup
        stat_map = {s['id']: s for s in stats}
        
        # Filter for routers with valid position
        routers = []
        for s in stats:
             # get_router_stats already filters for routers with position
             routers.append(s)

        if not routers:
            return issues, cluster_data

        # 2. Build Clusters
        # Adjacency list: index -> list of neighbor indices
        adj = {i: [] for i in range(len(routers))}
        
        for i in range(len(routers)):
            for j in range(i + 1, len(routers)):
                r1 = routers[i]
                r2 = routers[j]
                dist = haversine(r1['lat'], r1['lon'], r2['lat'], r2['lon'])
                
                if dist < self.router_density_threshold:
                    adj[i].append(j)
                    adj[j].append(i)
        
        # Find connected components (clusters)
        visited = set()
        clusters = []
        
        for i in range(len(routers)):
            if i not in visited:
                component = []
                stack = [i]
                visited.add(i)
                while stack:
                    curr = stack.pop()
                    component.append(routers[curr])
                    for neighbor in adj[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            stack.append(neighbor)
                if len(component) > 1:
                    clusters.append(component)
        
        # 3. Analyze Clusters and Generate Recommendations
        for cluster in clusters:
            # Sort by relay_count (desc), then neighbors (desc)
            # We want the "best" router first
            cluster.sort(key=lambda x: (x['relay_count'], x['neighbors']), reverse=True)
            
            best_router = cluster[0]
            others = cluster[1:]
            
            other_names = [o['name'] for o in others]
            
            # Calculate distances between all router pairs in this cluster
            distances = []
            for i in range(len(cluster)):
                for j in range(i + 1, len(cluster)):
                    r1 = cluster[i]
                    r2 = cluster[j]
                    dist_m = haversine(r1['lat'], r1['lon'], r2['lat'], r2['lon'])
                    distances.append({
                        'router1': r1['name'],
                        'router2': r2['name'],
                        'distance_m': dist_m
                    })
            
            # Store cluster data
            cluster_data.append({
                'size': len(cluster),
                'best_router': best_router['name'],
                'best_router_relays': best_router['relay_count'],
                'other_routers': other_names,
                'distances': distances
            })
            
            # Construct message (kept for backward compatibility)
            msg = f"Topology: High Router Density! Found cluster of {len(cluster)} routers. "
            msg += f"Best positioned seems to be '{best_router['name']}' ({best_router['relay_count']} relays). "
            msg += f"Consider changing others to CLIENT: {', '.join(other_names)}."
            
            issues.append(msg)

        return issues, cluster_data


    def check_signal_vs_distance(self, nodes: dict, my_node: dict) -> list:
        """
        Checks for nodes that are close but have poor SNR (indicating obstruction or antenna issues).
        """
        issues = []
        
        my_pos = get_val(my_node, 'position', {})
        my_lat = get_val(my_pos, 'latitude')
        my_lon = get_val(my_pos, 'longitude')
        
        if my_lat is None or my_lon is None:
            return issues # Can't calculate distance relative to me

        for node_id, node in nodes.items():
            # Skip myself
            user = get_val(node, 'user', {})
            if node_id == get_val(user, 'id'):
                continue
                
            pos = get_val(node, 'position', {})
            lat = get_val(pos, 'latitude')
            lon = get_val(pos, 'longitude')
            
            if lat is None or lon is None:
                continue

            # Calculate distance
            dist = haversine(my_lat, my_lon, lat, lon)
            
            # Check SNR (if available in snr field or similar)
            snr = get_val(node, 'snr')
            
            if snr is not None:
                # Heuristic: If < 1km and SNR < 0, that's suspicious for LoRa (unless heavy obstruction)
                # Ideally, close nodes should have high SNR (> 5-10)
                if dist < 1000 and snr < -5:
                     node_name = get_node_name(node, node_id)
                     issues.append(f"Performance: Node '{node_name}' is close ({dist:.0f}m) but has poor SNR ({snr:.1f}dB). Check antenna/LOS.")
        
        return issues
