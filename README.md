# Meshtastic Network Monitor

An autonomous Python application designed to monitor, test, and diagnose the health of a Meshtastic mesh network. It identifies "toxic" behaviors, congestion, and configuration issues that can degrade network performance.

## Documentation

Full documentation is available in the `docs/` directory:

-   **[Usage Guide](docs/usage.md)**: How to run the monitor (USB/TCP) and command-line options.
-   **[Configuration Guide](docs/configuration.md)**: Detailed explanation of `config.yaml` settings.
-   **[Report Generation](docs/report_generation.md)**: How to use the `report_generate.py` tool.
-   **[Architecture](docs/architecture.md)**: Overview of the codebase structure and components.

## Quick Start

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Configure**:
    Copy `sample-config.yaml` to `config.yaml` and edit it:
    ```bash
    cp sample-config.yaml config.yaml
    nano config.yaml
    ```

3.  **Run**:
    ```bash
    python3 main.py
    ```

## Features at a Glance

-   **Passive Health Checks**: Detects congestion (>25% ChUtil), spam (>10% AirUtil), and bad topology.
-   **Auto-Discovery**: Automatically finds and tests important nodes (Routers, Repeaters).
-   **Active Testing**: Performs traceroutes to map the network and find dead zones.
-   **Route Analysis**: Identifies critical relays and bottlenecks.
-   **Reporting**: Generates detailed Markdown and HTML reports with network insights.
-   **Data Persistence**: Saves all data to JSON for future analysis.

## Project Structure

-   `mesh_analyzer/`: Core application logic.
-   `scripts/`: Utilities like `report_generate.py`.
-   `reports/`: Output directory for reports and data.
-   `docs/`: Detailed documentation.

