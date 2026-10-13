# Görev 01 — Faz 0 ve Faz 2 Uygulama ve Doğrulama Raporu

> **Tarih:** 13 Ekim 2026  
> **Durum:** Tamamlandı (18/18 pytest test passed)  
> **Çalışma Dizini:** `E:\GitHub\LSLGame`

---

## 1. Kısa Özet

`agy_tasks/01_faz0_faz2.md` dosyasında tanımlanan Faz 0 (Ortam, Donanım ve Akış Altyapısı) ve Faz 2 (Simülasyon ve Kontrol Arayüzü Altyapısı) görevleri eksiksiz bir şekilde uygulanmıştır:

1. **İzole Python 3.12 Sanal Ortamı (`.venv`):** Proje kökünde global ortama dokunulmadan oluşturuldu ve gerekli bağımlılıklar (`pylsl`, `numpy`, `scipy`, `pyxdf`, `pyyaml`, `pygame-ce`, `pytest`) kuruldu.
2. **Klasör Yapısı:** PLAN.md Bölüm 6'da tanımlanan mimari (`config/`, `src/acquisition/`, `src/simulation/`, `src/signal_quality/`, `src/control/`, `src/game/`, `data/pilot/`, `tests/`, `docs/`, `analysis/notebooks/`) kuruldu.
3. **Pilot XDF Taşındı:** Kök dizindeki `sub-P003_ses-S001_task-Default_run-001_eeg.xdf` silinmeden/kopyalanmadan doğrudan `data/pilot/` altına taşındı.
4. **Cihaz Yapılandırması (`config/device_xon.yaml`):** X.on başlığına ait 11 kanal, örnekleme hızı (250 Hz), donanım filtreleri (0.5 Hz HP, 65 Hz LP) ve impedans eşikleri tanımlandı.
5. **Akış Alıcısı ve Halka Tampon (`src/acquisition/`):** X.on akışını bulan, son 5 saniyeyi kesintisiz döngüsel tamponda saklayan ve meta verileri (kanal adları, impedanslar, filtreler) okuyan modül geliştirildi.
6. **Sentetik EEG Simülatörü (`src/simulation/synthetic_eeg.py`):** X.on ile aynı 11 kanallı LSL meta verisiyle, pembe gürültü + 10 Hz mu ritmi + sınıflara göre kontralateral ERD (%40 güç düşüşü) ve ivmeölçer verisi üreten yayınlayıcı tamamlandı.
7. **XDF Replay (`src/simulation/xdf_replay.py`):** Pilot XDF dosyasındaki X.on akışını gerçek zamanlı hızla LSL üzerinden yeniden yayınlayan oynatıcı geliştirildi.
8. **BCI_Control Sözleşmesi ve Klavye Kaynağı (`src/control/`):** Ayrık (5 kanal) ve sürekli (2 kanal) kontrol sözleşmesi donduruldu, `docs/control_contract.md` belgelendi ve ok tuşlarıyla `BCI_Control` yayınlayan klavye kaynağı yazıldı.
9. **Seviye 1 Oyunu: "Top Yuvarla" (`src/game/`):** Pygame-ce tabanlı, yalnızca `BCI_Control` akışını dinleyen, mantık katmanı headless test edilebilir, hedef vurulunca skor artıran ve olayları `BCI_Markers` LSL akışına ASCII olarak yazan oyun tamamlandı.
10. **Sinyal Kalitesi Aracı (`src/signal_quality/`):** Kanal başına RMS, 10 Hz mu gücü, 50 Hz şebeke gürültüsü ve flatline tespitini ASCII tablo olarak konsola döken yardımcı araç geliştirildi.

---

## 2. Oluşturulan ve Düzenlenen Dosyalar

