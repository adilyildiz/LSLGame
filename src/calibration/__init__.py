"""Calibration module (Graz-BCI protocol)."""

from src.calibration.paradigm import (
    CalibrationStage,
    CalibrationStateMachine,
    CalibrationTiming,
    TrialInfo,
    generate_balanced_sequence,
    load_calibration_config,
)

__all__ = [
    "CalibrationStage",
    "CalibrationStateMachine",
    "CalibrationTiming",
    "TrialInfo",
    "generate_balanced_sequence",
    "load_calibration_config",
]
