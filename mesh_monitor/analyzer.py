import logging
import time
from .utils import get_val, haversine, get_node_name

logger = logging.getLogger(__name__)

class NetworkHealthAnalyzer:
    def __init__(self, ignore_no_position=False):
        self.ch_util_threshold = 25.0
        self.air_util_threshold = 10.0
        self.ignore_no_position = ignore_no_position

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
                issues.append(f"Spam: Node '{node_name}' AirUtilTx {air_util:.1f}% (Threshold: {self.air_util_threshold}%)")

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
        if my_node:
            issues.extend(self.check_signal_vs_distance(nodes, my_node))

        return issues

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
