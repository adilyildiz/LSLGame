# Görev 04 — Faz 3: Kalibrasyon Veri Toplama Aracı Uygulama ve Doğrulama Raporu

> **Tarih:** 13 Ekim 2026  
> **Durum:** Tamamlandı (35/35 pytest testi başarılı)  
> **Çalışma Dizini:** `E:\GitHub\LSLGame`

---

## 1. Genel Özet

`agy_tasks/04_faz3_kalibrasyon.md` belgesinde tanımlanan ve `PLAN.md` **Faz 3 (3.1–3.5)** ile **Bölüm 20 (Oturum Protokolü)** isterleri doğrultusunda Graz-BCI motor imgeleme (MI) kalibrasyon veri toplama aracı eksiksiz olarak geliştirilmiş ve doğrulanmıştır.

Geliştirilen bileşenler:
1. **`config/calibration.yaml`**: PLAN 3.1–3.3 parametrelerini içeren, kodda sabit değer bırakmayan merkezi yapılandırma (süreler, run ve deneme sayıları, mola süreleri, `mi2`, `mi3`, `mi5` oturum profilleri, görsel ve kalite eşikleri).
2. **`src/calibration/paradigm.py`**: Tamamen headless test edilebilen saf mantık ve durum makinesi katmanı (`CalibrationStateMachine`). Her run için sınıfların dengeli dağılımı (fark ≤ 1), en uzun aynı sınıf serisi ≤ 3 kısıtı ve seed tekrarlanabilirliği sağlanmıştır. Marker'lar katı ASCII kurallarına uygun adlandırılmıştır.
3. **`src/calibration/run_calibration.py`**: Pygame tabanlı kullanıcı arayüzü:
   - Başlangıç öncesi donanım ve kalite kontrol ekranı (X.on tespiti, impedans tablosu, son 5 sn canlı 50/10 Hz kalite oranı, C3/Cz/C4 kapı kontrolü).
   - LabRecorder için PLAN 3.5'e uygun dosya adı önerisi (`data/{subject}/{session}/{subject}_{session}_task-MI_run-01.xdf`) ekranda ve konsolda gösterimi.
   - `pygame.draw.polygon` ile vektörel oklar, sabitleme haçı (`+`), dinlenme ekranı, Türkçe yazı tipleri.
   - Ekran güncellemesi (`pygame.display.flip()`) hemen ardından `pylsl.local_clock()` ile senkronize marker iletimi (ekran çizilmeden önce marker gönderilmeme kuralı).
   - ESC ile oturumun güvenle sonlandırılması (`session_end`) ve `logs/` altına detaylı JSON oturum günlüğü yazılması.
4. **Simülatörle Uçtan Uca (E2E) Test**: `SyntheticEEGSource` ve `MarkerPublisher` kullanılarak LSL üzerinden eşzamanlı kayıt yapılmış, `imagery_start` – `imagery_end` pencerelerinde EEG varlığı, marker sırası, sınıf dengesi ve < 20 ms zaman damgası hizalaması (PLAN Faz 3 çıkış kriteri) başarıyla doğrulanmıştır.
5. **`docs/calibration_guide.md`**: Başlık takma, impedans ayarı, LabRecorder konfigürasyonu, CLI çalıştırma ve PLAN 3.4 kinestetik imgeleme yönergelerini içeren Türkçe oturum rehberi hazırlanmıştır.

---

## 2. Madde Madde Değişiklikler ve Doğrulama Kanıtları

### 1. `config/calibration.yaml`
- **Ne Yapıldı:**
  - `timing`: fixation_sec (2.0), cue_sec (1.0), imagery_sec (4.0), rest_min_sec (1.5), rest_max_sec (3.0), inter_run_pause_sec (60.0).
  - `run`: trials_per_run (20), max_consecutive_same_class (3).
  - `profiles`:
    - `mi2`: left, right, rest (default_runs: 4).
    - `mi3`: + feet (default_runs: 6).
    - `mi5`: + both_hands, + arithmetic (default_runs: 10).
  - `quality_gate`: C3, Cz, C4 kritik kanalları ve impedans eşikleri.
  - `recording`: stream_name_markers (`BCI_Markers`), filename_template formatı.
- **Hangi Test Kanıtlıyor:**
  - `tests/test_calibration.py::test_calibration_config_file_integrity_and_cli_parsing`

---

### 2. `src/calibration/paradigm.py` (Saf Mantık ve Durum Makinesi)
- **Ne Yapıldı:**
  - `generate_balanced_sequence(classes, count, seed, max_streak)`:
    - Sınıflar run içinde dengelidir: `count // n_classes` ve kalanlar dağıtılır, fark en fazla 1'dir.
    - Rejection sampling ile aynı sınıfın ardışık 4 kez gelmesi (`max_streak <= 3`) engellenmiştir.
    - `seed` ile 100% deterministiktir.
  - `CalibrationStateMachine`:
    - Durumlar: `IDLE`, `RUN_READY`, `FIXATION`, `CUE`, `IMAGERY`, `REST`, `INTER_RUN_PAUSE`, `SESSION_END`.
    - Sahte saat (virtual clock) veya gerçek LSL saati ile çalışabilir (`update(current_time)` ve `commit_transition(timestamp)`).
    - Marker'lar: `session_start`, `session_end`, `run_start`, `run_end`, `trial_start`, `fixation_start`, `cue_<sinif>`, `imagery_start`, `imagery_end`, `rest_start`, `trial_end`, `pause_start`, `pause_end`.
    - ASCII kontrolü: Tüm marker isimleri `.isascii()` ve küçük harf doğrulamasına tabidir.
    - ESC / abort durumunda `session_end` marker'ı gönderilir ve oturum özeti `aborted: True` olarak işaretlenir.
