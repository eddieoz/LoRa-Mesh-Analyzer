# Architecture Overview

The LoRa Mesh Analyzer is structured as a modular Python application. This document outlines the key components and their responsibilities.

## Directory Structure

```
LoRa-Mesh-Analyzer/
├── mesh_analyzer/       # Core package
│   ├── monitor.py       # Main application loop and orchestration
│   ├── analyzer.py      # Passive health check logic
│   ├── active_tests.py  # Active testing logic (Traceroute, etc.)
│   ├── reporter.py      # Report generation (Markdown/HTML)
│   ├── route_analyzer.py# Route analysis and topology mapping
│   ├── config_validator.py # Configuration validation
│   └── utils.py         # Shared utility functions
├── scripts/             # Standalone scripts and tools
│   ├── report_generate.py # Tool to regenerate reports from JSON
│   └── ...
├── reports/             # Generated reports and data
├── tests/               # Unit tests
├── config.yaml          # User configuration
└── main.py              # Entry point
```

## Core Components

### `monitor.py`
The central coordinator. It:
1.  Initializes the Meshtastic interface.
2.  Loads configuration.
3.  Runs the main loop:
    - Collects node data.
    - Triggers auto-discovery or priority node selection.
    - Orchestrates active tests.
    - Invokes the analyzer and reporter.

### `analyzer.py`
Responsible for passive analysis of the mesh. It checks for:
-   **Congestion**: High Channel Utilization.
-   **Spam**: High Airtime usage.
-   **Placement**: Routers without GPS, redundant routers.
-   **Configuration**: Deprecated roles, bad hop limits.

### `active_tests.py`
Handles active network probing. It:
-   Sends traceroute requests.
-   Parses responses.
-   Manages timeouts and rate limiting.

### `reporter.py`
Generates human-readable reports. It:
-   Takes analysis results and test data.
-   Formats them into Markdown or HTML.
-   Saves raw data to JSON for persistence.

### `route_analyzer.py`
Analyzes the topology based on traceroute data. It:
-   Identifies common relays (backbone nodes).
-   Detects bottlenecks (single points of failure).
-   Calculates link quality metrics.

## Data Flow

1.  **Collection**: `monitor.py` collects raw node data from the Meshtastic interface.
2.  **Testing**: `active_tests.py` probes specific nodes and adds results to the dataset.
3.  **Analysis**: `analyzer.py` and `route_analyzer.py` process the raw data and test results to identify issues and patterns.
4.  **Reporting**: `reporter.py` formats the findings into a report and saves the state to JSON.
