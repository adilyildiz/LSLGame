# Görev 02 — Denetim Düzeltmeleri Uygulama ve Doğrulama Raporu

> **Tarih:** 13 Ekim 2026  
> **Durum:** Tamamlandı (23/23 pytest testi başarılı)  
> **Çalışma Dizini:** `E:\GitHub\LSLGame`

---

## 1. Genel Özet

`agy_tasks/02_denetim_duzeltmeleri.md` dosyasında tanımlanan bağımsız denetim bulguları (S1–S5) titizlikle incelenmiş ve hiçbir ek gereksiz refaktör yapılmadan yalnızca ilgili 5 sorun eksiksiz biçimde düzeltilmiştir.

- **S1 (Komut Kaybı & Staleness):** `ControlReceiver`'a son geçerli komutu saklama ve `stale_after` (0.3 sn) mekanizması eklendi. `BallRollGameLogic` `has_signal=False` iken topu anında durduracak şekilde güncellendi, oyun HUD'una "BCI Komut: SINYAL YOK" göstergesi eklendi.
- **S2 (Sonsuz Kilitlenme & Zaman Aşımı):** `ControlReceiver` ve `XonStreamReceiver`'daki tüm `StreamInlet` oluşturma noktalarında hemen ardından `inlet.open_stream(timeout=...)` çağrıldı; bağlanılamazsa Python'un yerleşik `TimeoutError` hatası fırlatılıyor. Testlerdeki yerel `stream_info` ile inlet oluşturma kalıbı kaldırılıp `source_id` üzerinden resolve etme standardına geçildi.
- **S3 (`--standalone-keyboard` Çalıştırılması):** `--standalone-keyboard` bayrağı verildiğinde oyun, kendi içinde bir `KeyboardControlSource` başlatıp tek oyun penceresinden tuşları yakalayarak tam LSL zinciri (`KeyboardControlSource` -> LSL Outlet -> LSL Inlet -> `ControlReceiver`) üzerinden oyunu kontrol edebilir hale getirildi.
- **S4 (Sentetik ERD Şiddeti):** `SyntheticEEGSource`'a `erd_power_drop=0.40` ve `random_seed` parametreleri eklendi. Genlik katsayısı $\sqrt{1 - 0.40} \approx 0.7746$ olarak güncellendi ve ERD hem $\mu$ hem $\beta$ bileşenlerine uygulandı.
- **S5 (Simülatör Karışması & Ayrımı):** `find_xon_stream` fonksiyonuna `allow_simulator=False` parametresi eklendi; varsayılanda `-SIM-` içeren akışlar eleniyor. Birden fazla akış olduğunda `WARNING` loglanıyor. `ControlReceiver` ve `XonStreamReceiver` simülatör akışını tespit edip HUD'da `[ SIMULASYON ]` olarak gösteriyor.

---

## 2. Madde Madde Değişiklikler ve Doğrulama Kanıtları

### S1 — Oyun her karede komutu kaybediyor

- **Ne Değişti:**
  - `src/control/contract.py` içerisindeki `ControlReceiver`:
    - `stale_after: float = 0.3` parametresi ve `_last_sample`, `_last_sample_time` durum değişkenleri eklendi.
    - `get_command()` çağrıldığında yeni örnek yoksa ve son örnekten bu yana `stale_after` süresi dolmamışsa son geçerli komut korunarak `has_signal=True` olarak dönülüyor.
    - Son örnekten bu yana 0.3 sn'den fazla süre geçmişse `direction='rest'`, `confidence=0.0`, `vx=0.0`, `vy=0.0` ve `has_signal=False` dönüyor.
  - `src/game/ball_roll.py`:
    - `BallRollGameLogic.update()` içinde `command.get("has_signal", True) is False` ise top durduruluyor (`vx = 0.0`).
    - `BallRollGame.run()` HUD çiziminde `has_signal=False` iken kırmızı renkle `"BCI Komut: SINYAL YOK"` metni görüntüleniyor.
- **Hangi Test Kanıtlıyor:**
  - `tests/test_control_contract.py::test_control_receiver_sample_retention_and_staleness`
  - Test senaryosu: 20 Hz ile 'left' komutu gönderilirken alıcı 60 FPS hızında 60 kare okur. Hareketli kare oranı ölçülür. Ardından gönderim kesilir ve 0.35 sn sonra komut okunur.
  - Ölçülen hareketli kare oranı: **%100.0** (Şartname: $\ge$ %90).
  - 0.35 sn sonra: `has_signal=False` ve `direction='rest'`.
