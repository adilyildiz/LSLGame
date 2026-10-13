"""XDF Replay modülü testi."""

import time
import pylsl
import pytest
from src.simulation.xdf_replay import XDFReplay


def test_xdf_replay_stream():
    replay = XDFReplay(
        xdf_path="data/pilot/sub-P003_ses-S001_task-Default_run-001_eeg.xdf",
        stream_name_prefix="X.on",
        speed_factor=2.0,  # Testi hızlandırmak için 2 kat hız
        loop=False,
    )
    assert replay.n_channels == 11
    assert replay.nominal_srate == pytest.approx(250.0)

    # Replay'i başlat
    replay.start()

    inlet = pylsl.StreamInlet(replay.lsl_info, max_buflen=5)
    time.sleep(0.1)

    chunk, timestamps = inlet.pull_chunk(timeout=1.0)
    assert len(chunk) > 0, "Replay akışından veri alınamadı."
    assert len(chunk[0]) == 11

    inlet.close_stream()
    replay.stop()
