"""
Constants and default values for the Meshtastic Network Monitor.

This module centralizes all default configuration values to ensure
a single source of truth and easier maintenance.
"""

# Thresholds
DEFAULT_CHANNEL_UTILIZATION_THRESHOLD = 25.0  # Percentage
DEFAULT_AIR_UTIL_TX_THRESHOLD = 7.0  # Percentage
DEFAULT_ROUTER_DENSITY_THRESHOLD = 2000  # Meters
DEFAULT_ACTIVE_THRESHOLD_SECONDS = 7200  # 2 hours
DEFAULT_MAX_NODES_LONG_FAST = 60

# Timeouts and Intervals
DEFAULT_TRACEROUTE_TIMEOUT = 60  # Seconds
DEFAULT_TEST_INTERVAL = 30  # Seconds between tests
DEFAULT_ANALYSIS_INTERVAL = 60  # Seconds between analysis runs
DEFAULT_DISCOVERY_WAIT_SECONDS = 60  # Seconds to wait during discovery

# Active Testing
DEFAULT_HOP_LIMIT = 7  # Maximum hops for traceroute
DEFAULT_AUTO_DISCOVERY_LIMIT = 5  # Number of nodes to auto-discover
DEFAULT_AUTO_DISCOVERY_ROLES = ['ROUTER', 'REPEATER']

# Geospatial
DEFAULT_CLUSTER_RADIUS = 2000  # Meters for router cluster analysis

# Reporting
DEFAULT_REPORT_CYCLES = 1  # Number of test cycles before generating report
DEFAULT_REPORT_DIR = "reports"

# Logging
DEFAULT_LOG_LEVEL = "INFO"
