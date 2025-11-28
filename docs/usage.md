# Usage Guide

This guide covers how to run the Meshtastic Network Monitor in various modes.

## Prerequisites

Ensure you have installed the dependencies:

```bash
pip install -r requirements.txt
```

## Basic Execution

### USB / Serial Connection
If your Meshtastic device is connected via USB:

```bash
python3 main.py
```

The monitor will automatically detect the serial port.

### TCP / Network Connection
If your Meshtastic device is on the network (e.g., WiFi):

```bash
python3 main.py --tcp <IP_ADDRESS>
```

Example:
```bash
python3 main.py --tcp 192.168.1.10
```

## Command Line Options

| Option | Description |
| :--- | :--- |
| `--tcp <IP>` | Connect to a device via TCP/IP instead of Serial. |
| `--ignore-no-position` | Suppress warnings about routers without a valid GPS position. Useful for portable routers. |
| `--help` | Show the help message and exit. |

## Running in the Background

To run the monitor continuously, you might want to use `nohup` or a systemd service.

**Using nohup:**
```bash
nohup python3 main.py > monitor.log 2>&1 &
```

## Interpreting Output

The monitor outputs logs to the console (and `monitor.log` if redirected).

### Common Log Messages

-   **`INFO - Connected to radio...`**: Successful connection to the Meshtastic device.
-   **`INFO - Starting analysis cycle...`**: The monitor is beginning a new round of checks.
-   **`WARNING - Congestion: Node X reports ChUtil Y%`**: The specified node is experiencing high channel utilization.
-   **`INFO - Sending traceroute to...`**: The monitor is actively testing a node.

## Reports

Reports are generated in the `reports/` directory.
-   **Format**: `report-YYYYMMDD-HHMMSS.md` (and `.html` if enabled).
-   **Data**: `report-YYYYMMDD-HHMMSS.json` contains the raw data.

See [Report Generation](report_generation.md) for details on how to regenerate reports.
