# Görev 04 — Faz 3: Kalibrasyon Veri Toplama Aracı

Önce `PLAN.md`'nin **Faz 3** bölümünü (3.1–3.5) ve **Bölüm 20**'yi (Oturum Protokolü) dikkatle oku. Mevcut koddaki şu kalıpları yeniden kullan, kopyalama:
- `src/game/ball_roll.py` içindeki `MarkerPublisher`, `get_system_font` ve HUD sabitleri
- `src/acquisition/stream_receiver.py` içindeki `find_xon_stream` ve meta veri okuma
- `src/signal_quality/quality_metrics.py`

## Yapılacaklar

### 1. `config/calibration.yaml`
PLAN 3.1–3.3'teki tüm parametreler, kodda sabit değer olmayacak:
- Süreler: sabitleme 2 sn, ipucu 1 sn, imgeleme 4 sn, dinlenme 1.5–3 sn (rastgele).
- Run başına deneme sayısı: 20.
- Run sayısı.
- Run arası mola.
- Sınıf listesi.
- Hazır "oturum profilleri":
  - `mi2`: left, right, rest
  - `mi3`: + feet
  - `mi5`: + both_hands, + arithmetic

### 2. `src/calibration/paradigm.py` — saf mantık (headless test edilebilir)
- **Deneme sırası:** Her run'da sınıflar dengeli olmalı (20 deneme / sınıf sayısı; tam bölünmüyorsa fark en fazla 1). Sıra karıştırılmış olmalı; aynı sınıf en fazla 3 kez üst üste gelebilir. `seed` ile tekrarlanabilir olsun.
- **Zaman çizelgesi:** Her deneme için aşamaların (fixation, cue, imagery, rest) başlangıç ve bitiş zamanlarını üreten bir durum makinesi. Gerçek saat yerine verilen zamanla ilerleyebilmeli (test için).
- **Marker'lar** (yalnızca ASCII, PLAN 3.1 ile uyumlu):
  - `run_start`, `run_end`
  - `trial_start`, `fixation_start`
  - `cue_<sinif>`
  - `imagery_start`, `imagery_end`
  - `rest_start`, `trial_end`
  - `pause_start`, `pause_end`
  - `session_start`, `session_end`
- **Marker zamanlaması:** Marker zaman damgası, ekranın gerçekten güncellendiği ana (`pygame.display.flip()` çağrısından hemen sonra) `pylsl.local_clock()` ile alınmalı. Ekran çizilmeden önce gönderilen marker kabul edilmez.

### 3. `src/calibration/run_calibration.py` — pygame arayüzü
- Tam ekran veya pencere seçeneği; siyah/koyu gri arka plan, ortada `+` sabitleme.
- **İpucu:** Yön oku `pygame.draw.polygon` ile çizilsin; sol ← ve sağ → oklar. `feet` için aşağı ok, `both_hands` için yukarı ok, `arithmetic` için "100 − 7" gibi bir metin, `rest` için "DİNLEN" metni ya da daire. Ok ipucu süresince görünsün, sonra kaybolsun, `+` kalsın.
- Ekranda yanıp sönme yok (PLAN 6.1/21).
- **Başlamadan önce kontrol ekranı:**
  - X.on akışı aranır (`find_xon_stream`). `--simulator` bayrağıyla `allow_simulator=True` kullanılsın.
  - Akış meta verisinden impedanslar okunup tabloda gösterilir. PLAN 1.1b'deki eşikler `config/device_xon.yaml`'dan alınsın.
  - Son 5 sn'nin sinyal kalitesi canlı gösterilir: kanal başına 50 Hz ve 10 Hz güç oranı, renkli.
  - C3/Cz/C4 kapıyı geçmezse kullanıcı uyarılır; yine de "devam" seçeneği olsun.
- **Run akışı:**
  - Space ile run başlar.
  - Run arası molada ekranda "Mola – hazır olunca SPACE" yazar.
  - ESC oturumu güvenli biçimde bitirir; o ana kadarki markerlar gönderilmiş olur.
- **Kayıt:** LabRecorder'ı kendisi başlatmaz. Kullanıcıya oturum başında bir hatırlatma gösterir: "LabRecorder'da X.on + BCI_Markers akışlarını seçip kaydı başlatın". Kayıt dosya adı önerisini PLAN 3.5'teki adlandırma kuralıyla ekranda ve konsolda gösterir.
- **Oturum günlüğü:** Oturum sonunda `logs/` altına bir JSON yaz. İçeriği:
  - Katılımcı kodu, oturum, profil, seed
  - Deneme listesi (sınıf, run, deneme no)
  - Oturum başındaki impedans değerleri
  - Başlangıç ve bitiş saati
  - Yarıda kesildi mi
- **Komut satırı:**
  ```
  python -m src.calibration.run_calibration --subject sub-01 --session ses-YYYYMMDD --profile mi2 [--simulator] [--runs N] [--seed S] [--windowed]
  ```

### 4. Simülatörle uçtan uca kayıt testi (headless)
Bir test aracı veya pytest testi şunu doğrulasın:
- `SyntheticEEGSource` başlatılır. Paradigma kısaltılmış sürelerle (ör. aşamalar 0.2 sn) koşturulur.
- Simülatörün sınıfı ipucuna göre değiştirilir (left → 'left' vb.).
- Hem EEG hem `BCI_Markers` aynı süreç içinde pylsl ile kaydedilir.
- Ardından:
  - Her `imagery_start` – `imagery_end` aralığında EEG örnekleri var mı?
  - Marker sırası doğru mu?
  - Deneme sayıları sınıf başına dengeli mi?
- PLAN Faz 3 çıkış kriteri: "Markerlar ile EEG zaman damgaları doğru hizalı". Aynı test, EEG ve marker zaman damgalarının aynı LSL saatinde olduğunu ve hizalama hatasının < 20 ms olduğunu kontrol etsin.

### 5. Belgeler
`docs/calibration_guide.md` yaz. Kısa, Türkçe, kullanıcıya yönelik bir oturum rehberi olsun:
- Başlık takma
- İmpedans kontrolü
- LabRecorder ayarı
- Aracı çalıştırma
- PLAN 3.4'teki imgeleme yönergeleri
- Oturum sonrası

## Testler
- Deneme sırası dengesi ve en uzun seri ≤ 3; aynı seed ile aynı sıra.
- Durum makinesi aşama süreleri ve marker sırası (sahte saatle).
- Tüm marker adları ASCII.
- ESC ile yarıda kesilen oturumda `session_end` ve yarıda kesildi bilgisi.
- Madde 4'teki uçtan uca simülatör testi (toplam < 30 sn).
- Pencere açan test yok.

## Kurallar
- `PLAN.md`'yi değiştirme. Dosya silme. Git commit yapma.
- Mevcut 28 testin tamamı + yeni testler geçmeli: `.venv\Scripts\python -m pytest -q`. Toplam süre < 2 dk.
- Çalıştırdığın her komuta zaman sınırı koy; hiçbiri 60 sn'den uzun beklememeli.
- Bitince `docs/agy_report_04.md` yaz: ne yapıldı, hangi test neyi kanıtlıyor, pytest çıktısı, eksik/yapılamayanlar.