- **Pytest Çıktısı:**
  ```text
  tests/test_control_contract.py::test_control_receiver_sample_retention_and_staleness PASSED [100%]
  ```

---

### S2 — Alıcılar sonsuza kadar kilitlenebiliyor

- **Ne Değişti:**
  - `src/control/contract.py` (`ControlReceiver.__init__`) ve `src/acquisition/stream_receiver.py` (`XonStreamReceiver.__init__`):
    - `StreamInlet` nesnesi oluşturulduktan hemen sonra `inlet.open_stream(timeout=timeout)` çağrısı eklendi.
    - Bağlantı zaman aşımına uğrarsa veya kaynak kaybolursa yakalanıp yerleşik `TimeoutError` fırlatılıyor.
    - Hiçbir kod yolunda parametresiz (sonsuz) LSL beklemesi bırakılmadı.
  - `ControlReceiver` ve `XonStreamReceiver` sınıflarına `source_id: Optional[str] = None` desteği eklendi.
  - Testlerdeki `ControlReceiver(stream_info=sender.stream_info)` kalıpları kaldırılarak LSL ağında `source_id` üzerinden resolve edilip bağlanma yöntemine geçildi.
- **Hangi Test Kanıtlıyor:**
  - `tests/test_control_contract.py::test_control_receiver_timeout_nonexistent_and_closed_stream`
  - 1. Var olmayan akışa bağlanma girişimi (timeout=1.0 sn) ~1.01 saniyede `TimeoutError` ile sonuçlandı ($\le 1.0 + 2.0$ sn).
  - 2. Kapatılmış akışa bağlanma girişimi (timeout=1.0 sn) ~1.00 saniyede `TimeoutError` ile sonuçlandı ($\le 1.0 + 2.0$ sn).
  - Testin tamamı 8.0 saniyelik üst sınırın çok altında tamamlandı.
- **Pytest Çıktısı:**
  ```text
  tests/test_control_contract.py::test_control_receiver_timeout_nonexistent_and_closed_stream PASSED [100%]
  ```

---

### S3 — `--standalone-keyboard` çalışmıyor

- **Ne Değişti:**
  - `src/game/ball_roll.py`:
    - `BallRollGame` sınıfına `keyboard_source: Optional[KeyboardControlSource] = None` desteği eklendi.
    - Oyun ana döngüsünde Pygame penceresi odaktayken basılan yön tuşları (`pygame.key.get_pressed()`) okunup `keyboard_source.set_keys(...)` ile dahili kaynağa iletiliyor.
    - Oyun kapandığında `finally` bloğu `keyboard_source.stop()` ve `receiver.close()` ile kaynakları temizliyor.
    - `__main__` bloğunda `--standalone-keyboard` bayrağı verildiğinde dahili `KeyboardControlSource(source_id="Ball_Roll_Standalone_KB")` arka planda başlatılıyor ve oyun kendi `BCI_Control` akışına bağlanıyor.
- **Hangi Test Kanıtlıyor:**
  - `tests/test_control_contract.py::test_standalone_keyboard_workflow`
  - Klavye kaynağından tuş basımı tetiklenip `ControlReceiver` üzerinden `BallRollGameLogic`'e iletildiği ve topun beklenen yönde hareket ettiği headless olarak doğrulanmıştır.
- **Pytest Çıktısı:**
  ```text
  tests/test_control_contract.py::test_standalone_keyboard_workflow PASSED [100%]
  ```

---

### S4 — Sentetik ERD şiddeti şartnameden sapıyor

