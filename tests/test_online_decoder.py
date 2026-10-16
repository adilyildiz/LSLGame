"""OnlineDecoder (Faz 5) birim/entegrasyon testi — LSL gerektirmez."""

import numpy as np

from src.models.pipelines import build_m1_log_bandpower
from src.online.decoder import OnlineDecoder
from src.processing.epochs import extract_epochs
from src.simulation.offline_dataset import generate_offline_dataset


def _train_model():
    rec = generate_offline_dataset(erd_power_drop=0.6, n_runs=3, trials_per_run=20, profile="mi2", seed=3)
    ep = extract_epochs(rec, filter_mode="causal")
    model = build_m1_log_bandpower(srate=ep.srate, ch_names=ep.ch_names)
    model.fit(ep.data, ep.labels)
    return model, rec


def test_decoder_warmup_then_probabilities():
    model, rec = _train_model()
    dec = OnlineDecoder(model, srate=rec.srate, n_channels=rec.eeg.shape[1], smoothing=0.0, conf_threshold=0.0)
    assert dec.predict_probs() is None  # veri yok -> hazır değil

    n = int(rec.srate * 6)
    for i in range(0, n, 25):  # 0.1 sn'lik bloklar
        dec.push(rec.eeg[i : i + 25])
    assert dec.ready
    probs = dec.predict_probs()
    assert probs is not None
    assert set(probs) == {"p_left", "p_right", "p_up", "p_down", "p_rest"}
    assert 0.0 <= max(probs.values()) <= 1.0
    assert np.isclose(probs["p_left"] + probs["p_right"], 1.0, atol=1e-6) or probs["p_rest"] > 0


def test_low_confidence_gives_rest():
    model, rec = _train_model()
    dec = OnlineDecoder(model, srate=rec.srate, n_channels=rec.eeg.shape[1], smoothing=0.0, conf_threshold=1.01)
    for i in range(0, int(rec.srate * 6), 25):
        dec.push(rec.eeg[i : i + 25])
    probs = dec.predict_probs()
    assert probs["p_rest"] == 1.0
