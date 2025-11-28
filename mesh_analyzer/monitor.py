import time
import sys
import threading
import logging
from pubsub import pub
import meshtastic.serial_interface
import meshtastic.tcp_interface
import meshtastic.util
from .analyzer import NetworkHealthAnalyzer
from .active_tests import ActiveTester
from .reporter import NetworkReporter

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

import yaml
import os

# ... imports ...

class MeshMonitor:
    def __init__(self, interface_type='serial', hostname=None, ignore_no_position=False, config_file='config.yaml'):
        self.interface = None
        self.interface_type = interface_type
        self.hostname = hostname
        self.config = self.load_config(config_file)
        self.analyzer = NetworkHealthAnalyzer(config=self.config, ignore_no_position=ignore_no_position)
        self.reporter = NetworkReporter(report_dir="reports", config=self.config)
        self.active_tester = None 
        self.running = False
        self.config = self.load_config(config_file)
        self.packet_history = [] # List of recent packets for duplication check
        
        # Configure Log Level
        log_level_str = self.config.get('log_level', 'info').upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        logger.setLevel(log_level)
        logging.getLogger().setLevel(log_level) # Set root logger too to capture lib logs if needed
        logger.info(f"Log level set to: {log_level_str}")
        self.last_analysis_time = 0
        
        # Discovery State
        self.discovery_mode = False
        self.discovery_start_time = 0
        self.discovery_wait_seconds = self.config.get('discovery_wait_seconds', 60)
        self.online_nodes = set()

    def load_config(self, config_file):
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Error loading config file: {e}")
        return {}

    def start(self):
        logger.info(f"Connecting to Meshtastic node via {self.interface_type}...")
        try:
            # ... interface init ...
            if self.interface_type == 'serial':
                self.interface = meshtastic.serial_interface.SerialInterface()
            elif self.interface_type == 'tcp':
                if not self.hostname:
                    raise ValueError("Hostname required for TCP interface")
                self.interface = meshtastic.tcp_interface.TCPInterface(self.hostname)
            else:
                raise ValueError(f"Unknown interface type: {self.interface_type}")

            # Check local config
            self.check_local_config()

            priority_nodes = self.config.get('priority_nodes', [])
            auto_discovery_roles = self.config.get('auto_discovery_roles', ['ROUTER', 'REPEATER'])
            auto_discovery_limit = self.config.get('auto_discovery_limit', 5)

            # ... subscriptions ...
            pub.subscribe(self.on_receive, "meshtastic.receive")
            pub.subscribe(self.on_connection, "meshtastic.connection.established")
            pub.subscribe(self.on_node_info, "meshtastic.node.updated")

            logger.info("Connected to node.")
            self.running = True
            
            # Start Discovery Phase if no priority nodes are set
            if not priority_nodes:
                logger.info("Auto-discovery mode: Using node database to select targets...")
                logger.info(f"Will select up to {auto_discovery_limit} nodes matching roles: {auto_discovery_roles}")
                
                # Get Local Node ID for self-exclusion
                local_id = None
                try:
                    # Try myInfo first (protobuf object with my_node_num attribute)
                    if hasattr(self.interface, 'myInfo') and self.interface.myInfo:
                        my_node_num = getattr(self.interface.myInfo, 'my_node_num', None)
                        if my_node_num:
                            # Convert decimal node number to hex ID format (!42bb5074)
                            local_id = f"!{my_node_num:08x}"
                    
                    # Fallback: use localNode
                    if not local_id and hasattr(self.interface, 'localNode') and self.interface.localNode:
                        if hasattr(self.interface.localNode, 'user'):
                            local_id = getattr(self.interface.localNode.user, 'id', None)
                        elif isinstance(self.interface.localNode, dict):
                            local_id = self.interface.localNode.get('user', {}).get('id')
                    
                    logger.info(f"Local Node ID: {local_id}")
                except Exception as e:
                    logger.warning(f"Could not retrieve local node ID: {e}")

                # Create ActiveTester with auto-discovery (no online_nodes needed)
                traceroute_timeout = self.config.get('traceroute_timeout', 60)
                test_interval = self.config.get('active_test_interval', 30)
                analysis_mode = self.config.get('analysis_mode', 'distance')
                cluster_radius = self.config.get('cluster_radius', 2000)
                
                self.active_tester = ActiveTester(
                    self.interface, 
                    priority_nodes=[],  # Empty - will trigger auto-discovery
                    auto_discovery_roles=auto_discovery_roles,
                    auto_discovery_limit=auto_discovery_limit,
                    online_nodes=set(),  # Not used anymore - discovery uses lastHeard
                    local_node_id=local_id,
                    traceroute_timeout=traceroute_timeout,
                    test_interval=test_interval,
                    analysis_mode=analysis_mode,
                    cluster_radius=cluster_radius
                )
                
                logger.info("Active testing started with auto-discovered nodes.")

            else:
                 # Direct start if priority nodes exist
                 logger.info(f"Loaded {len(priority_nodes)} priority nodes for active testing.")
                 
                 # Get Local Node ID explicitly
                 local_id = None
                 try:
                     # Try myInfo first (protobuf object with my_node_num attribute)
                     if hasattr(self.interface, 'myInfo') and self.interface.myInfo:
                         my_node_num = getattr(self.interface.myInfo, 'my_node_num', None)
                         if my_node_num:
                             # Convert decimal node number to hex ID format (!42bb5074)
                             local_id = f"!{my_node_num:08x}"
                     
                     # Fallback: use localNode
                     if not local_id and hasattr(self.interface, 'localNode') and self.interface.localNode:
                         if hasattr(self.interface.localNode, 'user'):
                             local_id = getattr(self.interface.localNode.user, 'id', None)
                         elif isinstance(self.interface.localNode, dict):
                             local_id = self.interface.localNode.get('user', {}).get('id')
                     
                     logger.info(f"Local Node ID: {local_id}")
                 except Exception as e:
                     logger.warning(f"Could not retrieve local node ID: {e}")

                 traceroute_timeout = self.config.get('traceroute_timeout', 60)
                 test_interval = self.config.get('active_test_interval', 30)
                 analysis_mode = self.config.get('analysis_mode', 'distance')
                 cluster_radius = self.config.get('cluster_radius', 2000)

                 self.active_tester = ActiveTester(
                    self.interface, 
                    priority_nodes=priority_nodes,
                    auto_discovery_roles=auto_discovery_roles,
                    auto_discovery_limit=auto_discovery_limit,
                    local_node_id=local_id,
                    traceroute_timeout=traceroute_timeout,
                    test_interval=test_interval,
                    analysis_mode=analysis_mode,
                    cluster_radius=cluster_radius
                )

            self.main_loop()

        except Exception as e:
            logger.error(f"Failed to connect or run: {e}")
            self.stop()

    def check_local_config(self):
        """
        Analyzes the local node's configuration and warns about non-optimal settings.
        """
        logger.info("Checking local node configuration...")
        try:
            # Wait a moment for node to populate if needed (though interface init usually does it)
            node = None
            if hasattr(self.interface, 'localNode'):
                node = self.interface.localNode
            
            if not node:
                logger.warning("Could not access local node information.")
                return

            # 1. Check Role
            # We access the protobuf config directly
            try:
                # Note: node.config might be a property of the node object
                # In some versions, it's node.localConfig
                # Let's try to access it safely
                if hasattr(node, 'config'):
                    config = node.config
                elif hasattr(node, 'localConfig'):
                    config = node.localConfig
                else:
                    logger.warning("Could not find config attribute on local node.")
                    return

                from meshtastic.protobuf import config_pb2
                role = config.device.role
                role_name = config_pb2.Config.DeviceConfig.Role.Name(role)
                
                if role_name in ['ROUTER', 'ROUTER_CLIENT', 'REPEATER']:
                    logger.warning(f" [!] Local Node Role is '{role_name}'.")
                    logger.warning("     Recommended for monitoring: 'CLIENT' or 'CLIENT_MUTE'.")
                    logger.warning("     (Active monitoring works best when the monitor itself isn't a router)")
                else:
                    logger.info(f"Local Node Role: {role_name} (OK)")
            except Exception as e:
                logger.warning(f"Could not verify role: {e}")

            # 2. Check Hop Limit
            try:
                if hasattr(node, 'config'):
                    config = node.config
                elif hasattr(node, 'localConfig'):
                    config = node.localConfig
                
                hop_limit = config.lora.hop_limit
                if hop_limit > 3:
                    logger.warning(f" [!] Local Node Hop Limit is {hop_limit}.")
                    logger.warning("     Recommended: 3. High hop limits can cause network congestion.")
                else:
                    logger.info(f"Local Node Hop Limit: {hop_limit} (OK)")
            except Exception as e:
                logger.warning(f"Could not verify hop limit: {e}")

        except Exception as e:
            logger.error(f"Failed to check local config: {e}")

    def stop(self):
        self.running = False
        if self.interface:
            self.interface.close()

    def on_receive(self, packet, interface):
        try:
            # Store packet for analysis
            # We need: id, fromId, hopLimit (if available)
            pkt_info = {
                'id': packet.get('id'),
                'fromId': packet.get('fromId'),
                'toId': packet.get('toId'),
                'rxTime': packet.get('rxTime', time.time()),
                'hopLimit': packet.get('hopLimit'), # Might be in 'decoded' depending on packet type
                'decoded': packet.get('decoded', {})
            }
            
            # Keep history manageable (e.g., last 100 packets or last minute)
            self.packet_history.append(pkt_info)
            # Prune old packets (older than 60s)
            current_time = time.time()
            self.packet_history = [p for p in self.packet_history if current_time - p['rxTime'] < 60]

            # Track Online Nodes (for Discovery)
            sender_id = packet.get('fromId')
            if sender_id:
                self.online_nodes.add(sender_id)

            if packet.get('decoded', {}).get('portnum') == 'ROUTING_APP':
                # This might be a traceroute response
                pass
            
            # Log interesting packets
            portnum = packet.get('decoded', {}).get('portnum')
            if portnum == 'TEXT_MESSAGE_APP':
                text = packet.get('decoded', {}).get('text', '')
                logger.info(f"Received Message: {text}")
            elif portnum == 'TRACEROUTE_APP': 
                 logger.info(f"Received Traceroute Packet from {packet.get('fromId')}")
                 logger.debug(f"Full packet: {packet}")
                 logger.debug(f"Decoded: {packet.get('decoded', {})}")
                 if self.active_tester:
                     # Calculate RTT if possible (requires original send time, which we track in active_tester)
                     rtt = time.time() - self.active_tester.last_test_time
                     # Pass the full packet so record_result can extract hopLimit and rxSnr
                     self.active_tester.record_result(packet.get('fromId'), packet, rtt=rtt)

        except Exception as e:
            logger.error(f"Error parsing packet: {e}")

    def on_connection(self, interface, topic=pub.AUTO_TOPIC):
        logger.info("Connection established signal received.")

    def on_node_info(self, node, interface):
        # logger.debug(f"Node info updated: {node}")
        pass

    def apply_manual_positions(self, nodes):
        """
        Applies manual positions from config to nodes.
        """
        manual_positions = self.config.get('manual_positions', {})
        if not manual_positions:
            return

        for node_id, pos in manual_positions.items():
            if node_id in nodes:
                node = nodes[node_id]
                # Ensure position dict exists
                if 'position' not in node:
                    node['position'] = {}
                
                # Update position
                if 'lat' in pos and 'lon' in pos:
                    node['position']['latitude'] = pos['lat']
                    node['position']['longitude'] = pos['lon']
                    logger.debug(f"Applied manual position to {node_id}: {pos}")

    def main_loop(self):
        logger.info("Starting monitoring loop...")
        while self.running:
            try:
                # Run Analysis every 60 seconds
                current_time = time.time()
                
                # --- Active Testing & Analysis ---

                if current_time - self.last_analysis_time >= 60:
                    logger.debug("--- Running Network Analysis ---")
                    nodes = self.interface.nodes
                    
                    # Apply Manual Positions
                    self.apply_manual_positions(nodes)
                    
                    # Get local node info for distance calculations
                    my_node = None
                    if hasattr(self.interface, 'localNode'):
                        my_node = self.interface.localNode
                    
                    # Run Analysis
                    test_results = self.active_tester.test_results if self.active_tester else []
                    issues = self.analyzer.analyze(nodes, packet_history=self.packet_history, my_node=my_node, test_results=test_results)
                    
                    # Run Router Efficiency Analysis (using accumulated test results if available)
                    if self.active_tester:
                        issues.extend(self.analyzer.check_router_efficiency(nodes, test_results=self.active_tester.test_results))
                        issues.extend(self.analyzer.check_route_quality(nodes, test_results=self.active_tester.test_results))
                    else:
                        issues.extend(self.analyzer.check_router_efficiency(nodes))
                    
                    # Report Issues
                    if issues:
                        # logger.warning(f"Found {len(issues)} potential issues:")
                        # for issue in issues:
                        #     logger.warning(f"  - {issue}")
                        pass
                    else:
                        logger.debug("No critical issues found in current scan.")
                    
                    self.last_analysis_time = current_time

                # Check for Reporting Trigger
                if self.active_tester:
                    report_cycles = self.config.get('report_cycles', 1)
                    if self.active_tester.completed_cycles >= report_cycles:
                        logger.info(f"Reporting threshold reached ({self.active_tester.completed_cycles} cycles). Generating report...")
                        
                        # Get local node for distance calculations
                        local_node = None
                        if hasattr(self.interface, 'localNode'):
                            local_node = self.interface.localNode
                        
                        # Calculate Router Stats for Report
                        router_stats = self.analyzer.get_router_stats(nodes, self.active_tester.test_results)

                        self.reporter.generate_report(nodes, self.active_tester.test_results, issues if 'issues' in locals() else [], local_node=local_node, router_stats=router_stats, analyzer=self.analyzer)
                        
                        # Reset cycle count and results
                        self.active_tester.completed_cycles = 0
                        self.active_tester.test_results = []
                        
                        logger.info("Report generated. Exiting...")
                        self.running = False
                        break

                # Run Active Tests (checks its own interval)
                if self.active_tester:
                    self.active_tester.run_next_test()

                # Wait for next scan
                time.sleep(1) 
            # ... exceptions ... 
            # ... exceptions ...
            except KeyboardInterrupt:
                logger.info("Stopping monitor...")
                # Generate partial report if we have nodes (even if no test results yet)
                if nodes:
                    logger.info("Generating partial report before exit...")
                    local_node = None
                    if hasattr(self.interface, 'localNode'):
                        local_node = self.interface.localNode
                    
                    # Use whatever results we have (could be empty)
                    results = self.active_tester.test_results if self.active_tester else []
                    
                    router_stats = self.analyzer.get_router_stats(nodes, results)
                    self.reporter.generate_report(nodes, results, issues if 'issues' in locals() else [], local_node=local_node, router_stats=router_stats, analyzer=self.analyzer)
                
                self.stop()
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(10)

def main():
    # Simple CLI for testing
    import argparse
    parser = argparse.ArgumentParser(description='Meshtastic Network Monitor')
    parser.add_argument('--tcp', help='Hostname for TCP connection (e.g. 192.168.1.10)')
    parser.add_argument('--ignore-no-position', action='store_true', help='Ignore routers without position')
    args = parser.parse_args()

    if args.tcp:
        monitor = MeshMonitor(interface_type='tcp', hostname=args.tcp, ignore_no_position=args.ignore_no_position)
    else:
        monitor = MeshMonitor(interface_type='serial', ignore_no_position=args.ignore_no_position)
    
    try:
        monitor.start()
    except KeyboardInterrupt:
        monitor.stop()

if __name__ == "__main__":
    main()
