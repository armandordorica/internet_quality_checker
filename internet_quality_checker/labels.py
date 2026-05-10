"""Helpers for display names and filesystem-safe labels."""


def filename_label_from_network_name(network_name):
    """Convert a network display name into a safe filename label."""
    label = "".join(char.lower() if char.isalnum() else "_" for char in network_name.strip())
    label = "_".join(part for part in label.split("_") if part)
    return label or "internet_quality"
