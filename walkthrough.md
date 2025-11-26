# Meshtastic Network Monitor - Walkthrough

I have created an autonomous Python application to monitor your Meshtastic mesh for health and configuration issues.

## Features
- **Congestion Detection**: Flags nodes with Channel Utilization > 25%.
- **Spam Detection**: Flags nodes with high Airtime Usage (> 10%).
- **Role Audit**: Identifies deprecated `ROUTER_CLIENT` roles and potentially misplaced `ROUTER` nodes (no GPS).
- **Active Testing**: (Optional) Can run traceroutes to specific nodes.

## Installation

1.  **Dependencies**: Ensure you have the `meshtastic` python library installed.
    ```bash
    pip install -r requirements.txt
    ```

2.  **Hardware**: Connect your Meshtastic device via USB.

## Usage

### Running the Monitor (USB/Serial)
Run the monitor directly from the terminal. It will auto-detect the USB device.

```bash
python3 -m mesh_monitor.monitor
```

### Running with TCP (Network Connection)
If your node is on the network (e.g., WiFi), specify the IP address:

```bash
python3 -m mesh_monitor.monitor --tcp 192.168.1.10
```

### Options
- `--ignore-no-position`: Suppress warnings about routers without position (GPS) enabled.
  ```bash
  python3 -m mesh_monitor.monitor --ignore-no-position
  ```

## Configuration (Priority Testing)

You can specify a list of "Priority Nodes" in `config.yaml`. The monitor will prioritize running active tests (traceroute) on these nodes.

**config.yaml**:
```yaml
priority_nodes:
  - "!12345678" 
  - "!87654321"
```

## Output Interpretation

The monitor runs a scan every 60 seconds. You will see logs like this:

```text
INFO - Connected to node.
INFO - --- Running Network Analysis ---
WARNING - Found 2 potential issues:
WARNING -   - Congestion: Node 'MountainRepeater' reports ChUtil 45.0% (Threshold: 25.0%)
WARNING -   - Config: Node 'OldUnit' is using deprecated role 'ROUTER_CLIENT'.
```

## Files Created
- `mesh_monitor/monitor.py`: Main application loop.
- `mesh_monitor/analyzer.py`: Logic for detecting issues.
- `mesh_monitor/active_tests.py`: Tools for active probing (traceroute).
- `tests/mock_test.py`: Verification script.
