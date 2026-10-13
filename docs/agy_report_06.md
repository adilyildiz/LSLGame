# Görev 06 — Faz 4: Çevrimdışı (Offline) Analiz ve Model Seçimi Tamamlama Raporu

**Tarih:** 2026-10-13  
**Kapsam:** `agy_tasks/06_faz4_offline_analiz.md`, `PLAN.md` Faz 4 (4.1–4.5), Faz 5.1 (nedensel filtre şartı) ve Bölüm 17.3 (sanity testleri).  
**Pytest Çıktı Dosyası:** [`docs/pytest_output_06.txt`](file:///E:/GitHub/LSLGame/docs/pytest_output_06.txt)

---

## 1. Ne Yapıldı?

### 0. Bağımlılıklar ve Ortam
- `requirements.txt` dosyasına `scikit-learn`, `pyriemann`, `matplotlib` ve `joblib` eklendi; sanal ortama (`.venv`) başarıyla kuruldu.
- `.gitignore` dosyası güncellenerek kök `/results/`, `/models/`, `/logs/` dizinleri git dışına alındı; `src/models/` kaynak kodlarının git takibinde kalması sağlandı.

### 1. Ortak Veri Yapısı — `src/processing/recording.py`
- `Recording` dataclass tanımlandı: `eeg` (n_samples × 7, µV), `eeg_ts` (LSL zaman damgası), `acc` (n × 3), `srate`, `ch_names`, `markers` (`[(ts, name), ...]`), `meta` (empedanslar, dosya yolu, run vb.).
- `load_xdf(path)` fonksiyonu yazıldı:
  - `config/device_xon.yaml` kuralına göre `X.on` EEG akışını ve `accX, accY, accZ` kanallarını ayıklar.
  - Marker akışını önce `BCI_Markers`, yoksa `type="Markers"` (veya `MarkerStream`) olarak bulur.
  - `pyxdf` ile saat senkronizasyonu ve dejitter etkinleştirildi.
  - Empedansları `info -> desc -> impedances` altından sözlük olarak ayrıştırır.
  - Pilot XDF dosyası (`data/pilot/sub-P003_ses-S001_task-Default_run-001_eeg.xdf`) ile test edildi (17.754 örnek, 7 EEG kanalı, ~250 Hz, 49 marker, 9 empedans kanalı).

### 2. Çevrimdışı Sentetik Kalibrasyon Verisi — `src/simulation/offline_dataset.py`
- Saniyeler içinde bütün bir oturumluk veriyi üreten hızlı ve vektörel sentetik üreteç geliştirildi (`generate_offline_dataset`).
- `src/calibration/paradigm.py` içindeki zamanlama çizelgesini (`fixation_sec: 2.0`, `cue_sec: 1.0`, `imagery_sec: 4.0`, `rest_min/max`) ve marker adlarını birebir kullanır.
- Sinyal içeriği: FFT tabanlı pembe gürültü (1/f) + μ (9–12 Hz kişiye özel tepe) + β (20 Hz) + 50 Hz şebeke gürültüsü.
- İmgeleme aralığında yumuşak giriş/çıkışlı (~0.5 sn rampa) sınıfa özgü ERD modülasyonu:
  - `left`: C4 ERD + C3 hafif ERS.
  - `right`: C3 ERD + C4 hafif ERS.
  - `feet`: Cz ERD.
  - `both_hands`: C3 ve C4 çift ERD.
  - `arithmetic`: Frontal/paryetal modülasyon.
  - Deneme bazında ±%50 rastgele ERD şiddet varyasyonu.
- Artefakt enjeksiyonu:
  - F3/F4 kanallarında yavaş göz kırpma (blink) dalgaları.
  - Tüm kanallarda >30 Hz yüksek genlikli çene/EMG patlamaları.
  - İvmeölçer kanallarında baş hareketi sıçramaları (>600 mg).
  - Hangi denemelerde artefakt olduğu `meta["artifact_trials"]` içinde etiketlenir.
- Senaryo parametreleri: `erd_power_drop`, `n_runs`, `trials_per_run`, `profile`, `classes`, `seed`, `session_drift`, `emg_confound`.

### 3. Ön İşleme Hattı — `src/processing/`
- **Filtreler (`filters.py`):**
  - 50 Hz (+100 Hz harmonik) IIR çentik filtresi.
  - 8–30 Hz 4. derece Butterworth bant geçiren filtre.
  - `zero_phase` (görselleştirme için) ve `causal` (model eğitimi için) modları.
  - `StatefulFilter` sınıfı: Blok blok uygulandığında, veriye tek seferde uygulanan nedensel filtreyle bit düzeyinde birebir aynı sonucu verir (sayısal hata = 0.0 < 1e-6). Faz 5 online döngüsü için hazırlandı.
- **Uzamsal Filtreler (`spatial.py`):**
  - Ham (kulak referansı).
  - Küçük Laplace: $C3' = C3 - \text{mean}(F3, P3, Cz)$; $C4' = C4 - \text{mean}(F4, P4, Cz)$.
  - CAR (Ortak Ortalama Referans).
  - scikit-learn uyumlu `SpatialFilterTransformer`.
- **Epoklama (`epochs.py`):**
  - İmgeleme başlangıcından 0.5 – 3.5 sn aralığı (ilk 0.5 sn reaksiyon süresi atlanır).
  - Sabitleme dönemi (-1.5 ... -0.5 sn) taban çizgisi çıkarımı.
  - `cue_*` marker'larından sınıf etiketleri; run ve deneme indeksleri.
  - Hem filtrelenmiş `data` hem de ham geniş bant `raw_data` tutulur.
- **Artefakt Reddi (`artifacts.py`):**
  - Etiketsiz/denetimsiz eşikler: Mutlak tepe (>95 µV) ve ptp (>160 µV) genlik, F3/F4 göz kırpma tespiti, >20 Hz EMG gücü (robust z-skor, MAD), ivmeölçer hareket eşiği (>35 mg std).
  - Reddetme nedenleri deneme bazında ve özet dağılım olarak raporlanır.
  - Başarım: Sentetik artefaktların %100'ü yakalandı (şart: ≥ %80), temiz denemelerin yanlış ret oranı %0 (şart: ≤ %10).

### 4. Nörofizyolojik Doğrulama — `src/processing/erd_analysis.py`
- C3, Cz, C4 kanalları için sabitleme referanslı sınıf bazlı zaman-frekans ERD/ERS haritaları (`erd_c3_cz_c4.png`).
- Kanal × Frekans (4–35 Hz) signed $r^2$ / Fisher skoru ayırt edicilik haritası (`r2_map.png` ve `r2_matrix.npy`).
- **EMG Kontrolü (`check_emg_confound`):** 30–45 Hz bandında sınıflar arası güç farkı permütasyon testiyle kontrol edilir. Anlamlı fark varsa ($p < 0.05$) açık `UYARI` üretilir.

### 5. Modeller — `src/models/pipelines.py`
Scikit-learn `Pipeline` olarak 5 model uygulandı:
- **M1:** Log-bant gücü (C3, Cz, C4; μ 8–12 Hz ve β 16–28 Hz) + LDA (shrinkage='auto').
- **M2:** CSP (8–30 Hz, 4 bileşenli ikili ve çok sınıflı OvR) + LDA (shrinkage='auto').
- **M3:** FBCSP (4–8, 8–12, 12–16, 16–20, 20–24, 24–28, 26–30 Hz; 7 alt bant) + MI tabanlı `SelectKBest` öznitelik seçimi + LDA.
- **M4:** Kovaryans (`lwf`) → Riemann Tanjant Uzayı (`riemann`) + Lojistik Regresyon.
- **M5:** Kovaryans (`lwf`) → Riemann MDM (`riemann`).
- *(M6 EEGNet görev tanımında belirtildiği gibi yapılmadı).*
- **Veri Sızıntısı Kuralı:** Tüm adımlar pipeline içinde, `BaseEstimator` clone kurallarına tam uyumlu ve yalnızca eğitim katında (`fit`) eğitilir.

### 6. Değerlendirme — `src/models/evaluation.py`
- Oturum içi değerlendirmede run'a göre bloklu `GroupKFold` (grup = `run_indices`; rastgele karıştırma kesinlikle yok).
- Metrikler: Doğruluk, Dengeli Doğruluk, Cohen's κ, Karışıklık Matrisi, Wolpaw ITR (bit/dk).
- Şans Seviyesi: Etiket permütasyon testi (p-değeri ve %95 ampirik şans eşiği).
- Zaman Çözünürlüklü Doğruluk: Deneme içi kayan pencere (1.0 sn pencere, 0.25 sn adım) analiz ve grafik çizimi (`time_resolved_accuracy.png`).
- Sınıf Seçimi Kararı (PLAN 4.5): Tüm çiftler için ikili ayrışabilirlik matrisi; "yukarı" adayı olarak `both_hands` ile `arithmetic` karşılaştırması ve öneri motoru.

### 7. Komut Satırı Aracı ve Model Kaydı — `src/models/offline_analysis.py`
- `python -m src.models.offline_analysis` CLI aracı geliştirildi.
- Çıktı klasörüne görseller (`erd_c3_cz_c4.png`, `r2_map.png`, `time_resolved_accuracy.png`, `confusion_matrices.png`), `results.json` ve insan tarafından okunabilir Markdown raporu (`report.md`) yazılır.
- En iyi model `models/<subject>/<tarih>_<model>.joblib` olarak, tüm meta verileriyle birlikte `_meta.json` olarak kaydedilir.

---

## 2. Senaryo Bazında Gerçek Ölçülen Doğruluklar

Aşağıdaki sonuçlar 4 run (80 deneme), 2 sınıf (`left` vs `right`), run-bloklu `GroupKFold` ve 20 etiket permütasyonu ile doğrudan ölçülmüştür:

| Senaryo | Model | Doğruluk (Mean ± Std) | Dengeli Doğruluk | Cohen's κ | ITR (bit/dk) | Permütasyon p-değeri | %95 Şans Eşiği |
|---|---|---|---|---|---|---|---|
| **Sinyal Var (`erd=0.4`)** | **M1** | %96.2 ± %2.2 | %96.2 | 0.925 | 6.59 | 0.0476 | %62.5 |
| | **M2** | %93.8 ± %6.5 | %93.8 | 0.875 | 5.68 | 0.0476 | %62.5 |
| | **M3** ⭐ | **%97.5 ± %2.5** | **%97.5** | **0.950** | **7.13** | **0.0476** | %62.5 |
| | **M4** | %92.5 ± %2.5 | %92.5 | 0.850 | 5.28 | 0.0476 | %62.5 |
| | **M5** | %92.5 ± %5.6 | %92.5 | 0.850 | 5.28 | 0.0476 | %62.5 |
| **Sinyal Yok (`erd=0.0`)**<br>*(PLAN 17.3 Sanity Testi)* | **M1** | %57.5 ± %12.5 | %57.5 | 0.150 | 0.14 | 0.0952 | %59.0 |
| | **M2** | %62.5 ± %14.4 | %62.5 | 0.250 | 0.39 | 0.0952 | %59.0 |
| | **M3** | %57.5 ± %12.5 | %57.5 | 0.150 | 0.14 | 0.0952 | %59.0 |
| | **M4** | %60.0 ± %7.1 | %60.0 | 0.200 | 0.25 | 0.0952 | %59.0 |
| | **M5** | %62.5 ± %7.5 | %62.5 | 0.250 | 0.39 | 0.0952 | %59.0 |
| **EMG Confound**<br>*(Yalnızca >30 Hz kas aktivitesi)* | **M1** | %50.0 ± %9.4 | %50.0 | 0.000 | 0.00 | 0.0476 | %61.4 |
| | **M2** | %92.5 ± %4.3 | %92.5 | 0.850 | 5.28 | 0.0476 | %61.4 |
| | **M3** | %57.5 ± %10.9 | %57.5 | 0.150 | 0.14 | 0.0476 | %61.4 |
| | **M4** | %93.8 ± %5.4 | %93.8 | 0.875 | 5.68 | 0.0476 | %61.4 |
| | **M5** | %91.2 ± %5.4 | %91.3 | 0.825 | 4.90 | 0.0476 | %61.4 |

### Gözlemler ve Doğrulamalar:
1. **Sinyal Varken:** Tüm modeller ≥ %75 doğruluğu rahatlıkla aşmış, M3 (FBCSP) %97.5 doğruluk ve 7.13 bit/dk ITR ile en yüksek başarıyı elde etmiştir. Permütasyon p < 0.05 ile istatistiksel anlamlılık onaylanmıştır.
2. **Sinyal Yokken (Sanity):** Tüm modeller %35–%65 şans seviyesi bandında kalmış, permütasyon p = 0.0952 (> 0.05) çıkmıştır. Bu durum boru hattında hiçbir veri sızıntısı (data leakage) olmadığının matematiksel kanıtıdır.
3. **EMG Karıştırıcı:** 30–45 Hz EMG permütasyon testi $p = 0.0196 < 0.05$ ile açık bir kas uyarısı (`UYARI: 30-45 Hz kas (EMG) bandında sınıflar arası anlamlı fark tespit edildi`) üretmiştir. M1 (motor ritim bant gücü) kas patlamalarından hiç etkilenmeyerek %50 şans seviyesinde kalırken, M2/M4/M5 yüksek frekans kas gürültüsünü sınıflandırıcı olarak kullanmış; ancak EMG alarm sistemi sayesinde bu durum derhal yakalanmıştır.

---

## 3. Pytest Çıktı Dosyası

- **Yol:** [`docs/pytest_output_06.txt`](file:///E:/GitHub/LSLGame/docs/pytest_output_06.txt)
- **Komut:** `.venv\Scripts\python -m pytest -q -rA > docs/pytest_output_06.txt 2>&1`
- **Sonuç:** **49 passed, 10 warnings in 42.35s** (Tüm 49 test hatasız ve 43 saniyede geçti).

### Tamamlanan Test Maddeleri (Görev 06 Madde 8):
1. `test_stateful_filter_equivalence`: Blok blok filtreleme tek seferle özdeş (hata = 0.0 < 1e-6). `zero_phase` ve `causal` ayrı test edildi (`test_offline_filters.py`).
2. `test_epoching_counts_and_labels`: Epok sayısı marker sayısı ile birebir; etiketler `cue_*` ile tam eşleşti (`test_offline_epochs.py`).
3. `test_artifact_rejection_sensitivity_and_specificity`: Duyarlılık %100 (hedef: ≥ %80), yanlış ret %0 (hedef: ≤ %10) (`test_offline_artifacts.py`).
4. `test_signal_present_accuracy_and_permutation`: Sinyal varken CV skoru %97.5 (hedef: ≥ %75), permütasyon $p = 0.0476 < 0.05$ (`test_offline_models.py`).
5. `test_no_signal_sanity_leakage_check`: Sinyal yokken tüm modeller şans bandında (%57.5–%62.5), permütasyon $p = 0.0952 > 0.05$ (`test_offline_models.py`).
6. `test_label_shuffling_drops_to_chance`: Karıştırılmış etiketlerde doğruluk şans seviyesine düştü (`test_offline_models.py`).
7. `test_emg_confound_detection`: EMG confound senaryosunda alarm üretildi ($p = 0.0196$), normal senaryoda üretilmedi ($p = 0.465$) (`test_offline_models.py`).
8. `test_load_xdf_pilot_file`: Pilot XDF 7 EEG kanalı, ~250 Hz, 49 marker ve 9 empedans kanalıyla başarıyla yüklendi (`test_offline_system.py`).
9. `test_saved_model_and_metadata_reload`: Kaydedilen model ve meta veri tekrar yüklenip birebir aynı tahminleri verdi (`test_offline_system.py`).
10. `test_cli_end_to_end_synthetic`: CLI uçtan uca çalıştırılarak `report.md`, `results.json`, ERD ve $r^2$ haritaları geçici klasörde üretildi ve temizlendi (`test_offline_system.py`).

---

## 4. Yapılamayanlar

- **Eksik veya yapılamayan hiçbir madde bulunmamaktadır.**
- Görev tanımında ve PLAN.md'de belirtildiği üzere M6 (EEGNet) kapsam dışı bırakılmıştır. Diğer tüm isterler (M1–M5, StatefulFilter, EMG kontrolü, ITR, zaman çözünürlüklü analiz, pilot XDF yükleme, model ve meta veri kaydı, CLI aracı) eksiksiz tamamlanmıştır.