- **Hangi Testler Kanıtlıyor:**
  - `tests/test_calibration.py::test_balanced_sequence_distribution_and_streak`
  - `tests/test_calibration.py::test_state_machine_virtual_clock_timeline_and_markers`
  - `tests/test_calibration.py::test_all_marker_names_are_strict_ascii`
  - `tests/test_calibration.py::test_session_abort_saves_proper_log_and_markers`

---

### 3. `src/calibration/run_calibration.py` (Pygame Arayüzü ve Akış)
- **Ne Yapıldı:**
  - Koyu gri arka plan (`20, 20, 20`), merkezde `+` sabitleme haçı (`draw_fixation_cross`).
  - Vektörel polygon oklar (`pygame.draw.polygon`):
    - Sol `←`, Sağ `→`, Ayak (aşağı `↓`), İki el (yukarı `↑`).
    - Aritmetik ("100 − 7" metni), Dinlenme ("DİNLEN" ve daire).
    - İpucu süresince görünür, imgeleme başladığında kaybolur ve yalnızca `+` kalır (PLAN 3.1).
  - Kontrol Ekranı:
    - `find_xon_stream` ile X.on akışı aranır (opsiyonel `--simulator` bayrağı ile).
    - İmpedans tablosu: Cihaz meta verisinden okunup `config/device_xon.yaml` eşikleriyle (40k / 70k) renklendirilir.
    - Canlı sinyal kalitesi: `XonStreamReceiver` üzerinden son 5 sn'lik veriden RMS, 10 Hz mu, 50 Hz şebeke ve 50/10 dB güç oranı hesaplanır.
    - C3/Cz/C4 kontrolü: Kritik kanallar yeşil değilse ekranda uyarı verilir, yine de devam etme seçeneği sunulur.
    - LabRecorder yönlendirmesi ve PLAN 3.5'e uygun dosya adı şablonu ekranda ve terminalde gösterilir.
  - Marker Senkronizasyonu:
    - Yeni görsel ekrana çizilir, `pygame.display.flip()` çağrılır, hemen akabinde `flip_ts = pylsl.local_clock()` alınır ve marker'lar bu zaman damgasıyla LSL'e basılır.
  - Oturum Günlüğü:
    - Oturum sonunda veya ESC ile yarıda kesildiğinde `logs/calibration_{subject}_{session}_{datetime}.json` dosyası yazılır.
- **Hangi Testler Kanıtlıyor:**
  - `tests/test_calibration.py::test_calibration_app_filename_and_quality_check`
  - `tests/test_calibration.py::test_calibration_config_file_integrity_and_cli_parsing`

---

### 4. Simülatörle Uçtan Uca (E2E) Kayıt Testi
- **Ne Yapıldı:**
  - `SyntheticEEGSource` (250 Hz) ve `MarkerPublisher` başlatıldı.
  - Paradigma kısaltılmış sürelerle (fixation: 0.05s, cue: 0.05s, imagery: 0.10s, rest: 0.05s) koşturuldu.
  - Simülatör sınıfı ipucuna göre dinamik olarak güncellendi (`source.set_class(current_class)`).
  - Her iki akış da `pylsl.StreamInlet` ile çekildi ve kaydedildi.
  - Doğrulanan kriterler:
    1. Marker sırası (`session_start` -> `run_start` -> `trial_start` -> `cue_*` -> `imagery_start` -> `imagery_end` -> `trial_end` -> `session_end`).
    2. Sınıf dengesi (6 denemede her sınıftan tam olarak 2 deneme).
    3. Her `imagery_start` – `imagery_end` aralığında EEG örneklerinin eksiksiz bulunması.
    4. PLAN Faz 3 çıkış kriteri doğrulaması: EEG ve marker zaman damgaları aynı yerel LSL saatindedir ve zaman hizalama hatası < 20 ms'dir (250 Hz'de beklenen ~4 ms).
    5. Test süresi 7.97 sn olup 30 sn sınırının oldukça altındadır.
- **Hangi Test Kanıtlıyor:**
  - `tests/test_calibration.py::test_e2e_calibration_simulator_recording_and_alignment`

---

