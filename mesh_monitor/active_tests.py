import logging
import time
import meshtastic.util

logger = logging.getLogger(__name__)

class ActiveTester:
    def __init__(self, interface, priority_nodes=None):
        self.interface = interface
        self.priority_nodes = priority_nodes if priority_nodes else []
        self.last_test_time = 0
        self.min_test_interval = 30 # Seconds between active tests
        self.current_priority_index = 0

    def run_next_test(self):
        """
        Runs the next scheduled test. Prioritizes nodes in the config list.
        """
        if not self.priority_nodes:
            return

        if time.time() - self.last_test_time < self.min_test_interval:
            return

        # Round-robin through priority nodes
        node_id = self.priority_nodes[self.current_priority_index]
        self.send_traceroute(node_id)
        
        self.current_priority_index = (self.current_priority_index + 1) % len(self.priority_nodes)

    def send_traceroute(self, dest_node_id):
        """
        Sends a traceroute request to the destination node.
        """
        logger.info(f"Sending traceroute to priority node {dest_node_id}...")
        try:
            self.interface.sendTraceRoute(dest_node_id, hopLimit=7)
            self.last_test_time = time.time()
        except Exception as e:
            logger.error(f"Failed to send traceroute: {e}")

    def flood_test(self, dest_node_id, count=5):
        """
        CAUTION: Sends multiple messages to test reliability.
        """
        logger.warning(f"Starting FLOOD TEST to {dest_node_id} (Count: {count})")
        for i in range(count):
            self.interface.sendText(f"Flood test {i+1}/{count}", destinationId=dest_node_id)
            time.sleep(5) # Wait 5 seconds between messages
