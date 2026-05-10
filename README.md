# Internet Quality Checker

Google Meet-oriented internet quality monitoring from a Jupyter notebook.

The clean workflow notebook is `internet_quality_checker.ipynb`. The original exploratory notebook is preserved as `internet_test.ipynb`.

## Module Layout

- `internet_quality_checker/config.py`: thresholds and probe defaults
- `internet_quality_checker/network.py`: Wi-Fi helpers, TCP latency probes, speed probes, monitor runner
- `internet_quality_checker/metrics.py`: jitter, packet loss, summaries, quality status
- `internet_quality_checker/plotting.py`: live dashboard plots
- `internet_quality_checker/reporting.py`: CSV/PDF export
- `internet_quality_checker/comparison.py`: saved-run comparison plots
- `internet_quality_checker/ui.py`: notebook widgets

## Usage

1. Open `internet_quality_checker.ipynb`.
2. Run the install/import cells.
3. Enter a network label in the widget.
4. Run the monitor cell.
5. Interrupt the cell to stop early, then run the export cell.
6. Run the comparison cell after collecting multiple networks.
