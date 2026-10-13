# Görev 02 — Denetim Düzeltmeleri (Görev 01 çıktısı üzerine)

Görev 01'in çıktısı bağımsız olarak denetlendi. Testler geçiyor, ancak testlerin yakalamadığı 5 sorun bulundu. Yalnızca bunları düzelt. Başka refaktör yapma.

## S1 — Oyun her karede komutu kaybediyor (DOĞRULANDI)
`src/game/ball_roll.py`: Oyun 60 FPS'te `get_command(timeout=0.0)` çağırıyor. Kontrol akışı ise 20 Hz. Yeni örnek gelmeyen karelerde komut `rest` oluyor ve top duruyor.
**Ölçüm:** Klavyeden sürekli "sol" gönderilirken 58 karenin yalnızca 20'sinde (%34) hareket var. Top 1 saniyede 232 px yerine 80 px gidiyor.
**Düzeltme:**
- `ControlReceiver`'a "son geçerli komutu tut" davranışı ekle.
- Yeni örnek yoksa son komut döner; ama son örnekten bu yana `stale_after` (varsayılan 0.3 sn) geçtiyse `rest` ve `has_signal=False` döner.
- Oyun `has_signal=False` iken topu durdursun ve HUD'da "SINYAL YOK" göstersin. (PLAN.md 17.2: sinyal kesilince nesne durmalı.)
**Test:** 20 Hz gönderip 60 Hz okuyan gerçekçi bir test yaz. Hareketli kare oranı ≥ %90 olmalı. Gönderim durduktan 0.3 sn sonra `rest` + `has_signal=False` dönmeli.

## S2 — Alıcılar sonsuza kadar kilitlenebiliyor (DOĞRULANDI)
`ControlReceiver(stream_info=outlet.get_info())` ile oluşturulan alıcı, ilk `pull_chunk` çağrısında zaman aşımı olmadan bekliyor. Görev 01 sırasında takılan süreç de buydu. liblsl sürekli "Error while receiving the stream info … retrying" yazıyor.
**Düzeltme:**
- `ControlReceiver` ve `src/acquisition/stream_receiver.py` içindeki tüm `StreamInlet` oluşturma noktalarında, oluşturduktan hemen sonra `inlet.open_stream(timeout=...)` çağır (varsayılan 5 sn).
- Başarısız olursa `TimeoutError` fırlat.
- Hiçbir kod yolunda zaman aşımsız (sonsuz) LSL beklemesi kalmasın.
- Testlerde `outlet.get_info()` ile inlet oluşturma kalıbını kaldır; akışları `source_id` ile resolve ederek bağlan.
**Test:** Var olmayan / kapatılmış bir akışa bağlanma girişimi, belirtilen zaman aşımı + 2 sn içinde `TimeoutError` ile bitmeli. Testin kendisine de bir üst süre koy.

## S3 — `--standalone-keyboard` çalışmıyor
`python -m src.game.ball_roll --standalone-keyboard` alıcıyı `None` bırakıyor, yani top hiç hareket etmiyor. Ayrıca ayrı klavye penceresi yalnızca odaktayken tuş alıyor. Oyunu izlerken klavye penceresine odaklanmak kullanışsız.
**Düzeltme:** Bu bayrakla oyun `KeyboardControlSource`'u kendi içinde başlatsın. Tuşları **oyun penceresinden** okuyup kaynağa versin. Kendi `BCI_Control` akışına resolve ile bağlansın. Böylece tek pencereyle, tam LSL zinciri üzerinden oynanır.

## S4 — Sentetik ERD şiddeti şartnameden sapıyor
`synthetic_eeg.py` genliği 0.60 ile çarpıyor; bu güçte ~%64 düşüş demek. Şartname ~%40 güç düşüşü istiyordu, genlik çarpanı sqrt(0.60) ≈ 0.775 olmalı. Abartılı ERD, ileride kod çözücü testlerini gerçekçi olmayan biçimde iyimser yapar.
**Düzeltme:** `SyntheticEEGSource(erd_power_drop=0.40)` parametresi ekle. Genlik çarpanı = sqrt(1 − erd_power_drop). ERD hem μ hem β bileşenine uygulansın.
**Test:** Uçtan uca testi %40 ile geçecek hale getir. Gerekirse pencereyi uzat (ör. 4 sn) veya Welch ayarlarını değiştir. Eşiği gevşetme: C4/C3 8–30 Hz güç oranı < 0.85 olmalı. Testin rastgelelikten dolayı ara sıra başarısız olmaması için tohum (seed) parametresi ekle.

## S5 — Simülatör gerçek başlıkla karışabilir
Sentetik akışın adı `X.on-SIM-0000`, yani `find_xon_stream`'in `X.on` önekiyle eşleşiyor. İkisi aynı anda açıksa alıcı rastgele birini seçebilir. Bu durumda kullanıcı simülatörle oynadığını fark etmeyebilir.
**Düzeltme:**
- `find_xon_stream(allow_simulator=False)` parametresi ekle. Varsayılan durumda adında `-SIM-` geçen akışlar atlansın.
- Simülatörü kullanan kod (testler, demo) `allow_simulator=True` versin.
- Birden fazla eşleşme varsa uyarı logla.
- Oyun HUD'unda veri kaynağı simülatörse "SIMULASYON" yazsın. (Bu bilgi `BCI_Control` üzerinden gelmiyorsa bu madde yalnızca alıcı tarafı için geçerli.)

## Kurallar
- `PLAN.md`'yi değiştirme. Dosya silme. Git commit yapma.
- Tüm testler (eski + yeni) geçmeli: `.venv\Scripts\python -m pytest -q`. Toplam süre < 2 dk.
- Hata ayıklarken çalıştırdığın her Python komutuna/betiğine bir zaman sınırı koy. Hiçbir komut 60 sn'den uzun beklememeli.
- Bitince `docs/agy_report_02.md` yaz. Her madde (S1–S5) için: ne değişti, hangi test kanıtlıyor, pytest çıktısı. Yapamadığın bir şey varsa açıkça yaz.