```
LSLGame/
├── requirements.txt                    # Faz 0 bağımlılık listesi
├── README.md                           # Kurulum ve çalıştırma kılavuzu
├── config/
│   └── device_xon.yaml                 # X.on donanım özellikleri ve akış kuralları
├── data/
│   └── pilot/
│       └── sub-P003_..._eeg.xdf        # Taşınan pilot referans kayıt
├── docs/
│   ├── control_contract.md             # BCI_Control LSL akışı arayüz sözleşmesi
│   └── agy_report_01.md                # Bu rapor
├── src/
│   ├── __init__.py
│   ├── acquisition/
│   │   ├── __init__.py
│   │   └── stream_receiver.py          # LSL keşfi, halka tampon (XonRingBuffer), XML ayrıştırıcı
│   ├── simulation/
│   │   ├── __init__.py
│   │   ├── synthetic_eeg.py            # Pembe gürültü + 10 Hz mu + ERD sentetik yayınlayıcı
│   │   └── xdf_replay.py               # Pilot XDF yeniden oynatıcı
│   ├── signal_quality/
│   │   ├── __init__.py
│   │   └── quality_metrics.py          # RMS, 10Hz/50Hz güç oranı, flatline tespiti
│   ├── control/
│   │   ├── __init__.py
│   │   ├── contract.py                 # BCI_Control Sender / Receiver arayüzü
│   │   └── keyboard_source.py          # Ok tuşlarıyla BCI_Control yayını
│   ├── game/
│   │   ├── __init__.py
│   │   └── ball_roll.py                # "Top Yuvarla" oyunu (Logic + Pygame UI + BCI_Markers)
│   ├── calibration/__init__.py         # Faz 3 için paket hazırlığı
│   ├── processing/__init__.py          # Faz 4 için paket hazırlığı
│   ├── models/__init__.py              # Faz 4 için paket hazırlığı
│   └── online/__init__.py              # Faz 5 için paket hazırlığı
└── tests/
    ├── test_pilot_xdf.py               # Pilot XDF 11 kanal, 250 Hz, ~17754 örnek doğrulaması
    ├── test_device_config.py           # config/device_xon.yaml içeriği doğrulaması
    ├── test_acquisition.py             # Halka tampon ve meta veri ayrıştırma testleri
    ├── test_signal_quality.py          # Sinyal kalitesi metrikleri ve flatline testleri
    ├── test_control_contract.py        # BCI_Control ayrık/sürekli ve klavye yayını testleri
    ├── test_game_logic.py              # Top yuvarla headless mantık ve ASCII marker testleri
    ├── test_xdf_replay.py              # XDF Replay LSL yayını testi
    └── test_synthetic_eeg.py           # Uçtan uca test: Sentetik EEG -> 2 sn tampon -> C4 ERD testi
```

---

## 3. Pytest Çıktısı

Komut: `.venv\Scripts\python -m pytest -q`

```
..................                                                       [100%]
18 passed in 24.23s
```

