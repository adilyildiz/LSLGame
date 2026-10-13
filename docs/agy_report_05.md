# Görev 05 — Faz 3 Denetim Düzeltmeleri Raporu

> **Tarih:** 13 Ekim 2026  
> **Durum:** Tamamlandı (36/36 pytest testi başarılı, 22.55 saniye)  
> **Test Çıktı Dosyası:** [`docs/pytest_output_05.txt`](file:///E:/GitHub/LSLGame/docs/pytest_output_05.txt)  
> **Çalışma Dizini:** `E:\GitHub\LSLGame`

---

## 1. Genel Özet

`agy_tasks/05_faz3_denetim_duzeltmeleri.md` belgesinde belirtilen denetim bulguları ve 4 kritik düzeltme maddesi (K1–K4) eksiksiz olarak giderilmiştir:

1. **K1 — `run_calibration.py` Gerçek API Uyumu:**
   - `search_eeg_stream()` içindeki istisna yutma kaldırıldı; akış bulunamadığında (`TimeoutError`) ayrı, beklenmeyen kod hatalarında (`Exception`) `logger.error` ve `print` ile hatayı gösterip `raise` edecek biçimde düzenlendi.
   - `XonStreamReceiver` sınıfına açık `@property def is_running(self) -> bool`, `get_latest_window()` ve `get_window()` metotları eklendi.
   - `run_calibration.py` içindeki tüm dış API çağrıları (`receiver.*`, `marker_pub.*`, `sm.*`, `compute_signal_quality`, `parse_xon_metadata`) gerçek modül tanımlarıyla eşleştirildi.

2. **K2 — Gerçek Entegrasyon Testi (Mock Yok):**
   - [`tests/test_calibration_app.py`](file:///E:/GitHub/LSLGame/tests/test_calibration_app.py) yazıldı.
   - `os.environ["SDL_VIDEODRIVER"] = "dummy"` ile headless çalışması sağlandı.
   - Gerçek `CalibrationApp` nesnesi gerçek `SyntheticEEGSource` ile uçtan uca çalıştırıldı.
   - Canlı kalite metrikleri 7 EEG kanalı (F3, F4, C3, Cz, C4, P3, P4) için doğrulandı.
   - `draw_check_screen()`, `draw_pause_screen()` ve her `draw_cue()` sınıfı (`left`, `right`, `feet`, `both_hands`, `arithmetic`, `rest`) hatasız çizildi.
   - `run()` ana döngüsü klavye olayı (`pygame.K_SPACE`) enjeksiyonu ve `max_seconds` güvenlik zaman aşımıyla gerçek döngü üzerinden tamamlandı.
   - `logs/` altındaki oturum JSON günlüğünün `trials` listesini içerdiği doğrulandı ve test sonunda yalnızca kendi oluşturduğu dosya silindi.

3. **K3 — Simülatör Zaman Damgaları ve Örnek Düzeyinde Geçiş:**
   - `SyntheticEEGSource` sabit örnek sayacı `self._sample_counter` ve `t0 = pylsl.local_clock()` ile çalıştırıldı ($t_n = t_0 + n / f_s$).
   - `push_chunk` her pakete son örneğin açık zaman damgasıyla gönderildi.
   - Üretim döngüsü gerçek zaman saatiyle kilitlendi; bir paket ancak zamanı geldiğinde üretildi.
   - `set_class(class_name, timestamp=None)` zaman damgası kaydedildi ve geçiş paket düzeyinde değil, damgası bu zamandan büyük/eşit olan ilk örnekten itibaren uygulandı.
   - `sync_channel=True` seçeneği eklendi; BIP kanalına (indeks 7) aktif sınıf kodu (rest=0, left=1, right=2, down/feet=3, up/both_hands=4, arithmetic=5) yazıldı.

4. **K4 — Gerçek Zaman Hizalama Testi:**
   - [`tests/test_calibration.py`](file:///E:/GitHub/LSLGame/tests/test_calibration.py) içindeki `test_e2e_calibration_simulator_recording_and_alignment` testi BIP basamak tespitiyle yenilendi.
   - 12 olay koşturuldu: `ts = pylsl.local_clock()` alındı, hemen ardından `set_class` çağrıldı ve `cue_*` marker'ı `timestamp=ts` ile gönderildi.
   - BIP kanalındaki basamağın ilk örnek zaman damgası bulunup `gecikme = basamak_ts - marker_ts` ölçüldü.

---

## 2. Madde Madde Değişiklikler ve Doğrulama Kanıtları

### K1 — `run_calibration.py` Gerçek API Uyumu

- **Değişiklikler:**
  - [`src/calibration/run_calibration.py`](file:///E:/GitHub/LSLGame/src/calibration/run_calibration.py):
    - `search_eeg_stream()`: `TimeoutError` yakalandığında akışın bulunamadığı bilgisi loglandı (`return False`). Beklenmeyen tüm diğer istisnalar (`Exception`) `logger.error(..., exc_info=True)` ile tam traceback kaydedilip konsola yazdırıldı ve `raise` edildi.
    - `update_live_quality()`: `self.receiver.is_running` ve `self.receiver.ring_buffer.is_ready(1.0)` kontrolü eklendi; tamponun mevcut örnek sayısına göre `get_latest_window(duration_sec=avail_sec)` çağrılarak `ValueError` oluşması engellendi.
    - `CalibrationApp.__init__`: `config_path` parametresine sözlük (`dict`) tipi desteği eklendi.
    - `CalibrationApp.run()`: Başlangıçta ekranın oluşturulmasını garanti eden `if self.screen is None: self.init_pygame()` kontrolü, `max_seconds` güvenlik zaman aşımı ve oturum tamamlandığında otomatik döngüden çıkış eklendi.
  - [`src/acquisition/stream_receiver.py`](file:///E:/GitHub/LSLGame/src/acquisition/stream_receiver.py):
    - `XonStreamReceiver` sınıfına `@property def is_running(self) -> bool` eklendi (`self._running` değerini döndürür).
    - `XonStreamReceiver` sınıfına `get_latest_window(duration_sec)` ve `get_window(window_sec)` yetki aktarma metotları eklendi.
- **Hangi Test Kanıtlıyor:**
  - `tests/test_calibration_app.py::test_calibration_app_full_integration_real_hardware_simulator`
  - `tests/test_acquisition.py::test_find_xon_stream_allow_simulator`

---

### K2 — Gerçek Entegrasyon Testi (Mock Yok)

- **Değişiklikler:**
  - [`tests/test_calibration_app.py`](file:///E:/GitHub/LSLGame/tests/test_calibration_app.py) dosyası sıfırdan oluşturuldu.
  - Dosya başında `os.environ["SDL_VIDEODRIVER"] = "dummy"` ile headless ortam sağlandı.
  - Gerçek `SyntheticEEGSource` ve gerçek `CalibrationApp` eşleştirildi.
  - 1. Adım: `search_eeg_stream()` -> `True` döndü.
  - 2. Adım: `update_live_quality()` -> F3, F4, C3, Cz, C4, P3, P4 dahil tüm kanallar için `rms` ve `status` metrikleri hesaplandı.
  - 3. Adım: `draw_check_screen()` -> hatasız çizildi.
  - 4. Adım: `short_config` (aşama süreleri 0.1–0.15 sn, 3 deneme, 1 run, `mi2`) ile `app.run(max_seconds=20.0)` koşturuldu. Ayrı bir iş parçacığından `pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))` ile deneme başlatıldı ve oturum başarıyla tamamlandı (`app.sm.is_completed == True`).
  - 5. Adım: `logs/` altında oluşan oturum JSON dosyasının varlığı, `trials` listesinin 3 denemeyi eksiksiz içerdiği doğrulandı. Test sonunda dosya `created_log_file.unlink()` ile temizlendi.
  - 6. Adım: `left`, `right`, `feet`, `both_hands`, `arithmetic`, `rest` ve `draw_pause_screen()` çizim metotları test edildi.
- **Hangi Test Kanıtlıyor:**
  - `tests/test_calibration_app.py::test_calibration_app_full_integration_real_hardware_simulator` (4.74 saniyede başarılı)

---

### K3 — Simülatör Zaman Damgaları ve Senkron Kanalı

- **Değişiklikler:**
  - [`src/simulation/synthetic_eeg.py`](file:///E:/GitHub/LSLGame/src/simulation/synthetic_eeg.py):
    - `CLASS_CODES` sözlüğü tanımlandı: `rest: 0.0, left: 1.0, right: 2.0, down/feet: 3.0, up/both_hands: 4.0, arithmetic: 5.0`.
    - `__init__`: `sync_channel: bool = False`, `_sample_counter = 0`, `_t0 = None`, `_transitions = []` değişkenleri tanımlandı.
    - `set_class(class_name, timestamp=None)`: İsteğe bağlı `timestamp` parametresi eklendi (varsayılan: `pylsl.local_clock()`). Geçiş zaman damgalı olarak `_transitions` kuyruğuna eklendi.
    - `generate_chunk(n_samples)`: Her örnek için zaman damgası $t = t_0 + (\text{sample\_counter} + i) / f_s$ hesaplandı. Her örneğin aktif sınıfı, damgası $t$'den küçük veya eşit olan en son geçişe göre belirlendi (örnek düzeyinde sınıf değişimi).
    - `sync_channel=True` ise BIP kanalı (indeks 7) aktif sınıfın sayısal koduna ayarlandı; `sync_channel=False` ise 0.0 kaldı.
    - `step()`: `push_chunk` çağrısına paketin son örneğinin açık zaman damgası iletildi (`timestamp = t0 + (sample_counter + chunk_size - 1) / fs`).
    - `_run_loop()`: Üretim döngüsü paketin son örneğinin damga zamanı gelene kadar bekleyecek şekilde gerçek zamana kilitlendi.
- **Hangi Test Kanıtlıyor:**
  - `tests/test_synthetic_eeg.py::test_synthetic_eeg_metadata_and_streams`
  - `tests/test_synthetic_eeg.py::test_synthetic_eeg_end_to_end_left_class_erd`
  - `tests/test_calibration.py::test_e2e_calibration_simulator_recording_and_alignment`

---

### K4 — Gerçek Hizalama ve Gecikme Ölçümü

- **Değişiklikler:**
  - [`tests/test_calibration.py`](file:///E:/GitHub/LSLGame/tests/test_calibration.py) içindeki `test_e2e_calibration_simulator_recording_and_alignment`:
    - Simülatör `sync_channel=True` ile başlatıldı.
    - 12 olaylık test dizisi (`left`, `rest`, `right`, `rest`, `down`, `rest`, `up`, `rest`, `left`, `rest`, `right`, `rest`) boyunca `ts = pylsl.local_clock()` alındı, hemen ardından `set_class` çağrıldı ve `marker_pub.push("cue_*", timestamp=ts)` iletildi.
    - LSL üzerinden çekilen EEG verisinde BIP kanalındaki basamağın ilk örneği bulunarak `basamak_ts` tespit edildi.
    - Her olay için `gecikme = basamak_ts - marker_ts` hesaplandı.
- **Ölçülen Değerler:**
  - **Örnek Sayısı:** 12 olay
  - **Minimum Gecikme:** `0.02 ms`
  - **Ortalama Gecikme:** `1.94 ms`
  - **Maksimum Gecikme:** `3.60 ms`
  - **Kabul Kriteri Karşılaştırması:** Tüm olaylarda `-4.0 ms <= gecikme <= 12.0 ms` kriteri eksiksiz sağlandı (0.02 ms – 3.60 ms aralığında).
  - **Ardışık Örnek Damga Farkı:** `4.00 ms` (250 Hz için sabit; kriter: `<= 6.0 ms`).
- **Hangi Test Kanıtlıyor:**
  - `tests/test_calibration.py::test_e2e_calibration_simulator_recording_and_alignment`

---

### Ek İyileştirme — Control Receiver Zaman Damgası Tabanlı Staleness

- **Değişiklik:**
  - [`src/control/contract.py`](file:///E:/GitHub/LSLGame/src/control/contract.py) modülünde `ControlReceiver.get_command()`, LSL inlet tamponunda bekleyen eski örnekleri yanlışlıkla taze sayabiliyordu. `pull_latest()` LSL zaman damgasını döndürecek ve `now - sample_ts <= self.stale_after` kontrolü LSL damgası üzerinden yapılacak şekilde düzeltildi.
- **Hangi Test Kanıtlıyor:**
  - `tests/test_control_contract.py::test_control_receiver_sample_retention_and_staleness`

---

## 3. Test Koleksiyonu ve Pytest Çıktısı

Görev kuralı uyarınca tüm testler aşağıdaki komutla çalıştırılmış ve doğrudan dosyaya yazılmıştır:
```cmd
cmd /c ".venv\Scripts\python -m pytest -q -rA > docs\pytest_output_05.txt 2>&1"
```

Resmi çıktı dosyası: [`docs/pytest_output_05.txt`](file:///E:/GitHub/LSLGame/docs/pytest_output_05.txt)

### `--collect-only` ile Birebir Karşılaştırma Listesi (36 Test)

| # | Test Dosyası | Test Fonksiyonu Adı | Durum |
|---|---|---|---|
| 1 | `tests/test_acquisition.py` | `test_ring_buffer_basic` | PASSED |
| 2 | `tests/test_acquisition.py` | `test_ring_buffer_wraparound` | PASSED |
| 3 | `tests/test_acquisition.py` | `test_ring_buffer_get_latest_window` | PASSED |
| 4 | `tests/test_acquisition.py` | `test_parse_xon_metadata` | PASSED |
| 5 | `tests/test_acquisition.py` | `test_find_xon_stream_allow_simulator` | PASSED |
| 6 | `tests/test_acquisition.py` | `test_find_xon_stream_multiple_matches_warning` | PASSED |
| 7 | `tests/test_calibration.py` | `test_balanced_sequence_distribution_and_streak` | PASSED |
| 8 | `tests/test_calibration.py` | `test_state_machine_virtual_clock_timeline_and_markers` | PASSED |
| 9 | `tests/test_calibration.py` | `test_all_marker_names_are_strict_ascii` | PASSED |
| 10 | `tests/test_calibration.py` | `test_session_abort_saves_proper_log_and_markers` | PASSED |
| 11 | `tests/test_calibration.py` | `test_calibration_app_filename_and_quality_check` | PASSED |
| 12 | `tests/test_calibration.py` | `test_e2e_calibration_simulator_recording_and_alignment` | PASSED |
| 13 | `tests/test_calibration.py` | `test_calibration_config_file_integrity_and_cli_parsing` | PASSED |
| 14 | `tests/test_calibration_app.py` | `test_calibration_app_full_integration_real_hardware_simulator` | PASSED |
| 15 | `tests/test_control_contract.py` | `test_control_info_creation` | PASSED |
| 16 | `tests/test_control_contract.py` | `test_discrete_sender_receiver` | PASSED |
| 17 | `tests/test_control_contract.py` | `test_continuous_sender_receiver` | PASSED |
| 18 | `tests/test_control_contract.py` | `test_keyboard_source_emission` | PASSED |
| 19 | `tests/test_control_contract.py` | `test_control_receiver_sample_retention_and_staleness` | PASSED |
| 20 | `tests/test_control_contract.py` | `test_control_receiver_timeout_nonexistent_and_closed_stream` | PASSED |
| 21 | `tests/test_control_contract.py` | `test_standalone_keyboard_workflow` | PASSED |
| 22 | `tests/test_device_config.py` | `test_config_file_exists` | PASSED |
| 23 | `tests/test_device_config.py` | `test_config_contents` | PASSED |
| 24 | `tests/test_game_logic.py` | `test_game_logic_headless_movement_and_scoring` | PASSED |
| 25 | `tests/test_game_logic.py` | `test_target_sequence_balanced_and_constrained` | PASSED |
| 26 | `tests/test_game_logic.py` | `test_wrong_direction_results_in_miss` | PASSED |
| 27 | `tests/test_game_logic.py` | `test_idle_player_trial_timeout` | PASSED |
| 28 | `tests/test_game_logic.py` | `test_inter_trial_pause_ignores_commands` | PASSED |
| 29 | `tests/test_game_logic.py` | `test_ui_strings_contain_turkish_characters` | PASSED |
| 30 | `tests/test_game_logic.py` | `test_markers_are_pure_ascii_and_proper_sequence` | PASSED |
| 31 | `tests/test_pilot_xdf.py` | `test_pilot_xdf_exists` | PASSED |
| 32 | `tests/test_pilot_xdf.py` | `test_pilot_xdf_xon_stream` | PASSED |
| 33 | `tests/test_signal_quality.py` | `test_quality_metrics_pure_tones` | PASSED |
| 34 | `tests/test_synthetic_eeg.py` | `test_synthetic_eeg_metadata_and_streams` | PASSED |
| 35 | `tests/test_synthetic_eeg.py` | `test_synthetic_eeg_end_to_end_left_class_erd` | PASSED |
| 36 | `tests/test_xdf_replay.py` | `test_xdf_replay_stream` | PASSED |

**Sonuç Özeti:** `36 passed in 22.55s`
