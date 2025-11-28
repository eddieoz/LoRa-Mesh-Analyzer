import logging
import time
import threading
import meshtastic.util
from .utils import get_val, haversine

logger = logging.getLogger(__name__)

class ActiveTester:
    def __init__(self, interface, priority_nodes=None, auto_discovery_roles=None, auto_discovery_limit=5, online_nodes=None, local_node_id=None, traceroute_timeout=60, test_interval=30, analysis_mode='distance', cluster_radius=2000):
        self.interface = interface
        self.priority_nodes = priority_nodes if priority_nodes else []
        self.auto_discovery_roles = auto_discovery_roles if auto_discovery_roles else ['ROUTER', 'REPEATER']
        self.auto_discovery_limit = auto_discovery_limit
        self.online_nodes = online_nodes if online_nodes else set()
        self.local_node_id = local_node_id
        self.last_test_time = 0
        self.min_test_interval = test_interval # Seconds between active tests
        self.current_priority_index = 0
        self.pending_traceroute = None # Store ID of node we are waiting for
        self.traceroute_timeout = traceroute_timeout # Seconds to wait for a response
        self.analysis_mode = analysis_mode
        self.cluster_radius = cluster_radius
        
        # Reporting Data
        self.test_results = [] # List of dicts: {node_id, status, rtt, hops, snr, timestamp}
        self.completed_cycles = 0
        self.nodes_tested_in_cycle = set()
        
        # Thread safety
        self.lock = threading.Lock()

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
        if self.analysis_mode == 'router_clusters':
            return self._get_router_cluster_nodes()

        candidates = []
        nodes = self.interface.nodes
        
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

        # Group candidates by role
        from collections import defaultdict
        nodes_by_role = defaultdict(list)

        # Filter nodes and calculate distance
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

            # Get Role
            user = get_val(node, 'user', {})
            role = get_val(user, 'role', 'CLIENT')
            
            # Convert role to string if int
            if isinstance(role, int):
                try:
                    from meshtastic.protobuf import config_pb2
                    role = config_pb2.Config.DeviceConfig.Role.Name(role)
                except:
                    pass # Keep as int or whatever
            
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
                dist = haversine(my_lat, my_lon, lat, lon)
            
            # Add to bucket
            nodes_by_role[role].append({
                'id': node_id,
                'dist': dist,
                'lastHeard': last_heard,
                'role': role
            })

        # Select nodes based on role priority
        final_candidates = []
        limit = self.auto_discovery_limit
        
        logger.info(f"Selecting up to {limit} nodes based on role priority: {self.auto_discovery_roles}")

        for role_priority in self.auto_discovery_roles:
            if len(final_candidates) >= limit:
                break
                
            candidates_for_role = nodes_by_role.get(role_priority, [])
            if not candidates_for_role:
                continue
                
            # Sort by lastHeard (Descending - Most Recent) then Distance (Descending - Furthest)
            candidates_for_role.sort(key=lambda x: (x['lastHeard'], x['dist']), reverse=True)
            
            # Add to final list
            remaining_slots = limit - len(final_candidates)
            to_add = candidates_for_role[:remaining_slots]
            final_candidates.extend(to_add)
            
            logger.info(f"  Added {len(to_add)} nodes with role {role_priority}")

        if not final_candidates:
            logger.warning("No candidate nodes found matching criteria.")
            return []

        # Log the selection
        logger.info(f"Auto-discovered {len(final_candidates)} targets:")
        for c in final_candidates:
            logger.info(f"  - {c['id']} ({c['dist']/1000:.2f}km, role={c['role']}, lastHeard={c['lastHeard']})")
        
        # Return just the IDs
        selected_ids = [c['id'] for c in final_candidates]
        return selected_ids

    def _get_router_cluster_nodes(self):
        """
        Selects nodes that are within cluster_radius of known routers.
        """
        logger.info(f"Auto-discovery mode: Router Clusters (Radius: {self.cluster_radius}m)")
        nodes = self.interface.nodes
        routers = []
        
        # 1. Identify Routers with Position
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
                
                # Handle integer coordinates if needed
                if lat is None:
                    lat_i = get_val(pos, 'latitude_i') or get_val(pos, 'latitudeI')
                    if lat_i is not None: lat = lat_i / 1e7
                if lon is None:
                    lon_i = get_val(pos, 'longitude_i') or get_val(pos, 'longitudeI')
                    if lon_i is not None: lon = lon_i / 1e7

                if lat is not None and lon is not None:
                    routers.append({
                        'id': node_id,
                        'lat': lat,
                        'lon': lon
                    })
        
        logger.info(f"Found {len(routers)} routers with position.")
        
        # 2. Find Neighbors for each Router
        candidates = set()
        
        for r in routers:
            for node_id, node in nodes.items():
                if node_id == r['id']: continue
                
                # Check if we should ignore this node (e.g. no lastHeard)
                last_heard = get_val(node, 'lastHeard')
                if not last_heard: continue

                pos = get_val(node, 'position', {})
                lat = get_val(pos, 'latitude')
                lon = get_val(pos, 'longitude')
                
                # Handle integer coordinates
                if lat is None:
                    lat_i = get_val(pos, 'latitude_i') or get_val(pos, 'latitudeI')
                    if lat_i is not None: lat = lat_i / 1e7
                if lon is None:
                    lon_i = get_val(pos, 'longitude_i') or get_val(pos, 'longitudeI')
                    if lon_i is not None: lon = lon_i / 1e7
                
                if lat is not None and lon is not None:
                    dist = haversine(r['lat'], r['lon'], lat, lon)
                    if dist <= self.cluster_radius:
                        candidates.add(node_id)
        
        # 3. Select Nodes
        # Convert to list and sort/limit
        candidate_list = list(candidates)
        
        # Sort by lastHeard (most recent first)
        candidate_list.sort(key=lambda nid: get_val(nodes[nid], 'lastHeard', 0), reverse=True)
        
        selected = candidate_list[:self.auto_discovery_limit]
        logger.info(f"Selected {len(selected)} nodes near routers: {selected}")
        
        return selected

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
        with self.lock:
            self.last_test_time = time.time()
            self.pending_traceroute = dest_node_id
        
        # Start background thread
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
        
        # 3. Fallback: Old dict keys (only if not already parsed)
        if not route:
            route = decoded.get('route', [])
        if not route_back:
            route_back = decoded.get('routeBack', [])
        
        # Count hops (intermediate relay nodes only, route excludes source and destination)
        hops_to = len(route) if route else 0
        hops_back = len(route_back) if route_back else 0
        
        # Convert route node numbers to hex IDs for logging
        route_ids = [f"!{node:08x}" if isinstance(node, int) else str(node) for node in route]
        route_back_ids = [f"!{node:08x}" if isinstance(node, int) else str(node) for node in route_back]
        
        logger.info(f"Route to {node_id}: {' -> '.join(route_ids)} ({hops_to} hops)")
        logger.info(f"Route back: {' -> '.join(route_back_ids)} ({hops_back} hops)")
        
        with self.lock:
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
                self.last_test_time = time.time() # Start cooldown

    def record_timeout(self, node_id):
        """
        Records a failed test result (timeout).
        """
        logger.info(f"Recording timeout for {node_id}")
        with self.lock:
            self.test_results.append({
                'node_id': node_id,
                'status': 'timeout',
                'timestamp': time.time()
            })
            self._check_cycle_completion(node_id)
            if self.pending_traceroute == node_id:
                self.pending_traceroute = None # Clear pending if this was the node we were waiting for
                self.last_test_time = time.time() # Start cooldown

    def _check_cycle_completion(self, node_id):
        """
        Tracks which nodes have been tested in the current cycle.
        Must be called within a lock.
        """
        self.nodes_tested_in_cycle.add(node_id)
        
        # Check if we have tested all priority nodes
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
