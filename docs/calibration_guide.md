# Graz-BCI Kalibrasyon Oturumu Kullanıcı Rehberi

Bu rehber, **PLAN.md Faz 3** ve **Bölüm 20 (Oturum Protokolü)** doğrultusunda, Brain Products X.on başlığıyla kişiye özel motor imgeleme (MI) kalibrasyon verisi toplarken izlenecek adımları açıklar.

---

## 1. Oturum Öncesi Hazırlık ve Başlık Takma

1. **Ortam ve Güç:**
   - Bilgisayarı mümkünse **pilde** çalıştırın (şarj adaptörü 50 Hz şebeke gürültüsünü artırabilir).
   - Windows güç modunu "En iyi performans" yapın.
   - Ortam sessiz, loş olmayan sabit aydınlatmalı olmalıdır. Sandalye rahat, kollar ve omuzlar gevşek pozisyonda dinlenmelidir.
   - Son 2 saat içinde yoğun kafein tüketilmemiş olmalıdır (durum oturum günlüğüne not edilir).

2. **Başlık ve Elektrot Konumlandırma:**
   - X.on sünger elektrotlarını üretici talimatlarına göre (tuzlu su / salin solüsyonu ile) nemlendirin. Aşırı ıslak süngerler köprü oluşturabilir, kuru süngerler impedansı yükseltir.
   - Başlığın şarjını kontrol edin. Bluetooth adaptörünü başlığa yakın (≤ 2 m) tutun.
   - **Cz elektrotunu konumlandırın:** Burun kökü (nasion) ile kafatası arkasındaki çukur (inion) arasındaki mesafenin %50'si ve kulak tragusları arasındaki mesafenin %50'sinin kesiştiği tepe noktayı belirleyip başlığın Cz elektrodunu tam bu noktaya getirin.
   - C3 ve C4 elektrotlarının kafa derisine doğrudan temas ettiğinden ve saçların aralandığından emin olun.

3. **X.on PC Uygulaması ve LSL:**
   - X.on uygulamasını açın, başlığı bağlayın ve **LSL Yayınını (LSL Stream)** etkinleştirin.

---

## 2. İmpedans ve Sinyal Kalitesi Kontrolü

Kalibrasyon aracını başlatarak kontrol ekranını açın:

```powershell
python -m src.calibration.run_calibration --subject sub-01 --session ses-20261015 --profile mi2
```
*(Sentetik simülasyonla test etmek için `--simulator` bayrağını ekleyebilirsiniz).*

1. **Kontrol Ekranında İnceleme:**
   - **İmpedans Değerleri:**
     - **Yeşil:** < 40 kΩ (Kabul edilebilir; Cz için hedef < 20 kΩ).
     - **Sarı:** 40–70 kΩ (Orta; sünger nemini kontrol edin).
     - **Kırmızı:** > 70 kΩ (Yüksek direnç; saçları açın, süngeri yeniden nemlendirin).
   - **Canlı Kalite Paneli (Son 5 Saniye):**
     - RMS genliği 3–70 µV aralığında olmalıdır.
     - 50 Hz şebeke gürültüsünün 10 Hz mu ritmine oranı (50/10 dB) ≤ 3 dB olmalıdır.
     - Düz çizgi (flatline) veya kırpılma (clipping) olmamalıdır.
   - **C3 / Cz / C4 Kapısı:** Motor korteks üzerindeki bu üç elektrot yeşil duruma gelene kadar başlığı ayarlayın.

---

## 3. LabRecorder Kurulumu ve Kayıt

> **ÖNEMLİ:** Kalibrasyon aracı LabRecorder'ı otomatik başlatmaz. Kaydın LabRecorder ile harici olarak başlatılması gerekir.

1. **LabRecorder'ı Başlatın:**
   - LabRecorder uygulamasını açın ve "Update" butonuna basın.
2. **Akışları Seçin:**
   - `X.on` (veya `X.on-0000` / EEG akışı)
   - `BCI_Markers` (Kalibrasyon olay işaretçileri)
3. **Kayıt Dosya Yolunu Ayarlayın:**
   - Kalibrasyon ekranında önerilen formatı kullanın:
     ```
     data/sub-01/ses-20261015/sub-01_ses-20261015_task-MI_run-01.xdf
     ```
4. **Temel (Baseline) Kaydı:**
   - Run'lara geçmeden önce kaydı başlatıp 1 dakika göz açık, 1 dakika göz kapalı dinlenme kaydı alın.

