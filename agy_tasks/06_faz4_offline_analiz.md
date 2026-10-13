# Görev 06 — Faz 4: Çevrimdışı (Offline) Analiz ve Model Seçimi

Önce `PLAN.md`'nin **Faz 4** bölümünü (4.1–4.5), **Faz 5.1**'i (nedensel filtre şartı) ve **Bölüm 17.3**'ü (sanity testleri) dikkatle oku. Mevcut kodu yeniden kullan:
- `config/device_xon.yaml` (kanal sırası/indeksleri)
- `config/calibration.yaml` (marker adları, süreler)
- `src/calibration/paradigm.py` (marker adları sabitleri)

**Gerçek kalibrasyon verisi henüz yok.** Bu yüzden bütün hat, aşağıda tanımlanan **çevrimdışı sentetik veri üreteci** ile geliştirilip test edilecek. Gerçek XDF okuyucu ise pilot dosya ile test edilecek.

## 0. Bağımlılıklar
`requirements.txt`'ye ekle ve `.venv`'e kur: `scikit-learn`, `pyriemann`, `matplotlib`, `joblib`. (MNE kullanmak istersen ekleyebilirsin ama zorunlu değil; scipy yeterli.)

## 1. Ortak veri yapısı — `src/processing/recording.py`
Bir `Recording` dataclass'ı tanımla. İçeriği:
- `eeg` (n_samples × 7, µV)
- `eeg_ts` (LSL zamanı)
- `acc` (n × 3)
- `srate`
- `ch_names`
- `markers` (liste: (ts, ad))
- `meta` (dict: impedanslar, kaynak dosya, oturum, run)

Bu yapı iki kaynaktan oluşturulabilsin:
- **`load_xdf(path)`:**
  - X.on akışını `device_xon.yaml` kuralıyla bulsun.
  - Marker akışını önce `BCI_Markers`, yoksa type=`Markers` olarak bulsun.
  - `pyxdf` clock-sync ve dejitter açık olsun.
  - İmpedansları meta veriden alsın.
  - Pilot XDF ile test edilecek; orada marker adları farklı, bu sorun değil.
- **Sentetik üreteç** (madde 2).

## 2. Çevrimdışı sentetik kalibrasyon verisi — `src/simulation/offline_dataset.py`
Gerçek zamanlı DEĞİL; saniyeler içinde bir oturumluk veri üretsin.
- **Paradigma ve markerlar:** `paradigm.py`'deki dengeli deneme sırasını ve zaman çizelgesini kullansın; markerlar gerçek araçla aynı adlarda olsun.
- **Sinyal içeriği:**
  - Pembe gürültü + μ (10 Hz) + β (20 Hz) + 50 Hz şebeke.
  - Sınıfa özgü ERD **imgeleme aralığında** uygulansın; giriş/çıkış yumuşak olsun (~0.5 sn rampa).
  - Deneme başına rastgele ERD şiddeti olsun: ör. ortalama `erd_power_drop`, deneme bazında ±%50 değişkenlik.
  - Kişiye özgü bir **μ tepe frekansı** olsun (ör. 9–12 Hz arası parametre). FBCSP'nin bunu yakalayabildiği görülsün.
- **Artefaktlar:**
  - Belirli bir oranda göz kırpma (F3/F4, yavaş, büyük).
  - Çene/EMG patlamaları (tüm kanallarda >30 Hz).
  - İvmeölçerde hareket.
  - Hangi denemelere artefakt eklendiği `meta`'da kayıtlı olsun (artefakt reddi testleri için).
- **Senaryo parametreleri:** `erd_power_drop` (0 = hiç ERD yok → şans seviyesi beklenir), `n_runs`, `profile`, `seed`, `session_drift` (oturumlar arası kanal kazancı / ritim genliği kayması).
- **`emg_confound` senaryosu:** Sınıf bilgisi beyin ritminde DEĞİL, yalnızca >30 Hz kas aktivitesinde bulunsun. PLAN 4.2'deki EMG kontrolünün bunu yakaladığı test edilecek.

