import sys, time, numpy as np, pylsl
sys.path.insert(0, r"E:\GitHub\LSLGame")
from src.simulation.synthetic_eeg import SyntheticEEGSource
from src.game.ball_roll import MarkerPublisher
src = SyntheticEEGSource(random_seed=0, source_id="ALIGN2_SIM", sync_channel=True); src.start()
mp = MarkerPublisher(stream_name="ALIGN2_M", source_id="ALIGN2_M")
ei = pylsl.StreamInlet(pylsl.resolve_byprop("source_id", "ALIGN2_SIM", timeout=3)[0], max_buflen=90); ei.open_stream(5)
mi = pylsl.StreamInlet(pylsl.resolve_byprop("source_id", "ALIGN2_M", timeout=3)[0], max_buflen=90); mi.open_stream(5)
time.sleep(1.0)
for k in range(20):
    time.sleep(0.3 + 0.2*np.random.rand())
    ts = pylsl.local_clock(); src.set_class("left"); mp.push("cue_left", timestamp=ts)
    time.sleep(0.4); src.set_class("rest"); mp.push("cue_rest")
time.sleep(0.5); src.stop()
X, T = [], []
while True:
    c, t = ei.pull_chunk(timeout=0.3)
    if not c: break
    X += c; T += t
X = np.array(X); T = np.array(T); M = []
while True:
    s, t = mi.pull_sample(timeout=0.3)
    if s is None: break
    M.append((s[0], t))
bip = X[:, 7]; lv = bip[bip > 0]
on = T[1:][(bip[1:] > 0.5) & (bip[:-1] < 0.5)]
lags = [(on[on >= t - 0.1][0] - t) * 1000 for n, t in M if n == "cue_left" and (on >= t - 0.1).any()]
print(f"[hizalama] {len(lags)} olay | gecikme ms: ort {np.mean(lags):.1f}, min {np.min(lags):.1f}, max {np.max(lags):.1f}  (once: ort -12.5, min -32.9)")
print(f"[hizalama] EEG dt medyan {np.median(np.diff(T))*1000:.2f} ms, max {np.max(np.diff(T))*1000:.2f} ms (once max 57.6) | BIP kodlari: {sorted(set(np.round(bip,1)))}")