### 5. `docs/calibration_guide.md` (Kullanıcı Rehberi)
- Türkçe, kısa ve adım adım uygulanabilir oturum rehberi hazırlandı:
  - 1. Başlık hazırlığı, sünger nemlendirme, Cz tepe noktası ölçümü ve yerleşimi.
  - 2. İmpedans ve kontrol paneli incelemesi (C3/Cz/C4 kapısı).
  - 3. LabRecorder akış seçimi ve dosya adı kuralı.
  - 4. Kalibrasyon aracını CLI parametreleriyle çalıştırma (`--profile`, `--runs`, `--simulator` vb.).
  - 5. PLAN 3.4 kinestetik motor imgeleme yönergeleri (kas hissini hayal etme, gerçek hareket yapmama, göz kırpma/yutkunma disiplini, ritmiklik).
  - 6. Oturum sonrası kapatma, sünger temizliği ve oturum günlüğü notları.

---

## 3. Pytest Doğrulama Çıktısı

Mevcut 28 test + yeni 7 kalibrasyon testi olmak üzere toplam **35 testin tamamı** başarıyla geçmiştir:

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: E:\GitHub\LSLGame
collected 35 items

tests/test_acquisition.py::test_load_xon_config PASSED                   [  2%]
tests/test_acquisition.py::test_find_xon_stream_filters_simulator PASSED [  5%]
tests/test_acquisition.py::test_parse_xon_metadata PASSED                [  8%]
tests/test_acquisition.py::test_xon_ring_buffer_operations PASSED        [ 11%]
tests/test_acquisition.py::test_xon_stream_receiver_acquisition PASSED   [ 14%]
tests/test_calibration.py::test_balanced_sequence_distribution_and_streak PASSED [ 17%]
tests/test_calibration.py::test_state_machine_virtual_clock_timeline_and_markers PASSED [ 20%]
tests/test_calibration.py::test_all_marker_names_are_strict_ascii PASSED [ 22%]
tests/test_calibration.py::test_session_abort_saves_proper_log_and_markers PASSED [ 25%]
tests/test_calibration.py::test_calibration_app_filename_and_quality_check PASSED [ 28%]
tests/test_calibration.py::test_e2e_calibration_simulator_recording_and_alignment PASSED [ 31%]
tests/test_calibration.py::test_calibration_config_file_integrity_and_cli_parsing PASSED [ 34%]
tests/test_control_contract.py::test_control_receiver_pull_command PASSED [ 37%]
tests/test_control_contract.py::test_control_publisher_push_command PASSED [ 40%]
tests/test_control_contract.py::test_control_contract_validation PASSED   [ 42%]
tests/test_device_config.py::test_device_xon_config_integrity PASSED     [ 45%]
tests/test_device_config.py::test_impedance_thresholds PASSED            [ 48%]
tests/test_game_logic.py::test_game_logic_headless_movement_and_scoring PASSED [ 51%]
tests/test_game_logic.py::test_target_sequence_balanced_and_constrained PASSED [ 54%]
tests/test_game_logic.py::test_wrong_direction_results_in_miss PASSED    [ 57%]
tests/test_game_logic.py::test_trial_timeout_results_in_timeout_miss PASSED [ 60%]
tests/test_game_logic.py::test_inter_trial_pause_ignores_commands PASSED [ 62%]
tests/test_game_logic.py::test_markers_are_pure_ascii_and_proper_sequence PASSED [ 65%]
tests/test_game_logic.py::test_ui_strings_contain_turkish_characters PASSED [ 68%]
tests/test_pilot_xdf.py::test_pilot_xdf_eeg_stream_structure PASSED      [ 71%]
tests/test_pilot_xdf.py::test_pilot_xdf_sampling_rate_regularity PASSED   [ 74%]
tests/test_pilot_xdf.py::test_pilot_xdf_metadata_extraction PASSED       [ 77%]
tests/test_signal_quality.py::test_signal_quality_flatline_detection PASSED [ 80%]
tests/test_signal_quality.py::test_signal_quality_noise_and_clipping PASSED [ 82%]
tests/test_signal_quality.py::test_signal_quality_good_signal PASSED     [ 85%]
tests/test_synthetic_eeg.py::test_synthetic_eeg_metadata_and_streams PASSED [ 88%]
tests/test_synthetic_eeg.py::test_synthetic_eeg_end_to_end_left_class_erd PASSED [ 91%]
tests/test_synthetic_eeg.py::test_synthetic_eeg_blink_injection PASSED    [ 94%]
tests/test_xdf_replay.py::test_xdf_reader_loads_mock_stream PASSED       [ 97%]
tests/test_xdf_replay.py::test_xdf_replay_pushes_samples_to_lsl PASSED   [100%]

============================== 35 passed in 25.56s ==============================
```

---

## 4. Eksik ve Yapılamayanlar

- **Eksik veya yapılamayan bulunmamaktadır.**
- Şartnamedeki tüm kurallar (PLAN 3.1–3.5, PLAN Bölüm 20, zaman damgası senkronizasyonu, sınıf dengesi, ASCII marker'lar, impedans ve kalite kontrolleri, headless E2E testi ve kullanıcı rehberi) eksiksiz tamamlanmıştır.
- `PLAN.md` değiştirilmemiş, hiçbir dosya silinmemiş ve git commit yapılmamıştır.
