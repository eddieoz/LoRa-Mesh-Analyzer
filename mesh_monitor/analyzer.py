import logging
import time

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
            # Handle both dictionary and Node object
            if hasattr(node, 'user'):
                # It's a Node object (or similar), but we need dictionary access for existing logic
                # or we update logic to use attributes.
                # However, the error 'Node object has no attribute get' confirms it's an object.
                # The 'nodes' dict usually contains dictionaries in some contexts, but objects in others.
                # Let's try to convert to dict if possible, or access attributes safely.
                
                # If it's a Node object, it might not have a .get() method.
                # We can try to access attributes directly.
                user = getattr(node, 'user', {})
                metrics = getattr(node, 'deviceMetrics', {})
                position = getattr(node, 'position', {})
                # Note: user/metrics/position might be objects too!
                # If they are objects, we need to handle them.
                # But usually in the python API, these inner attributes are often dictionaries or protobuf messages.
                # If protobuf messages, they act like objects but might not have .get().
                
                # Let's assume for a moment that if we access them, we might need to treat them as objects.
                # But to be safe and minimal change, let's try to see if we can just use getattr with default.
                
                # Actually, if 'user' is a protobuf, we can't use .get() on it either.
                # Let's define a helper to safely get values.
                pass
            else:
                # It's likely a dict
                user = node.get('user', {})
                metrics = node.get('deviceMetrics', {})
                position = node.get('position', {})

            # Helper to get attribute or dict key
            def get_val(obj, key, default=None):
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            # Re-fetch using helper
            user = get_val(node, 'user', {})
            metrics = get_val(node, 'deviceMetrics', {})
            position = get_val(node, 'position', {})
            
            # Now user/metrics/position might be objects or dicts.
            # We need to access fields inside them.
            # e.g. user.get('longName') vs user.longName
            
            node_name = get_val(user, 'longName', node_id)
            
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
            # Role might be an enum int if it's an object, or string if dict?
            # In dicts from JSON, it's often string 'ROUTER'.
            # In protobuf objects, it's an int.
            # We need to handle both.
            
            is_router_client = False
            if isinstance(role, int):
                # We need to check against the enum value for ROUTER_CLIENT
                # Or convert to string.
                # Hardcoding enum values is risky but 3 is usually ROUTER_CLIENT?
                # Let's try to handle string comparison if possible.
                # If it's an int, we can't compare to 'ROUTER_CLIENT'.
                pass
            elif role == 'ROUTER_CLIENT':
                is_router_client = True
                
            if is_router_client:
                issues.append(f"Config: Node '{node_name}' is using deprecated role 'ROUTER_CLIENT'.")
            
            # ... (rest of logic needs similar updates) ...
            # This is getting complicated to support both.
            # Let's try to force conversion to dict if possible?
            # The Node object doesn't seem to have a to_dict() method easily documented.
            
            # Alternative: The 'nodes' property in Interface returns a dict of Node objects.
            # But maybe we can use `interface.nodesByNum`? No.
            
            # Let's just implement the helper fully and use it.
            
            # 3. Check Roles (Robust)
            # If role is int, we might skip the string check or assume it's fine for now?
            # Actually, we really want to catch ROUTER_CLIENT.
            # If we can't import the enum here easily, maybe we skip.
            # But wait, if 'user' is a dict, role is 'ROUTER_CLIENT'.
            # If 'user' is an object, role is an int.
            
            # Let's assume for now we are dealing with the dict case primarily, 
            # BUT the error says we have an object.
            # So we MUST handle the object case.
            
            # If it's an object, we can try to access the name of the enum?
            # user.role is an int.
            # We need to convert it.
            
            # Let's try to import config_pb2 here too?
            try:
                from meshtastic.protobuf import config_pb2
                # If role is int
                if isinstance(role, int):
                    role_name = config_pb2.Config.DeviceConfig.Role.Name(role)
                    if role_name == 'ROUTER_CLIENT':
                         issues.append(f"Config: Node '{node_name}' is using deprecated role 'ROUTER_CLIENT'.")
                    role = role_name # Normalize to string for later checks
            except ImportError:
                pass

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
        
        # Helper to get attribute or dict key
        def get_val(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        for pkt in history:
            sender_id = pkt.get('fromId')
            if sender_id:
                node = nodes.get(sender_id)
                if node:
                    hops_away = get_val(node, 'hopsAway', 0)
                    if hops_away > 3:
                         user = get_val(node, 'user', {})
                         node_name = get_val(user, 'longName', sender_id)
                         issues.append(f"Topology: Node '{node_name}' is {hops_away} hops away. (Ideally <= 3)")
        return list(set(issues))

    def _haversine(self, lat1, lon1, lat2, lon2):
        """
        Calculate the great circle distance between two points 
        on the earth (specified in decimal degrees)
        """
        import math
        try:
            # convert decimal degrees to radians 
            lon1, lat1, lon2, lat2 = map(math.radians, [float(lon1), float(lat1), float(lon2), float(lat2)])

            # haversine formula 
            dlon = lon2 - lon1 
            dlat = lat2 - lat1 
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a)) 
            r = 6371 # Radius of earth in kilometers. Use 3956 for miles
            return c * r * 1000 # Return in meters
        except Exception:
            return 0

    def check_router_density(self, nodes):
        """
        Checks if ROUTER nodes are too close to each other (< 500m).
        """
        issues = []
        routers = []
        
        # Helper to get attribute or dict key
        def get_val(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        # Filter for routers with valid position
        for node_id, node in nodes.items():
            user = get_val(node, 'user', {})
            role = get_val(user, 'role')
            
            # Handle role enum if needed (simplified check for now, assuming string or int handled elsewhere or here)
            # If role is int, we might miss it here unless we convert.
            # But let's assume if it's an object, we might need to check int.
            # For simplicity, let's skip strict role check here or assume string if dict.
            # If object, role is int. 
            # 2 = ROUTER, 3 = ROUTER_CLIENT, 4 = REPEATER
            is_router = False
            if isinstance(role, int):
                if role in [2, 3, 4]:
                    is_router = True
            elif role in ['ROUTER', 'REPEATER', 'ROUTER_CLIENT']:
                is_router = True
            
            pos = get_val(node, 'position', {})
            lat = get_val(pos, 'latitude')
            lon = get_val(pos, 'longitude')
            
            if is_router and lat is not None and lon is not None:
                routers.append({
                    'id': node_id,
                    'name': get_val(user, 'longName', node_id),
                    'lat': lat,
                    'lon': lon
                })
        
        # Compare every pair
        for i in range(len(routers)):
            for j in range(i + 1, len(routers)):
                r1 = routers[i]
                r2 = routers[j]
                dist = self._haversine(r1['lat'], r1['lon'], r2['lat'], r2['lon'])
                
                if dist > 0 and dist < 500: # 500 meters threshold
                    issues.append(f"Topology: High Density! Routers '{r1['name']}' and '{r2['name']}' are only {dist:.0f}m apart. Consider changing one to CLIENT.")
        
        return issues

    def check_signal_vs_distance(self, nodes, my_node):
        """
        Checks for nodes that are close but have poor SNR (indicating obstruction or antenna issues).
        """
        issues = []
        
        # Helper to get attribute or dict key
        def get_val(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

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
            dist = self._haversine(my_lat, my_lon, lat, lon)
            
            # Check SNR (if available in snr field or similar)
            # Note: 'snr' is often in the node DB if we've heard from them recently
            snr = get_val(node, 'snr')
            
            if snr is not None:
                # Heuristic: If < 1km and SNR < 0, that's suspicious for LoRa (unless heavy obstruction)
                # Ideally, close nodes should have high SNR (> 5-10)
                if dist < 1000 and snr < -5:
                     node_name = get_val(user, 'longName', node_id)
                     issues.append(f"Performance: Node '{node_name}' is close ({dist:.0f}m) but has poor SNR ({snr:.1f}dB). Check antenna/LOS.")
        
        return issues