## 3. Ön işleme — `src/processing/`
PLAN 4.1'e göre:
- **Filtreler** (`filters.py`):
  - 50 Hz (+100 Hz) çentik.
  - 8–30 Hz bant geçiren, Butterworth 4. derece.
  - **İki mod:** `zero_phase` (yalnızca görselleştirme ve ERD haritaları) ve `causal` (model eğitimi). **Model eğitimi varsayılan olarak `causal` kullanmalı** (PLAN 5.1: online ile dağılım uyumu).
  - Nedensel filtrenin blok blok uygulandığında tek seferde uygulamayla aynı sonucu verdiğini gösteren bir `StatefulFilter` sınıfı. Faz 5'te bu sınıf kullanılacak.
- **Uzamsal filtreler:** ham, küçük Laplace (C3' = C3 − ort(F3, P3, Cz); C4' = C4 − ort(F4, P4, Cz)), CAR.
- **Epoklama** (`epochs.py`):
  - `imagery_start` + 0.5 … +3.5 sn (yapılandırılabilir).
  - Etiketler `cue_*` marker'ından alınsın; deneme/run indeksi tutulsun.
- **Artefakt reddi** (`artifacts.py`):
  - Genlik eşiği.
  - F3/F4 göz kırpma tespiti.
  - >20 Hz EMG gücü (robust z-skor).
  - İvmeölçer hareket eşiği.
  - Eşikler **etiket kullanmadan** belirlensin.
  - Her reddin nedeni raporlansın.

## 4. Nörofizyolojik doğrulama — `src/processing/erd_analysis.py`
PLAN 4.2'ye göre:
- C3/Cz/C4 için sınıf başına ERD/ERS zaman-frekans haritaları. Referans: imgeleme öncesi sabitleme dönemi. Çıktı PNG.
- Kanal × frekans **r² (veya Fisher) haritası**. Çıktı PNG + sayısal matris.
- **EMG kontrolü:** 30–45 Hz bantta sınıflar arası fark istatistiksel olarak anlamlıysa (ör. permütasyon testi) açık bir UYARI üret.

## 5. Modeller — `src/models/pipelines.py`
PLAN 4.3'teki M1–M5'i scikit-learn `Pipeline` olarak kur:
- **M1:** log-bant gücü (C3, Cz, C4; μ ve β) + LDA (shrinkage).
- **M2:** CSP (8–30 Hz) + LDA.
- **M3:** FBCSP (4–8, 8–12, …, 26–30) + MI tabanlı öznitelik seçimi + LDA.
- **M4:** Kovaryans → Tanjant Uzayı + Lojistik Regresyon (pyriemann).
- **M5:** MDM (pyriemann).
- **M6 (EEGNet) yapılmayacak.**

**Veri sızıntısı kuralı:** CSP, öznitelik seçimi, kovaryans referansı ve normalize edici gibi tüm veri-güdümlü adımlar **pipeline içinde** olsun ve yalnızca eğitim katında `fit` edilsin.

## 6. Değerlendirme — `src/models/evaluation.py`
PLAN 4.4'e göre:
- **Oturum içi:** **run'a göre bloklu** çapraz doğrulama (`GroupKFold`, grup = run). Rastgele karıştırma YOK.
- **Oturumlar arası:** önceki oturumlarla eğit, son oturumla test.
- **Metrikler:** doğruluk, dengelenmiş doğruluk, Cohen's κ, karışıklık matrisi, ITR (bit/dk; Wolpaw formülü, deneme süresi yapılandırılabilir).
- **Şans seviyesi:** etiket permütasyon testi (en az 100 permütasyon; testlerde daha az olabilir) → p-değeri ve %95 şans eşiği.
- **Zaman çözünürlüklü doğruluk:** deneme içinde kayan pencere (ör. 1 sn pencere, 0.25 sn adım) → grafik.
- **Sınıf seçimi** (PLAN 4.5): tüm sınıf çiftleri için ikili doğruluk matrisi. "Yukarı" için `both_hands` ile `arithmetic`'in karşılaştırılması; hangisinin diğer sınıflardan daha iyi ayrıştığı raporlansın.