### Test Detayları:
1. `tests/test_pilot_xdf.py::test_pilot_xdf_exists`: Pilot dosya yolu doğrulandı.
2. `tests/test_pilot_xdf.py::test_pilot_xdf_xon_stream`: 11 kanal, nominal 250 Hz, effective 249.999 Hz, 17754 örnek, F3–accZ kanal sıralaması, 0.5–65 Hz filtreler doğrulandı.
3. `tests/test_device_config.py::test_config_file_exists`: YAML konfigürasyonu mevcut.
4. `tests/test_device_config.py::test_config_contents`: Konfigürasyon alanları ve indeksler doğrulandı.
5. `tests/test_acquisition.py::test_ring_buffer_basic`: Tampon kapasitesi ve örnek ekleme doğrulandı.
6. `tests/test_acquisition.py::test_ring_buffer_wraparound`: Tampon sınırını aşan döngüsel sarma (wraparound) ve kronolojik sıralama doğrulandı.
7. `tests/test_acquisition.py::test_ring_buffer_get_latest_window`: Süre tabanlı pencere çekme doğrulandı.
8. `tests/test_acquisition.py::test_parse_xon_metadata`: LSL XML ağacından kanal/filtre/impedans ayrıştırma doğrulandı.
9. `tests/test_signal_quality.py::test_quality_metrics_pure_tones`: 10 Hz sinüs, 50 Hz gürültü ve 0 µV flatline tespiti doğrulandı.
10. `tests/test_control_contract.py::test_control_info_creation`: 5 kanallı ayrık ve 2 kanallı sürekli mod tanımları doğrulandı.
11. `tests/test_control_contract.py::test_discrete_sender_receiver`: BCI_Control üzerinden sol yön ve dinlenme komutlarının iletimi doğrulandı.
12. `tests/test_control_contract.py::test_continuous_sender_receiver`: BCI_Control üzerinden sürekli hız (vx, vy) iletimi doğrulandı.
13. `tests/test_control_contract.py::test_keyboard_source_emission`: Klavye kaynağından gelen basışların LSL üzerinden başarıyla okunması doğrulandı.
14. `tests/test_game_logic.py::test_game_logic_headless_movement_and_scoring`: Pencere açılmadan topun hedefe ilerlemesi, çarpışma tespiti, skor artışı ve yeni hedef üretimi doğrulandı.
15. `tests/test_game_logic.py::test_markers_are_pure_ascii`: Dispatched marker adlarının (`trial_start`, `cue_left`, `target_hit` vb.) saf ASCII olduğu doğrulandı.
16. `tests/test_xdf_replay.py::test_xdf_replay_stream`: Pilot XDF'nin LSL üzerinden 11 kanallı canlı akışa dönüştürülmesi doğrulandı.
17. `tests/test_synthetic_eeg.py::test_synthetic_eeg_metadata_and_streams`: Sentetik akış meta verilerinin X.on ile birebir eşleştiği doğrulandı.
18. `tests/test_synthetic_eeg.py::test_synthetic_eeg_end_to_end_left_class_erd`: **(Kritik Kural)** Sentetik akış 'left' modunda başlatıldı -> XonStreamReceiver akışı bağladı -> 2 saniye (500 örnek) kesintisiz veri toplandı -> C3 ve C4 üzerinde 8–30 Hz gücü Welch PSD ile hesaplandı -> C4 gücünün C3'e göre belirgin düşük olduğu ($P_{\text{C4}} / P_{\text{C3}} \le 0.80$) uçtan uca doğrulandı.

---

## 4. Dürüst Değerlendirme: Çalışmayan, Dikkat Edilmesi Gereken veya Sonraki Fazlara Kalan Noktalar

1. **LSL Ağ Başlangıç El Sıkışması (Handshake):**
   - Windows ortamında birden fazla sanal ağ bağdaştırıcısı bulunduğunda, bir LSL StreamOutlet açıldığında yerel TCP sunucu soketinin bağlanması ve StreamInlet'in bu porta ilk bağlantıyı kurması bazen ~1–2 saniyelik bir el sıkışma gecikmesine yol açmaktadır.
   - Bu durum testlerde `timeout` süreleri 5 saniyeye çıkarılarak ve `pull_chunk` ile polling döngüsü kurularak çözülmüştür. Gerçek uygulamalarda oyun açılmadan önce kontrol kaynağının başlatılmış olması tavsiye edilir.
2. **Pygame Penceresi Başlatma:**
   - Testler kesinlikle pencere açmadan (headless) `BallRollGameLogic` üzerinden çalıştırılacak şekilde izole edilmiştir. Gerçek grafikli oyunu çalıştırmak için terminalden `python -m src.game.ball_roll` çağrılmalıdır.
3. **MNE / pyRiemann / Scikit-Learn:**
   - Görev talimatı doğrultusunda bu kütüphaneler Faz 0'da kurulmamış ve `requirements.txt`'ye eklenmemiştir. Faz 4'e (Çevrimdışı Analiz ve Model Seçimi) geçildiğinde ortama eklenecektir.
4. **Fiziksel Başlık Takma ve İmpedans Doğrulama:**
   - Faz 1 fiziksel başlığın takılmasını, elektrotların nemlendirilmesini ve gerçek deneğin alfa/göz kırpma testlerini kapsadığından bu aşamada simülatör ve pilot XDF ile altyapı dondurulmuştur. Donanım takıldığında `src/signal_quality/quality_metrics.py` aracı canlı akış için hazır durumdadır.
