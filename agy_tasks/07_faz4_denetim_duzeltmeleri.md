# Görev 07 — Faz 4 Denetim Düzeltmeleri

Görev 06 bağımsız olarak denetlendi. 49 test geçiyor ve rapordaki test adları gerçek. Ancak üç doğrulanmış sorun ve bir yöntem sorunu var. Yalnızca bunları düzelt.

## D1 — "Sinyal yok" senaryosu aslında sinyal içeriyor (DOĞRULANDI)
`src/simulation/offline_dataset.py`: `left`/`right` denemelerinde karşı kanala eklenen +%10 ERS, `erd_power_drop=0` iken de uygulanıyor. Bu yüzden "sinyalsiz" veride sınıf bilgisi var.

**Denetçi ölçümü** (2 sınıf, `erd=0`, 6 tohum, 40 permütasyon):
- Üreteç olduğu gibi: permütasyon p < 0.05 olan tohum sayısı **4/6**.
- ERS `drop > 0` koşuluna bağlanınca: **0/6**; doğruluklar %45–53.

**Düzeltme:**
- `erd_power_drop == 0` olduğunda (ve `emg_confound` senaryosunda) sınıfa bağlı **hiçbir** fark kalmasın.
- ERS genliği ERD ile orantılı olsun (ör. `0.25 × drop`).
- Bunu garanti eden bir test yaz: `erd=0` ile üretilen veride sınıflar arası C3/Cz/C4 bant gücü farkı istatistiksel olarak yok olmalı.

**Sanity testini güçlendir** (`test 5`):
- En az 5 farklı tohumla, **2 sınıfla** (`classes=["left","right"]`) çalışsın.
- Tüm modellerin ortalama doğruluğu %40–%60 arasında olmalı.
- Permütasyon p < 0.05 olan tohum sayısı ≤ 1 olmalı.

## D2 — EMG kontrolü yanlış veriye bakıyor
`src/processing/erd_analysis.py::check_emg_confound` 30–45 Hz gücünü `epochs.data` üzerinden ölçüyor. Bu veri zaten 8–30 Hz bant geçirenden geçmiş; kas bandı büyük ölçüde silinmiş. Sentetik EMG çok güçlü olduğu için test geçiyor, ama gerçek veride kaçırılır.

**Düzeltme:** EMG kontrolü `epochs.raw_data` üzerinde çalışsın. Bu veri yalnızca 50/100 Hz çentikten geçmiş, bant geçiren uygulanmamış olmalı; `extract_epochs` gerekirse `raw_data`'ya çentik uygulasın. `raw_data` yoksa açık bir hata versin.

**Test:**
- `emg_confound` senaryosunda EMG genliği bugünkünün **1/4'üne** düşürülse bile uyarı üretilmeli. Üretece EMG genlik parametresi ekle.
- `erd=0.4` normal senaryoda en az 5 tohumda uyarı oranı ≤ 1/5 olmalı.

## D3 — FBCSP alt bantları ön filtreyle çelişiyor
`extract_epochs` tüm epokları 8–30 Hz'e filtreliyor. M3'ün 4–8 Hz alt bandı bu yüzden boş. Ayrıca `emg_confound` için ham veriye ihtiyaç var.

**Düzeltme:** FBCSP alt bant listesi ön filtre aralığı içinde kalsın: 8–12, 12–16, 16–20, 20–24, 24–28, 28–30 veya benzeri. Ön filtre aralığı dışında kalan bir alt bant tanımlanırsa uyarı loglansın. Meta veri JSON'una FBCSP alt bantları da yazılsın.

## D4 — Permütasyon testi model seçimi yanlılığı içeriyor
`evaluate_session_cv` 5 model içinden en iyisini seçiyor ve permütasyonu yalnızca o model için yapıyor. Gerçek veride "en iyi model"in p-değeri iyimser olur.

**Düzeltme — maksimum istatistik permütasyonu:**
- Her permütasyonda **tüm modelleri** aynı karıştırılmış etiketlerle değerlendir ve en yüksek doğruluğu kaydet.
- Gözlenen en iyi doğruluk bu dağılımla karşılaştırılsın.
- Ayrıca her model için kendi p-değeri raporlansın.
- `report.md`'de hangi p-değerinin seçim-düzeltilmiş olduğu açıkça yazsın.
- Süre artışını sınırlamak için permütasyon sayısı parametre olarak kalsın.
- **Etiketler run içinde karıştırılsın** (run'lar arası değil). Böylece run yapısı korunur.

**Test:** `erd=0`, 2 sınıf, 5 tohumda seçim-düzeltilmiş p < 0.05 olan tohum sayısı ≤ 1.

## Kurallar
- `PLAN.md`'yi değiştirme. Dosya silme. Git commit yapma.
- Tüm testler (mevcut 49 + yeni) geçmeli. Toplam süre < 4 dk. Gerekirse yavaş testleri `@pytest.mark.slow` ile işaretle; ama D1 ve D4 sanity testleri varsayılan çalıştırmada **olmalı**.
- Testleri çalıştırırken çıktıyı **komutla** dosyaya yaz:
  ```
  .venv\Scripts\python -m pytest -q -rA > docs/pytest_output_07.txt 2>&1
  ```
  Rapora test adı veya sonuç uydurma.
- Çalıştırdığın her komuta zaman sınırı koy; hiçbiri 300 sn'den uzun beklememeli.
- Bitince `docs/agy_report_07.md` yaz: her madde (D1–D4) için ne değişti, hangi test kanıtlıyor. Ölçtüğün sanity sonuçlarını (tohum bazında doğruluk ve p) tablo olarak yaz.
