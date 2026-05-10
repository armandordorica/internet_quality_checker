"""Notebook UI helpers."""

import ipywidgets as widgets

from .labels import filename_label_from_network_name


def create_network_name_widget(default="Peanut Butter"):
    return widgets.Text(
        value=default,
        placeholder="Enter network name, e.g. Peanut Butter",
        description="Network:",
        layout=widgets.Layout(width="500px"),
    )


def network_name_from_widget(network_name_widget):
    network_name = network_name_widget.value.strip()
    if not network_name:
        raise ValueError("Enter a network name in the widget before running the monitor.")
    return network_name


def export_label_from_widget(network_name_widget):
    return filename_label_from_network_name(network_name_from_widget(network_name_widget))
