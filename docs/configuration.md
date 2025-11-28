# Configuration Guide

The `config.yaml` file controls the behavior of the Meshtastic Network Monitor. This guide explains each configuration option.

## Core Settings

### `log_level`
- **Description**: Sets the verbosity of the logging output.
- **Values**: `debug`, `info`, `warn`, `error`.
- **Default**: `info`.

## Auto-Discovery Settings

These settings control how the monitor automatically finds nodes to test when `priority_nodes` is empty.

### `analysis_mode`
- **Description**: Determines the strategy for selecting target nodes.
- **Values**:
    - `distance`: Selects a mix of nearest and furthest nodes.
    - `router_clusters`: Selects nodes that are within a certain radius of identified routers.
- **Default**: `distance`.

### `cluster_radius`
- **Description**: The radius (in meters) around a router to search for nodes when `analysis_mode` is set to `router_clusters`.
- **Default**: `2000`.

### `auto_discovery_roles`
- **Description**: A list of node roles to prioritize for testing. The monitor will look for nodes with these roles in the specified order.
- **Values**: `ROUTER`, `ROUTER_LATE`, `REPEATER`, `CLIENT`, `CLIENT_MUTE`, `TRACKER`, etc.

### `auto_discovery_limit`
- **Description**: The maximum number of nodes to select for active testing in each cycle.
- **Default**: `5`.

## Reporting Settings

### `report_cycles`
- **Description**: The number of full testing cycles to complete before generating a report.
- **Default**: `1`.

### `report_output_formats`
- **Description**: The formats in which to generate the report.
- **Values**: `markdown`, `html`.
- **Default**: `['markdown']`.

## Active Testing Settings

### `traceroute_timeout`
- **Description**: The time (in seconds) to wait for a traceroute response before giving up.
- **Default**: `90`.

### `active_test_interval`
- **Description**: The minimum time (in seconds) to wait between sending test packets to different nodes. This prevents flooding the network.
- **Default**: `30`.

### `hop_limit`
- **Description**: The maximum number of hops for traceroute packets.
- **Default**: `7`.

### `priority_nodes`
- **Description**: A list of specific Node IDs to test. If this list is populated, auto-discovery is disabled, and only these nodes are tested.
- **Format**: `"!<NodeID>"` (e.g., `"!12345678"`).

## Manual Geolocation Overrides

### `manual_positions`
- **Description**: Allows you to manually specify the latitude and longitude for nodes that do not report their position (e.g., fixed routers without GPS).
- **Format**:
  ```yaml
  manual_positions:
    "!nodeid":
      lat: 59.12345
      lon: 24.12345
  ```

## Analysis Thresholds

These thresholds determine when the monitor flags a node or network condition as an issue.

### `thresholds`
- **`channel_utilization`**: The percentage of channel utilization above which a node is flagged for congestion (Default: `25.0`).
- **`air_util_tx`**: The percentage of transmit airtime above which a node is flagged for spamming (Default: `7.0`).
- **`router_density_threshold`**: The minimum distance (in meters) between routers. Routers closer than this are flagged as redundant (Default: `2000`).
- **`active_threshold_seconds`**: Nodes seen within this time window are considered "active" (Default: `7200` i.e., 2 hours).

## Network Size Settings

### `max_nodes_for_long_fast`
- **Description**: The recommended maximum number of nodes for the `LONG_FAST` preset. If the network size exceeds this, a warning is generated.
- **Default**: `60`.
