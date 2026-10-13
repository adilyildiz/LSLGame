"""Simulation module for synthetic EEG generation and XDF replay."""

from src.simulation.synthetic_eeg import SyntheticEEGSource, create_xon_stream_info
from src.simulation.xdf_replay import XDFReplay

__all__ = [
    "SyntheticEEGSource",
    "create_xon_stream_info",
    "XDFReplay",
]
