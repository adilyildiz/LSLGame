"""Control interface module for BCI control streams and keyboard emulation."""

from src.control.contract import (
    CONTINUOUS_CHANNELS,
    DEFAULT_SRATE,
    DISCRETE_CHANNELS,
    STREAM_NAME,
    STREAM_TYPE,
    ControlMode,
    ControlReceiver,
    ControlSender,
    Direction,
    create_control_stream_info,
    identify_control_mode,
)
from src.control.keyboard_source import KeyboardControlSource

__all__ = [
    "STREAM_NAME",
    "STREAM_TYPE",
    "DEFAULT_SRATE",
    "DISCRETE_CHANNELS",
    "CONTINUOUS_CHANNELS",
    "ControlMode",
    "Direction",
    "create_control_stream_info",
    "identify_control_mode",
    "ControlSender",
    "ControlReceiver",
    "KeyboardControlSource",
]