---

## 4. Kalibrasyon Aracının Çalıştırılması

### Komut Satırı Seçenekleri
```powershell
python -m src.calibration.run_calibration [SEÇENEKLER]
```
- `--subject <code>`: Katılımcı kodu (örn. `sub-01`).
- `--session <ses-id>`: Oturum kodu (varsayılan: günün tarihi `ses-YYYYMMDD`).
- `--profile <mi2|mi3|mi5>`:
  - `mi2`: Sol El, Sağ El, Dinlenme (4 run, ~25 dk).
  - `mi3`: + Ayak (6 run).
  - `mi5`: + İki El, + Aritmetik (10 run, ~55 dk).
- `--runs <N>`: İsteğe bağlı olarak run sayısını değiştirme.
- `--seed <S>`: Rastgele deneme sırası için tekrarlanabilir tohum.
- `--windowed`: Tam ekran yerine pencere modunda açma.
- `--simulator`: Gerçek başlık olmadan sentetik EEG akışını dinleme.

### Akış ve Tuş Kontrolleri
- Kontrol ekranında **[SPACE]**: Kalibrasyonu başlatır.
- Run sırasında ekranda Graz-BCI sırası ilerler:
  - `+` (2 sn): Sabitleme (gözünüzü odaklayın).
  - `←` / `→` / simge (1 sn): İpucu (göreve hazırlanın).
  - `+` (4 sn): Motor imgeleme (sürekli hayal edin).
  - Boş ekran (1.5–3 sn): Dinlenme (göz kırpın, yutkunun).
- Run aralarında ekran: `"MOLA — hazır olunca SPACE"`. Dinlenin ve hazır olunca **[SPACE]** tuşuna basarak sonraki run'a geçin.
- **[ESC]**: Oturumu güvenle durdurur, `session_end` marker'ını gönderir ve log dosyasını kaydeder.

---

## 5. PLAN 3.4 Motor İmgeleme Yönergeleri (Kullanıcıya)

Kalibrasyonun başarısı, kullanıcının motor korteks aktivasyonunu doğru ve temiz gerçekleştirmesine bağlıdır:

1. **Kinestetik İmgeleme Yapın:**
   - Hareketi dışarıdan bir video izler gibi "görsel" hayal etmeyin.
   - **Kaslarınızın gerildiğini, bir topu veya yayı var gücünüzle sıktığınızı, elinizdeki kas hissini hayal edin.** Kinestetik imgeleme çok daha güçlü ERD (desenkronizasyon) üretir.
2. **Gerçek Hareket Yapmayın:**
   - Parmaklarınızı veya kollarınızı milimetrik bile olsa oynatmayın, dişlerinizi sıkmayın. Kas kasılması (EMG artefaktı) yapay ve yanıltıcı bir "başarı" doğurur, gerçek BCI modelini bozar.
3. **Göz Kırpma ve Yutkunma Disiplini:**
   - 4 saniyelik imgeleme süresince gözlerinizi kırpmamaya, göz hareketlerinden (EOG) ve yutkunmaktan kaçınmaya çalışın.
   - Dinlenme aşamasında (boş ekran) rahatça gözlerinizi kırpabilir ve yutkunabilirsiniz.
4. **Ritmik İmgeleme:**
   - Saniyede yaklaşık bir kez sıkıp bırakma hissini ritmik olarak tekrarlamak sinyal tutarlılığını artırır.
5. **Hissi Hatırlama (Isınma):**
   - Oturuma başlamadan önce elinizi birkaç kez gerçekten sıkıp bırakarak kas hafızanızı ve o hissi tazeleyin.

---

## 6. Oturum Sonrası Kapatma

1. **LabRecorder:** Kaydı durdurun. XDF dosya boyutunun makul (genelde run başına onlarca megabayt) olduğunu doğrulayın.
2. **Başlık Temizliği:** Başlığı çıkarın. Süngerleri üretici talimatına uygun şekilde saf su ile yıkayıp kurutun.
3. **Oturum Günlüğü:**
   - Kalibrasyon aracının otomatik oluşturduğu `logs/calibration_sub-XX_*.json` dosyasını kontrol edin.
   - `docs/session_log.md` dosyasına tarih, saat, uyku, kafein, elektrot kalitesi ve yorgunluk puanını (1–10) not edin.
4. **Yedekleme:** `data/` altındaki XDF dosyalarını ikincil bir diske veya güvenli sunucuya yedekleyin.
