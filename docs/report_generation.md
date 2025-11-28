# Report Generation Tool

The `report_generate.py` script allows you to regenerate Markdown reports from existing JSON data files. This is useful for:
- Re-applying analysis logic after updating the code or configuration.
- Generating reports in different formats (e.g., if you forgot to enable HTML).
- Debugging report generation issues without re-running long tests.

## Usage

```bash
python3 scripts/report_generate.py <json_file_path> [--output <output_path>]
```

### Arguments

- `json_file_path`: Path to the JSON data file (e.g., `reports/report-20251128-145548.json`).
- `--output`, `-o`: (Optional) Custom output path for the Markdown report. If not specified, the report is generated in the `reports/` directory with a new timestamp.

## Examples

**Regenerate a report from a JSON file:**

```bash
python3 scripts/report_generate.py reports/report-20251128-145548.json
```

**Regenerate a report and save it to a specific file:**

```bash
python3 scripts/report_generate.py reports/report-20251128-145548.json --output my_custom_report.md
```

## How it Works

1.  **Loads Data**: Reads the raw node data, test results, and session metadata from the JSON file.
2.  **Applies Configuration**: Uses the configuration embedded in the JSON file, but applies any manual positions from the *current* `config.yaml` to ensure up-to-date geolocation.
3.  **Re-runs Analysis**: Re-initializes the `NetworkHealthAnalyzer` and re-runs the analysis on the loaded data. This means any improvements to the analysis logic in the code will be reflected in the new report.
4.  **Generates Report**: Uses the `NetworkReporter` to generate the Markdown report, incorporating the new analysis results.
