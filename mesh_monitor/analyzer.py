import logging
import time
from .utils import get_val, haversine, get_node_name

logger = logging.getLogger(__name__)

class NetworkHealthAnalyzer:
    def __init__(self, config=None, ignore_no_position=False):
        self.config = config or {}
        self.ignore_no_position = ignore_no_position
        
        # Load thresholds from config or use defaults
        thresholds = self.config.get('thresholds', {})
        self.ch_util_threshold = thresholds.get('channel_utilization', 25.0)
        self.air_util_threshold = thresholds.get('air_util_tx', 7.0) # Updated default to 7%
        self.router_density_threshold = thresholds.get('router_density_threshold', 2000)
        self.max_nodes_long_fast = self.config.get('max_nodes_for_long_fast', 60)

    def analyze(self, nodes, packet_history=None, my_node=None):
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
        issues.extend(self.check_router_density(nodes))
        issues.extend(self.check_network_size_and_preset(nodes))
        if my_node:
            issues.extend(self.check_signal_vs_distance(nodes, my_node))

        return issues

    def get_router_stats(self, nodes, test_results=None):
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
            # A. Neighbors (2km)
            nearby_routers = 0
            total_neighbors = 0
            
            for node_id, node in nodes.items():
                if node_id == r['id']: continue
                pos = get_val(node, 'position', {})
                lat = get_val(pos, 'latitude')
                lon = get_val(pos, 'longitude')
                
                if lat and lon:
                    dist = haversine(r['lat'], r['lon'], lat, lon)
                    if dist < 2000:
                        total_neighbors += 1
                        # Check if it's also a router
                        # (Simplified check, ideally we'd check against the routers list but this is O(N))
                        user = get_val(node, 'user', {})
                        role = get_val(user, 'role')
                        if role in [2, 3, 'ROUTER', 'ROUTER_CLIENT']:
                            nearby_routers += 1

            # B. Relay Count
            relay_count = 0
            if test_results:
                for res in test_results:
                    route = res.get('route', [])
                    # Normalize route IDs to hex strings for comparison
                    route_hex = [f"!{n:08x}" if isinstance(n, int) else n for n in route]
                    
                    if r['id'] in route_hex:
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
                'role': r['role'],
                'neighbors_2km': total_neighbors,
                'routers_2km': nearby_routers,
                'ch_util': ch_util,
                'relay_count': relay_count,
                'status': ", ".join(status_issues) if status_issues else "OK"
            })
            
        return stats

    def check_router_efficiency(self, nodes, test_results=None):
        """
        Analyzes router placement and efficiency.
        Returns a list of issue strings.
        """
        issues = []
        stats = self.get_router_stats(nodes, test_results)
        
        for s in stats:
            if "Redundant" in s['status']:
                issues.append(f"Efficiency: Router '{s['name']}' is Redundant. Has {s['routers_2km']} other routers within 2km. Consolidate?")
            if "Congested" in s['status']:
                issues.append(f"Efficiency: Router '{s['name']}' is Congested (ChUtil {s['ch_util']:.1f}% > 20%).")
            if "Ineffective" in s['status']:
                issues.append(f"Efficiency: Router '{s['name']}' is Ineffective. Has {s['neighbors_2km']} neighbors but relayed 0 packets in tests.")

        return issues

    def check_route_quality(self, nodes, test_results):
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

    def check_duplication(self, history, nodes):
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

    def check_hop_counts(self, history, nodes):
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

    def check_router_density(self, nodes):
        """
        Checks if ROUTER nodes are too close to each other (< 500m).
        """
        issues = []
        routers = []
        
        # Filter for routers with valid position
        for node_id, node in nodes.items():
            user = get_val(node, 'user', {})
            role = get_val(user, 'role')
            
            is_router = False
            if isinstance(role, int):
                if role in [2, 3, 4]: # ROUTER, ROUTER_CLIENT, REPEATER
                    is_router = True
            elif role in ['ROUTER', 'REPEATER', 'ROUTER_CLIENT']:
                is_router = True
            
            pos = get_val(node, 'position', {})
            lat = get_val(pos, 'latitude')
            lon = get_val(pos, 'longitude')
            
            if is_router and lat is not None and lon is not None:
                routers.append({
                    'id': node_id,
                    'name': get_node_name(node, node_id),
                    'lat': lat,
                    'lon': lon
                })
        
        # Compare every pair
        for i in range(len(routers)):
            for j in range(i + 1, len(routers)):
                r1 = routers[i]
                r2 = routers[j]
                dist = haversine(r1['lat'], r1['lon'], r2['lat'], r2['lon'])
                
                if dist > 0 and dist < 500: # 500 meters threshold
                    issues.append(f"Topology: High Density! Routers '{r1['name']}' and '{r2['name']}' are only {dist:.0f}m apart. Consider changing one to CLIENT.")
        
        return issues

    def check_network_size_and_preset(self, nodes):
        """
        Checks if network size exceeds recommendations for the current preset.
        Note: We can't easily know the *current* preset of the network just from node DB,
        but we can warn based on size.
        """
        issues = []
        total_nodes = len(nodes)
        
        if total_nodes > self.max_nodes_long_fast:
             issues.append(f"Network Size: {total_nodes} nodes detected. If using LONG_FAST, consider switching to a faster preset (e.g. LONG_MODERATE or SHORT_FAST) to reduce collision probability.")
             
        return issues

    def check_router_density(self, nodes):
        """
        Checks for high density of routers.
        New Logic: Check for > 2 routers within 2km radius of each other.
        """
        issues = []
        routers = []
        
        # Filter for routers with valid position
        for node_id, node in nodes.items():
            user = get_val(node, 'user', {})
            role = get_val(user, 'role')
            
            is_router = False
            if isinstance(role, int):
                if role in [2, 3, 4, 9]: # ROUTER, ROUTER_CLIENT, REPEATER, ROUTER_LATE
                    is_router = True
            elif role in ['ROUTER', 'REPEATER', 'ROUTER_CLIENT', 'ROUTER_LATE']:
                is_router = True
            
            pos = get_val(node, 'position', {})
            lat = get_val(pos, 'latitude')
            lon = get_val(pos, 'longitude')
            
            if is_router and lat is not None and lon is not None:
                routers.append({
                    'id': node_id,
                    'name': get_node_name(node, node_id),
                    'lat': lat,
                    'lon': lon
                })
        
        # Check density for each router
        reported_pairs = set()
        
        for i, r1 in enumerate(routers):
            nearby_routers = []
            for j, r2 in enumerate(routers):
                if i == j: continue
                
                dist = haversine(r1['lat'], r1['lon'], r2['lat'], r2['lon'])
                if dist < self.router_density_threshold: 
                    nearby_routers.append(r2)
            
            if len(nearby_routers) >= 1:
                # Construct a unique key for this cluster to avoid duplicate messages
                # (Simple approach: just report for the center node)
                names = [r['name'] for r in nearby_routers]
                issues.append(f"Topology: High Router Density! '{r1['name']}' has {len(nearby_routers)} other routers within {self.router_density_threshold}m ({', '.join(names)}). Consider changing some to CLIENT.")

        return issues

    def check_signal_vs_distance(self, nodes, my_node):
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
