# Meshtastic Network Monitor

An autonomous Python application designed to monitor, test, and diagnose the health of a Meshtastic mesh network. It identifies "toxic" behaviors, congestion, and configuration issues that can degrade network performance.

## Features

The monitor runs a continuous loop (every 60 seconds) and performs the following checks:

### 1. Passive Health Checks
*   **Congestion Detection**: Flags nodes reporting a Channel Utilization (`ChUtil`) > **25%**. High utilization leads to packet collisions and mesh instability.
*   **Spam Detection**: 
    *   **Airtime**: Flags nodes with an Airtime Transmit Duty Cycle (`AirUtilTx`) > **10%**.
    *   **Duplication**: Flags nodes causing excessive message duplication (>3 copies of the same packet).
*   **Topology Checks**:
    *   **Hop Count**: Flags nodes that are >3 hops away, indicating a potentially inefficient topology.
*   **Role Audit**:
    *   **Deprecated Roles**: Flags any node using the deprecated `ROUTER_CLIENT` role.
    *   **Placement Verification**: Flags `ROUTER` or `REPEATER` nodes that do not have a valid GPS position.

    *   **Placement Verification**: Flags `ROUTER` or `REPEATER` nodes that do not have a valid GPS position.
    *   **Router Density**: Flags `ROUTER` nodes that are physically too close (< 500m) to each other, indicating redundancy.

### 2. Geospatial Analysis
*   **Signal vs Distance**: Flags nodes that are close (< 1km) but have poor SNR (< -5dB), indicating potential hardware issues or obstructions.
*   **Distance Calculation**: Uses GPS coordinates to calculate distances between nodes for topology analysis.

### 3. Local Configuration Analysis (On Boot)
*   **Role Check**: Warns if the monitoring node itself is set to `ROUTER` or `ROUTER_CLIENT` (Monitoring is best done as `CLIENT`).
*   **Hop Limit**: Warns if the default hop limit is > 3, which can cause network congestion.

### 3. Active Testing
*   **Priority Traceroute**: If configured, the monitor periodically sends traceroute requests to specific "Priority Nodes" to verify connectivity and hop counts.

## Installation

1.  **Clone the repository** (if applicable) or navigate to the project folder.
2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

### Basic Run (USB/Serial)
Connect your Meshtastic device via USB and run:
```bash
python3 -m mesh_monitor.monitor
```

### Network Connection (TCP)
If your node is on the network (e.g., WiFi):
```bash
python3 -m mesh_monitor.monitor --tcp 192.168.1.10
```

### Options
*   `--ignore-no-position`: Suppress warnings about routers without a position (useful for portable routers or privacy).
    ```bash
    python3 -m mesh_monitor.monitor --ignore-no-position
    ```

## Configuration (Priority Testing)

To prioritize testing specific nodes (e.g., to check if a router is reachable), add their IDs to `config.yaml`:

```yaml
priority_nodes:
  - "!12345678" 
  - "!87654321"
```

The monitor will cycle through these nodes and send traceroute requests to them.

## Interpreting Logs

The monitor outputs logs to the console. Here is how to interpret common messages:

### Health Warnings
```text
WARNING - Found 2 potential issues:
WARNING -   - Congestion: Node 'MountainRepeater' reports ChUtil 45.0% (Threshold: 25.0%)
```
*   **Meaning**: The node 'MountainRepeater' is seeing very high traffic. It might be in a noisy area or hearing too many nodes.
*   **Action**: Investigate the node. If it's a router, consider moving it or changing its settings.

```text
WARNING -   - Config: Node 'OldUnit' is using deprecated role 'ROUTER_CLIENT'.
```
*   **Meaning**: 'OldUnit' is configured with a role that is known to cause routing loops.
*   **Action**: Change the role to `CLIENT`, `ROUTER`, or `CLIENT_MUTE`.

### Active Test Logs
```text
INFO - Sending traceroute to priority node !12345678...
...
INFO - Received Traceroute Packet: {...}
```
*   **Meaning**: The monitor sent a test packet and received a response.
*   **Action**: Check the hop count in the response (if visible/parsed) to verify the path.

## Project Structure
*   `mesh_monitor/`: Source code.
    *   `monitor.py`: Main application loop.
    *   `analyzer.py`: Health check logic.
    *   `active_tests.py`: Traceroute logic.
*   `tests/`: Unit tests.
*   `config.yaml`: Configuration file.