## 7. Komut satırı aracı ve model kaydı — `src/models/offline_analysis.py`
```
python -m src.models.offline_analysis --xdf data/sub-01/ses-*/...xdf [...] --out results/sub-01 [--models M1,M2,M3,M4,M5] [--synthetic --erd 0.4 --runs 4 --profile mi2 --seed 1]
```
- Tüm adımları koştursun ve çıktı klasörüne şunları yazsın:
  - Şekiller.
  - `results.json`.
  - İnsan tarafından okunabilir `report.md`: model karşılaştırma tablosu, şans eşiği, EMG uyarısı, reddedilen deneme oranı, sınıf seçimi önerisi.
- En iyi modeli `models/<subject>/<tarih>_<model>.joblib` olarak kaydetsin. Yanında Faz 5'in ihtiyaç duyacağı her şeyi içeren bir meta veri JSON'u olsun:
  - Kanal listesi ve sırası.
  - Uzamsal filtre.
  - Filtre parametreleri (`causal`).
  - Pencere uzunluğu.
  - Sınıf listesi ve etiket sırası.
  - Örnekleme hızı.
  - Eğitim tarihi.
  - CV skoru.
  - Kullanılan veri dosyaları.

## 8. Testler (`tests/test_offline_*.py`)
Hepsi sentetik veriyle, hızlı:
1. `StatefulFilter`: blok blok == tek seferde (hata < 1e-6). `zero_phase` ve `causal` ayrı fonksiyonlar.
2. Epoklama: deneme sayısı = marker sayısı. Etiketler `cue_*` ile birebir.
3. Artefakt reddi: üretecin işaretlediği artefaktlı denemelerin ≥ %80'i yakalanmalı. Temiz denemelerin ≤ %10'u yanlışlıkla reddedilmeli.
4. **Sinyal varken:** `erd_power_drop=0.4`, mi2 (`left`/`right`), 4 run → en az bir model run-bloklu CV'de ≥ %75 doğruluk. Permütasyon p < 0.05.
5. **Sinyal yokken (sanity, PLAN 17.3):** `erd_power_drop=0.0` → tüm modeller şans seviyesinde: 2 sınıf için doğruluk %35–%65 arası ve permütasyon p > 0.05. Bu test, sızıntı olmadığının kanıtıdır.
6. **Etiket karıştırma:** gerçek veride etiketler karıştırılınca doğruluk şans seviyesine düşmeli.
7. **EMG karıştırıcı:** `emg_confound` senaryosunda EMG uyarısı üretilmeli. Sinyal varken normal senaryoda üretilmemeli.
8. `load_xdf` pilot XDF ile çalışmalı: 7 EEG kanalı, ~250 Hz, impedanslar dolu, marker listesi boş değil.
9. Kaydedilen model + meta veri tekrar yüklenip aynı tahminleri vermeli.
10. Uçtan uca CLI: `--synthetic` ile `report.md` ve `results.json` üretilmeli. Geçici bir klasör kullan, test sonunda temizle.

Tüm test süresi < 3 dk. Gerekirse testlerde permütasyon sayısını düşür ama parametre olarak bırak.

## Kurallar
- `PLAN.md`'yi değiştirme. Dosya silme. Git commit yapma.
- `results/` ve `models/` git dışında olmalı; `.gitignore`'u kontrol et, `results/` yoksa ekle.
- Testleri çalıştırırken çıktıyı **komutla** dosyaya yaz:
  ```
  .venv\Scripts\python -m pytest -q -rA > docs/pytest_output_06.txt 2>&1
  ```
  Rapora test adı veya sonuç **uydurma**. Denetçi `--collect-only` ve kendi ölçümleriyle karşılaştıracak.
- Çalıştırdığın her komuta zaman sınırı koy; hiçbiri 120 sn'den uzun beklememeli.
- Bitince `docs/agy_report_06.md` yaz. İçinde:
  - Ne yapıldı.
  - Senaryo bazında gerçek ölçülen doğruluklar (sinyal var / yok / EMG): her model için ortalama ± std.
  - Pytest çıktı dosyasının yolu.
  - Yapılamayanlar.