- **Ne Değişti:**
  - `src/simulation/synthetic_eeg.py`:
    - `SyntheticEEGSource` yapıcısına `erd_power_drop: float = 0.40`, `random_seed: Optional[int] = None` ve `source_id: Optional[str] = None` parametreleri eklendi.
    - Genlik katsayısı $\text{erd\_attenuation} = \sqrt{1 - \text{erd\_power\_drop}} = \sqrt{0.60} \approx 0.7746$ olarak hesaplandı.
    - `generate_chunk` içinde ERD zayıflatması hem $\mu$ (10 Hz) hem de $\beta$ (20 Hz) bileşenlerine birlikte uygulandı:
      $$\text{amp\_mu} = \text{base\_mu} \times \text{scale}, \quad \text{amp\_beta} = (\text{base\_mu} \times 0.4) \times \text{scale}$$
    - `PinkNoiseGenerator` ve `SyntheticEEGSource` sınıflarına `np.random.default_rng(random_seed)` entegre edilerek tekrarlanabilirlik sağlandı.
  - `tests/test_synthetic_eeg.py`:
    - `test_synthetic_eeg_end_to_end_left_class_erd` testi %40 güç düşüşüne göre güncellendi.
    - Veri penceresi 4.0 saniyeye çıkarıldı (1000 örnek).
    - Eşik şartnameye uygun olarak korundu: $C4 / C3 \text{ güç oranı} < 0.85$ (Ölçülen: $\approx 0.63$).
- **Hangi Test Kanıtlıyor:**
  - `tests/test_synthetic_eeg.py::test_synthetic_eeg_end_to_end_left_class_erd`
- **Pytest Çıktısı:**
  ```text
  tests/test_synthetic_eeg.py::test_synthetic_eeg_end_to_end_left_class_erd PASSED [100%]
  ```

---

### S5 — Simülatör gerçek başlıkla karışabilir

- **Ne Değişti:**
  - `src/acquisition/stream_receiver.py`:
    - `find_xon_stream` fonksiyonuna `allow_simulator: bool = False` eklendi. Varsayılan olarak adında `-SIM-` geçen akışlar eleniyor.
    - Birden fazla eşleşen X.on akışı bulunduğunda `logger.warning("Birden fazla X.on akışı bulundu...")` loglanıyor.
    - `XonStreamReceiver` yapıcısına `allow_simulator` ve `source_id` eklendi, `self.is_simulator` niteliği kaydedildi.
  - `src/control/contract.py`:
    - `ControlReceiver` nesnesi stream adı veya source_id içinde `SIM` veya `KEYBOARD` geçip geçmediğini denetleyerek `self.is_simulator` belirliyor ve `get_command()` çıktısına ekliyor.
  - `src/game/ball_roll.py`:
    - Simülasyon akışı dinleniyorsa HUD üzerinde `[ SIMULASYON ]` rozeti çiziliyor.
- **Hangi Test Kanıtlıyor:**
  - `tests/test_acquisition.py::test_find_xon_stream_allow_simulator`: `allow_simulator=False` ile `-SIM-` akışının elendiğini ve zaman aşımına uğradığını, `allow_simulator=True` ile başarıyla bulunduğunu doğrular.
  - `tests/test_acquisition.py::test_find_xon_stream_multiple_matches_warning`: Birden fazla akış olduğunda `warning` loglandığını kanıtlar.
- **Pytest Çıktısı:**
  ```text
  tests/test_acquisition.py::test_find_xon_stream_allow_simulator PASSED
  tests/test_acquisition.py::test_find_xon_stream_multiple_matches_warning PASSED
  ```

---

## 3. Toplu Pytest Sonuçları

Tüm testler (eski 18 test + yeni eklenen 5 test = toplam 23 test) `.venv` ortamında başarıyla geçmiş ve 2 dakikalık üst sınırın çok altında (~18.7 sn) tamamlanmıştır:

```text
============================= test session starts =============================
platform win32 -- Python 3.12.3, pytest-9.0.2, pluggy-1.6.0
rootdir: E:\GitHub\LSLGame
collected 23 items

tests\test_acquisition.py ......                                         [ 26%]
tests\test_control_contract.py .......                                   [ 56%]
tests\test_device_config.py .                                            [ 60%]
tests\test_game_logic.py ..                                              [ 69%]
tests\test_pilot_xdf.py ...                                              [ 82%]
tests\test_signal_quality.py ..                                          [ 91%]
tests\test_synthetic_eeg.py ..                                           [100%]

============================= 23 passed in 18.66s =============================
```

---

## 4. Yapılamayan veya Eksik Kalan Maddeler

- **Yapılamayan Madde:** Yoktur. S1'den S5'e kadar tüm maddeler gereksinimlere tam uyumlu şekilde uygulanmış, test edilmiş ve belgelenmiştir.
