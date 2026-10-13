import time, sys
sys.path.insert(0, r"E:\GitHub\LSLGame")
from src.control.keyboard_source import KeyboardControlSource
from src.control.contract import ControlReceiver
from src.game.ball_roll import BallRollGameLogic
from src.simulation.synthetic_eeg import SyntheticEEGSource
from src.acquisition.stream_receiver import find_xon_stream

# S2: eski kilitlenen kalip artik zaman asimi vermeli
src = KeyboardControlSource(mode="discrete", srate=20.0, source_id="AUDIT2_KB"); src.start()
t = time.perf_counter()
try:
    ControlReceiver(stream_info=src.sender.outlet.get_info(), timeout=3.0); print("[S2] get_info kalibi baglandi", round(time.perf_counter()-t,1), "sn")
except TimeoutError as e:
    print("[S2] get_info kalibi -> TimeoutError", round(time.perf_counter()-t,1), "sn (kilitlenme yok)")

# S1: ayni olcum
src.set_keys(left=True)
rx = ControlReceiver(source_id="AUDIT2_KB", timeout=5.0); time.sleep(0.5)
g = BallRollGameLogic(random_seed=1); g.spawn_new_target("left"); x0 = g.ball_x
frames = moving = 0; t0 = time.perf_counter()
while time.perf_counter() - t0 < 1.0:
    cmd = rx.get_command(timeout=0.0)
    moving += cmd["direction"] == "left"
    g.update(1/60, cmd); frames += 1; time.sleep(1/60)
print(f"[S1] {frames} kare, hareketli %{100*moving/frames:.0f}, top {x0-g.ball_x:.0f} px (once 80 px)")
src.stop(); time.sleep(0.5); c = rx.get_command(); print("[S1] kaynak durunca:", c["direction"], "has_signal=", c["has_signal"])

# S5: gercek basliksiz ortamda simulator varsayilan olarak secilmemeli
sim = SyntheticEEGSource(random_seed=0); sim.start()
try:
    find_xon_stream(timeout=2.0); print("[S5] HATA: simulator varsayilanla secildi")
except TimeoutError: print("[S5] varsayilan: simulator atlandi")
print("[S5] allow_simulator=True:", find_xon_stream(timeout=3.0, allow_simulator=True).name())
sim.stop()
