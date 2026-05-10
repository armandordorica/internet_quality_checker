"""Notebook UI helpers."""

import asyncio
from threading import Event

import ipywidgets as widgets
from IPython.display import display

from .labels import filename_label_from_network_name


def create_network_name_widget(default="Peanut Butter"):
    return widgets.Text(
        value=default,
        placeholder="Enter network name, e.g. Peanut Butter",
        description="Network:",
        layout=widgets.Layout(width="500px"),
    )


def create_network_control_widgets(default="Peanut Butter"):
    """Create network-name, confirmation, and stop controls for the notebook."""
    network_name_widget = create_network_name_widget(default=default)
    confirm_button = widgets.Button(description="Use this network name", button_style="success")
    stop_button = widgets.Button(description="Stop monitor", button_style="danger")
    status_output = widgets.Output()
    stop_signal = Event()

    def confirm_network_name(_):
        with status_output:
            status_output.clear_output()
            network_name = network_name_from_widget(network_name_widget)
            export_label = filename_label_from_network_name(network_name)
            print(f"Confirmed network name: {network_name}")
            print(f"Export filename label: {export_label}")

    def stop_monitor(_):
        stop_signal.set()
        with status_output:
            print("Stop requested. The monitor will finish its current probe and save collected samples.")

    confirm_button.on_click(confirm_network_name)
    stop_button.on_click(stop_monitor)

    controls = widgets.VBox([
        network_name_widget,
        widgets.HBox([confirm_button, stop_button]),
        status_output,
    ])
    display(controls)
    return {
        "network_name": network_name_widget,
        "confirm_button": confirm_button,
        "stop_button": stop_button,
        "status_output": status_output,
        "stop_signal": stop_signal,
    }


def network_name_from_widget(network_name_widget):
    network_name = network_name_widget.value.strip()
    if not network_name:
        raise ValueError("Enter a network name in the widget before running the monitor.")
    return network_name


def export_label_from_widget(network_name_widget):
    return filename_label_from_network_name(network_name_from_widget(network_name_widget))


def start_monitor_from_widgets(
    network_name_widget,
    stop_signal,
    duration_seconds=300,
    output_dir="internet_quality_results",
):
    """Start the monitor as a background notebook task so widget callbacks stay responsive."""
    from .metrics import summarize
    from .network import run_monitor

    network_name = network_name_from_widget(network_name_widget)
    connections_to_test = [{"name": network_name, "source_ip": None}]
    stop_signal.clear()

    async def monitor_runner():
        print("Starting monitor for network:", network_name)
        df = await run_monitor(
            connections_to_test,
            duration_seconds=duration_seconds,
            output_dir=output_dir,
            stop_signal=stop_signal,
        )
        display(summarize(df))
        return df

    task = asyncio.create_task(monitor_runner())
    print("Monitor started in the background. Use the Stop monitor button to stop cleanly.")
    return task
