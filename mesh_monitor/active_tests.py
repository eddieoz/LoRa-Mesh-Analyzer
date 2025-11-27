import logging
import time
import meshtastic.util

logger = logging.getLogger(__name__)

class ActiveTester:
    def __init__(self, interface, priority_nodes=None, auto_discovery_roles=None, auto_discovery_limit=5, online_nodes=None, local_node_id=None):
        self.interface = interface
        self.priority_nodes = priority_nodes if priority_nodes else []
        self.auto_discovery_roles = auto_discovery_roles if auto_discovery_roles else ['ROUTER', 'REPEATER']
        self.auto_discovery_limit = auto_discovery_limit
        self.online_nodes = online_nodes if online_nodes else set()
        self.local_node_id = local_node_id
        self.last_test_time = 0
        self.min_test_interval = 60 # Seconds between active tests
        self.current_priority_index = 0
        self.pending_traceroute = None # Store ID of node we are waiting for
        self.traceroute_timeout = 60 # Seconds to wait for a response
        
        # Reporting Data
        self.test_results = [] # List of dicts: {node_id, status, rtt, hops, snr, timestamp}
        self.completed_cycles = 0
        self.nodes_tested_in_cycle = set()

    def run_next_test(self):
        """
        Runs the next scheduled test. Prioritizes nodes in the config list.
        """
        # If no priority nodes, try auto-discovery
        if not self.priority_nodes:
            self.priority_nodes = self._auto_discover_nodes()
            if not self.priority_nodes:
                return # Still no nodes found

        current_time = time.time()

        # Check if we are waiting for a timeout
        if self.pending_traceroute:
            if current_time - self.last_test_time < self.traceroute_timeout:
                # Still waiting, don't send new one
                return
            else:
                logger.warning(f"Traceroute to {self.pending_traceroute} timed out.")
                # Record the timeout
                self.record_timeout(self.pending_traceroute)

        # Check throttling
        if current_time - self.last_test_time < self.min_test_interval:
            return

        # Round-robin through priority nodes
        # Safety check if list changed or index out of bounds
        # Safety check if list changed or index out of bounds
        if self.current_priority_index >= len(self.priority_nodes):
            self.current_priority_index = 0
            
        node_id = self.priority_nodes[self.current_priority_index]
        logger.info(f"Active Test Queue: {self.priority_nodes} (Index: {self.current_priority_index})")
        self.send_traceroute(node_id)
        
        self.current_priority_index = (self.current_priority_index + 1) % len(self.priority_nodes)

    def _auto_discover_nodes(self):
        """
        Selects nodes based on lastHeard timestamp, roles, and geolocation.
        Uses the existing node database instead of waiting for packets.
        """
        candidates = []
        nodes = self.interface.nodes
        
        # Helper to get attribute or dict key (same as in analyzer)
        def get_val(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        # Get local position
        my_lat = None
        my_lon = None
        if hasattr(self.interface, 'localNode'):
            # localNode is a Node object, need to look it up in nodes dict
            local_node_id = None
            if hasattr(self.interface.localNode, 'nodeNum'):
                local_node_id = f"!{self.interface.localNode.nodeNum:08x}"
                logger.debug(f"Local node ID from nodeNum: {local_node_id}")
            
            if local_node_id and local_node_id in nodes:
                local_node_data = nodes[local_node_id]
                pos = get_val(local_node_data, 'position', {})
                
                # Try float first
                my_lat = get_val(pos, 'latitude')
                my_lon = get_val(pos, 'longitude')
                
                # Fallback to int
                if my_lat is None:
                    lat_i = get_val(pos, 'latitude_i') or get_val(pos, 'latitudeI')
                    if lat_i is not None:
                        my_lat = lat_i / 1e7
                
                if my_lon is None:
                    lon_i = get_val(pos, 'longitude_i') or get_val(pos, 'longitudeI')
                    if lon_i is not None:
                        my_lon = lon_i / 1e7
                        
                logger.info(f"Local node position: lat={my_lat}, lon={my_lon}")
            else:
                logger.warning(f"Local node {local_node_id} not found in nodes dict or no nodeNum")
        else:
            logger.warning("No localNode attribute on interface")

        # Filter nodes by lastHeard, role, and calculate distance
        for node_id, node in nodes.items():
            # Skip self
            my_id = self.local_node_id
            
            # Fallback if not passed
            if not my_id:
                if hasattr(self.interface, 'localNode'):
                    my_id = get_val(get_val(self.interface.localNode, 'user', {}), 'id')
                if not my_id and hasattr(self.interface, 'myNode'):
                     my_id = get_val(get_val(self.interface.myNode, 'user', {}), 'id')

            if my_id:
                # Normalize IDs (remove leading !)
                my_id_norm = my_id.lstrip('!')
                node_id_norm = node_id.lstrip('!')
                
                if node_id_norm == my_id_norm:
                    logger.debug(f"Skipping self: {node_id} (Matches local {my_id})")
                    continue

            # Filter by lastHeard - only include nodes that have been heard
            last_heard = get_val(node, 'lastHeard')
            if not last_heard or last_heard == 0:
                logger.debug(f"Skipping {node_id}: No lastHeard data")
                continue

            # Filter by Role
            user = get_val(node, 'user', {})
            role = get_val(user, 'role', 'CLIENT')
            
            # Convert role to string if int
            if isinstance(role, int):
                try:
                    from meshtastic.protobuf import config_pb2
                    role = config_pb2.Config.DeviceConfig.Role.Name(role)
                except:
                    pass # Keep as int or whatever
            
            if role not in self.auto_discovery_roles:
                logger.debug(f"Skipping {node_id}: Role {role} not in {self.auto_discovery_roles}")
                continue
            
            # Calculate distance if possible
            dist = 0
            pos = get_val(node, 'position', {})
            
            # Try float coordinates first
            lat = get_val(pos, 'latitude')
            lon = get_val(pos, 'longitude')
            
            # Fallback to integer coordinates (divide by 1e7)
            if lat is None:
                lat_i = get_val(pos, 'latitude_i') or get_val(pos, 'latitudeI')
                if lat_i is not None:
                    lat = lat_i / 1e7
            
            if lon is None:
                lon_i = get_val(pos, 'longitude_i') or get_val(pos, 'longitudeI')
                if lon_i is not None:
                    lon = lon_i / 1e7
            
            if my_lat is not None and my_lon is not None and lat is not None and lon is not None:
                dist = self._haversine(my_lat, my_lon, lat, lon)
            
            candidates.append({
                'id': node_id,
                'dist': dist,
                'lastHeard': last_heard,
                'role': role
            })

        if not candidates:
            logger.warning("No candidate nodes found matching criteria (role, lastHeard)")
            return []

        # Sort by distance (Descending - Furthest First)
        candidates.sort(key=lambda x: x['dist'], reverse=True)
        
        # Select Top N (Furthest)
        limit = self.auto_discovery_limit
        selected = candidates[:limit]
        
        # Log the selection with distances and lastHeard
        logger.info(f"Auto-discovered {len(selected)} targets from node database:")
        for c in selected:
            logger.info(f"  - {c['id']} ({c['dist']/1000:.2f}km, role={c['role']}, lastHeard={c['lastHeard']})")
        
        # Return just the IDs
        selected_ids = [c['id'] for c in selected]
        return selected_ids

    def _haversine(self, lat1, lon1, lat2, lon2):
        import math
        try:
            lon1, lat1, lon2, lat2 = map(math.radians, [float(lon1), float(lat1), float(lon2), float(lat2)])
            dlon = lon2 - lon1 
            dlat = lat2 - lat1 
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a)) 
            r = 6371000 # Meters
            return c * r
        except:
            return 0

    def send_traceroute(self, dest_node_id):
        """
        Sends a traceroute request to the destination node.
        Runs in a separate thread to avoid blocking the main loop.
        """
        logger.info(f"Sending traceroute to priority node {dest_node_id}...")
        
        def _send_task():
            try:
                self.interface.sendTraceRoute(dest_node_id, hopLimit=7)
                logger.debug(f"Traceroute command sent to {dest_node_id}")
            except Exception as e:
                logger.error(f"Failed to send traceroute to {dest_node_id}: {e}")

        # Update state immediately so main loop knows we are busy
        self.last_test_time = time.time()
        self.pending_traceroute = dest_node_id
        
        # Start background thread
        import threading
        t = threading.Thread(target=_send_task, daemon=True)
        t.start() 

    def record_result(self, node_id, packet, rtt=None):
        """
        Records a successful test result.
        """
        logger.info(f"Recording success for {node_id}")
        
        # Extract route information from traceroute packet
        decoded = packet.get('decoded', {})
        
        logger.debug(f"Decoded packet keys: {list(decoded.keys())}")
        
        # The traceroute data is in decoded['traceroute'] (parsed by library)
        # or in RouteDiscovery protobuf in payload (if raw)
        route = []
        route_back = []
        
        # 1. Check for pre-parsed 'traceroute' dict (Meshtastic python lib does this)
        if 'traceroute' in decoded:
            tr = decoded['traceroute']
            if isinstance(tr, dict):
                route = tr.get('route', [])
                route_back = tr.get('routeBack', [])
                logger.debug(f"Found parsed traceroute: route={route}, route_back={route_back}")
        
        # 2. Fallback: Try to parse RouteDiscovery protobuf from payload
        elif 'payload' in decoded:
            try:
                from meshtastic import mesh_pb2
                # If payload is bytes, parse it
                if isinstance(decoded['payload'], bytes):
                    route_discovery = mesh_pb2.RouteDiscovery()
                    route_discovery.ParseFromString(decoded['payload'])
                    route = list(route_discovery.route)
                    route_back = list(route_discovery.route_back)
                    logger.debug(f"Parsed from bytes - route: {route}, route_back: {route_back}")
                # If it's already a protobuf object
                elif hasattr(decoded['payload'], 'route'):
                    route = list(decoded['payload'].route)
                    route_back = list(decoded['payload'].route_back)
                    logger.debug(f"Extracted from protobuf - route: {route}, route_back: {route_back}")
            except Exception as e:
                logger.debug(f"Could not parse RouteDiscovery protobuf: {e}")
        
        # 3. Fallback: Old dict keys
        if not route:
            route = decoded.get('route', [])
            route_back = decoded.get('routeBack', [])
        
        # Count hops (number of nodes in route - 1, excluding source)
        # Route includes: source -> hop1 -> hop2 -> destination
        # So hops = len(route) - 1 (we don't count the source)
        hops_to = len(route) - 1 if route and len(route) > 0 else 0
        hops_back = len(route_back) - 1 if route_back and len(route_back) > 0 else 0
        
        # Convert route node numbers to hex IDs for logging
        route_ids = [f"!{node:08x}" if isinstance(node, int) else str(node) for node in route]
        route_back_ids = [f"!{node:08x}" if isinstance(node, int) else str(node) for node in route_back]
        
        logger.info(f"Route to {node_id}: {' -> '.join(route_ids)} ({hops_to} hops)")
        logger.info(f"Route back: {' -> '.join(route_back_ids)} ({hops_back} hops)")
        
        self.test_results.append({
            'node_id': node_id,
            'status': 'success',
            'rtt': rtt,
            'hops_to': hops_to,
            'hops_back': hops_back,
            'route': route_ids,
            'route_back': route_back_ids,
            'snr': packet.get('rxSnr', 0),
            'timestamp': time.time()
        })
        self._check_cycle_completion(node_id)
        if self.pending_traceroute == node_id:
            self.pending_traceroute = None # Clear pending if this was the node we were waiting for

    def record_timeout(self, node_id):
        """
        Records a failed test result (timeout).
        """
        logger.info(f"Recording timeout for {node_id}")
        self.test_results.append({
            'node_id': node_id,
            'status': 'timeout',
            'timestamp': time.time()
        })
        self._check_cycle_completion(node_id)
        if self.pending_traceroute == node_id:
            self.pending_traceroute = None # Clear pending if this was the node we were waiting for

    def _check_cycle_completion(self, node_id):
        """
        Tracks which nodes have been tested in the current cycle.
        """
        self.nodes_tested_in_cycle.add(node_id)
        
        # Check if we have tested all priority nodes
        # Note: priority_nodes might change if auto-discovery re-runs, 
        # but usually it's stable for a cycle.
        if self.priority_nodes:
            all_tested = all(n in self.nodes_tested_in_cycle for n in self.priority_nodes)
            logger.debug(f"Cycle Progress: {len(self.nodes_tested_in_cycle)}/{len(self.priority_nodes)} nodes tested.")
            if all_tested:
                self.completed_cycles += 1
                logger.info(f"Completed Test Cycle {self.completed_cycles}")
                self.nodes_tested_in_cycle.clear()

    def flood_test(self, dest_node_id, count=5):
        """
        CAUTION: Sends multiple messages to test reliability.
        """
        logger.warning(f"Starting FLOOD TEST to {dest_node_id} (Count: {count})")
        for i in range(count):
            self.interface.sendText(f"Flood test {i+1}/{count}", destinationId=dest_node_id)
            time.sleep(5) # Wait 5 seconds between messages
