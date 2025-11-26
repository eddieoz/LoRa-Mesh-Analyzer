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
        self.analyzer = NetworkHealthAnalyzer(ignore_no_position=ignore_no_position)
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
            if priority_nodes:
                logger.info(f"Loaded {len(priority_nodes)} priority nodes for active testing.")
            
            self.active_tester = ActiveTester(self.interface, priority_nodes=priority_nodes)
            
            # ... subscriptions ...
            pub.subscribe(self.on_receive, "meshtastic.receive")
            pub.subscribe(self.on_connection, "meshtastic.connection.established")
            pub.subscribe(self.on_node_info, "meshtastic.node.updated")

            logger.info("Connected to node.")
            self.running = True
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

            if packet.get('decoded', {}).get('portnum') == 'ROUTING_APP':
                # This might be a traceroute response
                pass
            
            # Log interesting packets
            portnum = packet.get('decoded', {}).get('portnum')
            if portnum == 'TEXT_MESSAGE_APP':
                text = packet.get('decoded', {}).get('text', '')
                logger.info(f"Received Message: {text}")
            elif portnum == 'TRACEROUTE_APP': 
                 logger.info(f"Received Traceroute Packet: {packet}")

        except Exception as e:
            logger.error(f"Error parsing packet: {e}")

    def on_connection(self, interface, topic=pub.AUTO_TOPIC):
        logger.info("Connection established signal received.")

    def on_node_info(self, node, interface):
        # logger.debug(f"Node info updated: {node}")
        pass

    def main_loop(self):
        logger.info("Starting monitoring loop...")
        while self.running:
            try:
                logger.info("--- Running Network Analysis ---")
                nodes = self.interface.nodes
                
                # Get local node info for distance calculations
                my_node = None
                if hasattr(self.interface, 'localNode'):
                    my_node = self.interface.localNode
                
                # Run Analysis
                issues = self.analyzer.analyze(nodes, packet_history=self.packet_history, my_node=my_node)
                
                # Report Issues
                if issues:
                    logger.warning(f"Found {len(issues)} potential issues:")
                    for issue in issues:
                        logger.warning(f"  - {issue}")
                else:
                    logger.info("No critical issues found in current scan.")

                # Run Active Tests
                if self.active_tester:
                    self.active_tester.run_next_test()

                # Wait for next scan
                time.sleep(60) 
            # ... exceptions ...
            except KeyboardInterrupt:
                logger.info("Stopping monitor...")
                self.stop()
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(10)

if __name__ == "__main__":
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
    
    monitor.start()
