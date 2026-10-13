# LSLGame — X.on EEG ile Düşünceyle Kontrol Edilen Oyun: Detaylı Proje Planı

> **Amaç:** Brain Products **X.on** EEG başlığını takıp, ekrandaki bir nesneyi **yalnızca zihinsel görevlerle** sağa, sola, yukarı ve aşağı hareket ettirerek oynanabilen bir oyun geliştirmek.
>
> **Kapsam:** Bu belge yalnızca plandır; kod içermez. Her faz, bir sonraki faza geçmeden önce karşılanması gereken **çıkış kriterleri** ile tanımlanmıştır.

---

## İçindekiler

1. [Gerçekçi Beklentiler — Önce Bunu Okuyun](#1-gerçekçi-beklentiler--önce-bunu-okuyun)
2. [Donanım: X.on Hakkında Bilinmesi Gerekenler](#2-donanım-xon-hakkında-bilinmesi-gerekenler)
3. [Kontrol Paradigması: "Düşünce" Nasıl Yöne Dönüşecek?](#3-kontrol-paradigması-düşünce-nasıl-yöne-dönüşecek)
4. [Sistem Mimarisi](#4-sistem-mimarisi)
5. [Teknoloji Yığını](#5-teknoloji-yığını)
6. [Önerilen Klasör Yapısı](#6-önerilen-klasör-yapısı)
7. [Faz 0 — Ortam ve Donanım Kurulumu](#faz-0--ortam-ve-donanım-kurulumu)
8. [Faz 1 — Sinyal Doğrulama](#faz-1--sinyal-doğrulama)
9. [Faz 2 — Simülasyon Altyapısı (Başlıksız Geliştirme)](#faz-2--simülasyon-altyapısı-başlıksız-geliştirme)
10. [Faz 3 — Kalibrasyon Veri Toplama](#faz-3--kalibrasyon-veri-toplama)
11. [Faz 4 — Çevrimdışı (Offline) Analiz ve Model Seçimi](#faz-4--çevrimdışı-offline-analiz-ve-model-seçimi)
12. [Faz 5 — Çevrimiçi (Online) Kod Çözücü](#faz-5--çevrimiçi-online-kod-çözücü)
13. [Faz 6 — Oyun Tasarımı ve Geliştirme](#faz-6--oyun-tasarımı-ve-geliştirme)
14. [Faz 7 — Geri Bildirimli Eğitim ve Ko-adaptasyon](#faz-7--geri-bildirimli-eğitim-ve-ko-adaptasyon)
15. [Faz 8 — Hibrit Yedek Kontroller](#faz-8--hibrit-yedek-kontroller)
16. [Ölçütler ve Başarı Kriterleri](#16-ölçütler-ve-başarı-kriterleri)
17. [Test Planı](#17-test-planı)
18. [Riskler ve Önlemler](#18-riskler-ve-önlemler)
19. [Zaman Çizelgesi](#19-zaman-çizelgesi)
20. [Oturum Protokolü (Her Kayıtta Uygulanacak)](#20-oturum-protokolü-her-kayıtta-uygulanacak)
21. [Güvenlik, Etik ve Veri](#21-güvenlik-etik-ve-veri)
22. [Sözlük](#22-sözlük)
23. [Açık Sorular / Doğrulanacaklar](#23-açık-sorular--doğrulanacaklar)

---

## 1. Gerçekçi Beklentiler — Önce Bunu Okuyun

Projenin başarısı, doğru beklentiyle başlamaya bağlı. Kritik gerçekler:

| Beklenti | Gerçek |
|---|---|
| "Nesnenin yukarı gittiğini hayal edersem yukarı gider." | **Hayır.** Kafa derisi EEG'si, "nesne yukarı gidiyor" gibi soyut görsel düşünceleri güvenilir şekilde ayırt edemez. Bu, 64 kanallı laboratuvar sistemlerinde bile çözülmüş bir problem değildir. |
| Peki ne çalışır? | **Motor imgeleme (Motor Imagery, MI):** Elini/ayağını hareket ettirdiğini *hayal etmek*, motor korteks üzerindeki μ (8–13 Hz) ve β (13–30 Hz) ritimlerinde ölçülebilir bir güç düşüşü (ERD) yaratır. X.on'un **C3, Cz, C4** elektrotları tam bu bölgenin üzerindedir. |
| Yön nasıl elde edilir? | Her yöne bir **zihinsel görev** eşlenir (ör. sol el hayali → sola). Kullanıcı "nesneyi" değil, **eşlenmiş görevi** düşünür. Pratikte kısa sürede bu eşleme sezgiselleşir. |
| İlk gün oynayabilir miyim? | Büyük olasılıkla **2 yön (sağ/sol)** ile, düşük-orta doğrulukla. 4 yön, **birkaç gün–birkaç hafta** düzenli eğitim gerektirir. |
| Herkes yapabilir mi? | Literatürde kullanıcıların kayda değer bir kısmının ("BCI illiteracy / inefficiency") MI ile yeterli kontrol sağlayamadığı bildirilir. Bu yüzden plan **hibrit yedek kontroller** (Faz 8) içerir. |
| Kuru/sünger elektrot fark eder mi? | Evet. Jel elektrotlu sistemlere göre gürültü daha fazladır; artefakt yönetimi (göz kırpma, çene sıkma, kafa hareketi) kritik olacaktır. |

**Hedef seviyeler:**

- **Seviye 1 (MVP):** 2 sınıf (sol/sağ el hayali) → yatay hareket. Hedef doğruluk ≥ %70.
- **Seviye 2:** 3 sınıf (+ ayak hayali → aşağı) veya sürekli 1B kontrol + "dinlenme" durumu.
- **Seviye 3 (Nihai):** Tam 2B kontrol — sağ/sol/yukarı/aşağı.

---

## 2. Donanım: X.on Hakkında Bilinmesi Gerekenler

Brain Products tarafından yayımlanan bilgilere göre (bkz. [ürün sayfası](https://www.brainproducts.com/new-xon-eeg-headset/), [mağaza teknik sayfası](https://shop.brainproducts.com/product/xon-set/)):

| Özellik | Değer | Projeye etkisi |
|---|---|---|
| EEG kanalları | 7: **F3, F4, C3, Cz, C4, P3, P4** | C3/Cz/C4 motor imgeleme için ideal. Oksipital (O1/O2) yok → SSVEP zayıf olur. |
| Referans/Toprak | Kulak klipsi (GND/REF) | Yeniden referanslama seçenekleri sınırlı; CAR (ortak ortalama referans) 7 kanalla dikkatli kullanılmalı. |
| AUX | 1 kanal (EOG/EMG/EKG için) | Göz hareketi artefaktı için EOG ya da hibrit kontrol için EMG bağlanabilir. |
| Hareket sensörü | Dahili ivmeölçer | Kafa hareketi artefaktını tespit etme + yedek kontrol (kafa eğme). |
| Örnekleme hızı | 125 / 250 / 500 Hz | MI için **250 Hz yeterli** ve daha kararlı (pilot kayıt 250 Hz, kesintisiz). |
| Çözünürlük | 16 veya 24 bit | 24 bit tercih edilir; bağlantı kopuyorsa 16 bit + "extended range". |
| Bağlantı | Bluetooth LE 5 → **X.on PC uygulaması** | Zincir: **Başlık → (Bluetooth) → PC uygulaması → (yerel LSL) → oyun/kod çözücü**. Telefon ve Wi-Fi gerekmez. |
| LSL | PC uygulaması LSL akışını doğrudan yayınlar | Aynı bilgisayarda `pylsl` ile alınır. |
| Kafa çevresi | 54–60 cm | Kafanız bu aralıkta değilse elektrot teması sorunlu olabilir. |

### 2.1 Bağlantı ve ağ notu

Akış PC uygulamasından aynı bilgisayara yayınlandığı için ağ (multicast, eduroam vb.) sorunu **yoktur**; her şey `localhost` üzerinden çalışır. Dikkat edilecekler:

- **Bluetooth menzili ve parazit:** PC'nin Bluetooth anteni başlığa yakın olsun (≤ 2 m, arada engel yok). Dahili Bluetooth zayıfsa harici bir **BT 5.x USB adaptör + USB uzatma kablosu** ile anteni başa yaklaştırmak en etkili çözümdür.
- 2,4 GHz Wi-Fi, kablosuz mouse/klavye dongle'ları ve USB 3.0 portları Bluetooth'u bozabilir; adaptörü USB 2.0 portuna veya uzatma kablosuyla uzağa takın.
- Windows güç yönetiminde Bluetooth adaptörü için "güç tasarrufu için kapatılmasına izin ver" seçeneğini kapatın; güç modu "En iyi performans" olsun. Şarj adaptörü takılıyken ve pildeyken 50 Hz gürültüyü sinyal kalitesi panelinde karşılaştırın; daha temiz olanı standart yapın.
- Windows Güvenlik Duvarı LSL'i (Python) engellerse yerel ağ izinlerini verin.

### 2.2 Mevcut kayıttan doğrulanan akış bilgileri

`sub-P003_ses-S001_task-Default_run-001_eeg.xdf` (5 Ekim 2026, ~71 sn) incelendi. X.on akışı:

| Alan | Değer | Plana etkisi |
|---|---|---|
| Akış adı | `X.on-103512-0269` (başlığın seri numarasını içerir) | Kod, akışı **tam adla değil**, `type=EEG` + adın `X.on` ile başlamasıyla bulmalı (başlık değişirse ad değişir). Seri no. `device_xon.yaml`'a yazılır. |
| `source_id` | `103512-0269 250` | Örnekleme hızı source_id'ye gömülü; hız değişirse source_id de değişir. |
| Tür / biçim | `EEG`, `float32` | — |
| Örnekleme hızı | Nominal 250 Hz; ölçülen **249,996 Hz**; **hiç kesinti yok** (en büyük örnek aralığı 4,1 ms) | Faz 0 bağlantı kriteri bu kayıtta zaten karşılanmış. |
| Kanallar (11) | `F3, F4, C3, Cz, C4, P3, P4` (µV) + `BIP` (µV) + `accX, accY, accZ` (mg) | Kanal indeksleri: EEG 0–6, BIP 7, ivmeölçer 8–10. İvmeölçer **aynı akışta** gelir → ayrı senkronizasyon gerekmez. |
| `BIP` kanalı | Bu kayıtta tamamen **0** (bağlı değil) | AUX/bipolar giriş boş. İleride **EOG** (göz) elektrotları bağlanırsa göz artefaktı temizliği çok kolaylaşır. |
| Cihaz filtreleri | Yüksek geçiren **0,5 Hz**, alçak geçiren **65 Hz** (meta veride) | Veri zaten bantlı geliyor; 30 Hz üstü EMG kontrolü hâlâ yapılabilir. 50 Hz çentik filtresi **bizim tarafta** uygulanmalı. |
| İmpedans | Meta veride (`kilo-Ohm` birimiyle) kayıtlı; oturumun başındaki değerler | Her oturumda otomatik okunup `session_log`'a yazılmalı (bkz. Bölüm 2.3). |
| İvmeölçer | Ortalama ≈ (−105, 806, −494) mg → |g| ≈ 950 mg | Kafa eğimi net ölçülüyor → hibrit "kafa eğme" kontrolü (Faz 8) ve hareket artefaktı tespiti mümkün. |

### 2.3 Mevcut kaydın sinyal kalitesi bulguları

| Kanal | SS (µV) | İmpedans değeri (meta) | 50 Hz gürültü (10 Hz'e göre) | Yorum |
|---|---|---|---|---|
| F3 | 42,9 | 62 800 | **+9,7 dB** | Yavaş dalgalar baskın → göz kırpma/hareketi (beklenen) |
| F4 | 49,2 | 53 300 | **+8,5 dB** | Aynı |
| **C3** | 21,1 | **66 900** | **+10,8 dB** | ⚠️ MI için en önemli kanal; impedans yüksek, şebeke gürültüsü yüksek |
| **Cz** | 21,5 | **16 300 (en iyi)** | **−10,5 dB** (temiz) | ✅ Düşük impedans = temiz sinyal. Diğer kanallar böyle olmalı. |
| **C4** | 19,6 | **67 600** | **+13,7 dB** | ⚠️ MI için kritik; en gürültülülerden |
| P3 | 14,3 | 32 600 | +6,1 dB | Orta |
| P4 | 14,5 | **83 200 (en kötü)** | **+13,3 dB** | ⚠️ |
| Ref / Gnd | — | 25 000 / 10 500 | — | — |

**Çıkarımlar:**
1. **İmpedans ile şebeke gürültüsü açıkça ilişkili:** Cz en düşük impedansa ve en temiz sinyale sahip; impedansı yüksek C3, C4 ve P4'te 50 Hz gürültü, 10 Hz beyin ritminden daha güçlü. **Motor imgeleme için en kritik iki kanal (C3, C4) bu kayıtta en kötü durumdakiler arasında.**
2. Bu yüzden Faz 1'e **"kanal impedans kapısı"** eklendi: C3, Cz ve C4'ün impedansı, bu kayıttaki Cz düzeyine (≈ ≤ 20 000) yaklaşmadan MI kalibrasyonuna geçilmez.
3. Meta verideki impedans değerlerinin birimi ("kilo-Ohm" etiketiyle 16 300–83 200) üretici dokümanından **doğrulanmalı**. Mutlak değerden bağımsız olarak **kanallar arası göreli karşılaştırma** için kullanılabilir.
4. Bu kayıt bir renk/tepki görevi sırasında, gözler açıkken alınmış; belirgin 10 Hz alfa tepesi yok. Bu beklenen bir durum, bir sorun göstergesi değil. Asıl alfa testi Faz 1'de yapılacak.

### 2.4 Mevcut laboratuvar ekosistemi (aynı kayıttan)

Kayıtta X.on'a ek olarak şu akışlar da var. Bunlar projede **yeniden kullanılabilir**:

| Akış | İçerik | Bu projede kullanımı |
|---|---|---|
| `MarkerStream` (`LSLMarkerSender1`) | Görev olayları (`task_start`, `stimulus_start`, `response` …) | Marker isimlendirme düzeni örnek alınabilir. ⚠️ Türkçe karakterli markerlar (`Kırmızı`, `Sarı`, `Yeşil`) **bozuk kodlanmış** (UTF-8 değil). **Kural: Bu projede marker adları yalnızca ASCII olacak** (`cue_left`, `cue_right` …). |
| `FaceBlendshapes` (52 kanal, 30 Hz, MediaPipe) | `eyeBlinkLeft/Right`, `jawOpen`, `eyeLookUp/Down…` vb. | 🔹 **Artefakt etiketleme:** Kamera, göz kırpma ve çene hareketlerini EEG'den bağımsız tespit eder → EEG artefakt reddini doğrulamak/eğitmek için çok değerli. 🔹 Hibrit kontrol seçeneği (Faz 8). 🔹 Göz bakış yönü: Modelin "göz yönünü" öğrenip öğrenmediğini test etmek için (Bölüm 17.3). |
| `FaceLandmarks` (1434 kanal = 478 nokta × 3, 30 Hz) | Yüz noktaları | Baş pozu/hareket kontrolü (ivmeölçere ek). |
| `FaceEmotions` (7 kanal, 30 Hz) | Duygu olasılıkları | Yorgunluk/hayal kırıklığı takibi (opsiyonel). |
| `… [time]` akışları | Her akış için `timestamp / time_sync / time_arrival` | Kullanılan LabRecorder sürümü, saat senkronizasyonu bilgisini ayrı akışlar olarak kaydediyor. Analizde XDF okuyucunun **clock-sync** düzeltmesi açık olmalı; `[time]` akışları gecikme ölçümü için kullanılabilir. |

---

## 3. Kontrol Paradigması: "Düşünce" Nasıl Yöne Dönüşecek?

### 3.1 Değerlendirilen seçenekler

| Paradigma | Nasıl çalışır | X.on'a uygunluk | Karar |
|---|---|---|---|
| **Motor İmgeleme (MI)** | El/ayak hareketi hayali → μ/β ERD | **Yüksek** (C3, Cz, C4 mevcut) | ✅ **Ana yöntem** |
| SSVEP | Farklı frekanslarda yanıp sönen hedeflere bakmak | Düşük (oksipital elektrot yok; P3/P4 ile zayıf sinyal) | ❌ Ana yöntem değil, deneysel olabilir |
| P300 | Nadir uyaranlara verilen yanıt | Orta (Pz yok ama P3/P4/Cz var) | ❌ Seçim için iyi, sürekli hareket için yavaş |
| Görsel hayal ("nesne yukarı") | — | Çok düşük | ❌ Güvenilir değil |
| Göz kırpma / çene sıkma | Artefakt sinyali | Yüksek (F3/F4 kırpmaları yakalar) | ⚙️ Yedek / hibrit (Faz 8) |
| İvmeölçer (kafa eğme) | Kafa hareketi | Yüksek | ⚙️ Yedek / hibrit (Faz 8) |

### 3.2 Seçilen eşleme — İki strateji

#### Strateji A: Ayrık sınıflandırma (4 sınıf + dinlenme)

| Yön | Zihinsel görev | Beklenen nörofizyolojik iz |
|---|---|---|
| ⬅️ Sol | **Sol el** sıkma / parmak oynatma hayali | **C4** üzerinde μ/β güç düşüşü (kontralateral ERD) |
| ➡️ Sağ | **Sağ el** sıkma / parmak oynatma hayali | **C3** üzerinde μ/β güç düşüşü |
| ⬇️ Aşağı | **İki ayak** hareketi hayali (ayak parmaklarını kıvırma) | **Cz** üzerinde ERD (ayak temsili orta hatta, derinde — daha zayıf) |
| ⬆️ Yukarı | **İki el birden** hayali *veya* **zihinsel aritmetik** (ör. 100'den 7'şer geri sayma) | İki el: C3+C4 birlikte ERD; aritmetik: frontal/parietal değişimler (F3/F4/P3/P4) |
| ⏸️ Dur | Rahat, nötr dinlenme | Motor alanda μ ritmi korunur |

> **Not:** "Yukarı" en zor sınıftır. Faz 4'te iki aday (iki el vs. aritmetik) çevrimdışı karşılaştırılır; hangisi diğer sınıflardan daha iyi ayrışıyorsa o seçilir.

#### Strateji B: Sürekli 2B kontrol (Wolpaw & McFarland tarzı)

Wolpaw ve McFarland'ın (2004, PNAS) duyu-motor ritimlerle 2B imleç kontrolü yaklaşımından esinlenen yöntem:

- **Yatay hız** = (C4 μ/β gücü − C3 μ/β gücü) → sağ/sol el hayaline göre işaret değiştirir.
- **Dikey hız** = (C3 + C4 μ/β gücünün toplamı, temele göre) → "iki el birden hayal et" = güç düşer = **yukarı**; "tamamen gevşe" = güç artar = **aşağı**.
- Her eksen, kişiye özel doğrusal ağırlıklarla normalize edilir ve sürekli hız üretir.

| Karşılaştırma | Strateji A (Ayrık) | Strateji B (Sürekli) |
|---|---|---|
| Kurulum kolaylığı | Kalibrasyon + sınıflandırıcı | Kalibrasyon + doğrusal regresyon |
| Hissiyat | "Komut verme" | "Joystick gibi" akıcı |
| Eğitim süresi | Orta | Uzun (kullanıcı öğrenmesi gerekir) |
| Oyuna uygunluk | Labirent, grid oyunları | Hedef toplama, top yönlendirme |

**Karar:** Önce **Strateji A** (daha hızlı sonuç verir, hata ayıklaması kolay). Seviye 3'e ulaşıldıktan sonra **Strateji B** ayrı bir kontrol modu olarak eklenir. Mimari, ikisini de destekleyecek şekilde tasarlanır (bkz. Bölüm 4 — "Kontrol Arayüzü").

---

## 4. Sistem Mimarisi

### 4.1 Veri akışı

```
┌──────────────┐  BLE 5   ┌────────────────────┐  yerel LSL     ┌──────────────────────────────────────────────┐
│  X.on başlık │ ───────► │ X.on PC uygulaması │ ─────────────► │              PC (aynı bilgisayar)            │
│ 7 EEG + ACC  │          │ (LSL yayınlayıcı)  │   EEG akışı    │                                              │
└──────────────┘          └────────────────────┘                │  ┌──────────┐   ┌──────────┐   ┌──────────┐  │
                                                                │  │ Alıcı +  │──►│ Ön işleme│──►│ Kod      │  │
                                                                │  │ Tampon   │   │ (filtre, │   │ çözücü   │  │
                                                                │  └──────────┘   │ artefakt)│   │ (model)  │  │
                                                                │                 └──────────┘   └────┬─────┘  │
                                                                │                                     │        │
                                                                │                       "BCI_Control" │ LSL    │
                                                                │                                     ▼        │
                                                                │  ┌──────────┐   "Game_Markers" ┌──────────┐  │
                                                                │  │LabRecorder│◄──────────────── │  OYUN    │  │
                                                                │  │ (.xdf)   │◄── EEG + Control │ (pygame) │  │
                                                                │  └──────────┘                  └──────────┘  │
                                                                └──────────────────────────────────────────────┘
```

### 4.2 LSL akışları

| Akış adı | Tür | Yayınlayan | Tüketen | İçerik |
|---|---|---|---|---|
| `X.on-<seri no>` (ör. `X.on-103512-0269`) | `EEG`, 250 Hz, float32 | X.on PC uygulaması | Kod çözücü, LabRecorder | 11 kanal: 7 EEG (µV) + BIP + accX/Y/Z (mg) — ivmeölçer aynı akışta |
| `FaceBlendshapes` (opsiyonel, mevcut) | `Face`, 30 Hz | MediaPipe uygulaması | Artefakt etiketleme, hibrit kontrol | Göz kırpma, çene, bakış yönü |
| `BCI_Markers` | `Markers` (string, düzensiz) | Kalibrasyon / oyun | LabRecorder, kod çözücü | `trial_start`, `cue_left`, `imagery_end`, `target_hit` vb. |
| `BCI_Control` | `Control` (float, ~10–20 Hz) | Kod çözücü | Oyun, LabRecorder | `[p_sol, p_sağ, p_yukarı, p_aşağı, p_dinlenme]` veya `[vx, vy]` |

**Neden kontrol sinyali de LSL üzerinden?**
- Oyun ile kod çözücü **ayrı süreçler** olur → biri çökerse diğeri etkilenmez.
- Oyunu klavye/simülatörle test edebilirsiniz (aynı akış formatı).
- Her şey tek `.xdf` dosyasında, ortak zaman damgalarıyla kaydedilir → sonradan analiz yapılabilir.
- İleride oyunu Unity'ye taşımak isterseniz yalnızca oyun tarafı değişir (LSL4Unity).

### 4.3 Kontrol Arayüzü (sözleşme)

Oyun, kontrolün kaynağını bilmez; sadece şu soyut sinyali okur:

- **Ayrık mod:** Her güncellemede sınıf olasılıkları + "güven" değeri. Oyun, bir eşiği aşan sınıfı komut olarak uygular.
- **Sürekli mod:** `(vx, vy)` ∈ [-1, 1]².
- **Kaynaklar (tak-çıkar):** `EEG-MI`, `Klavye`, `Sentetik`, `İvmeölçer`, `Hibrit`.

Bu sözleşme Faz 2'de dondurulur ve sonraki tüm fazlar buna uyar.

---

## 5. Teknoloji Yığını

| Katman | Önerilen | Gerekçe | Alternatif |
|---|---|---|---|
| Dil | **Python 3.11/3.12** | BCI ekosistemi Python'da olgun | — |
| LSL | **pylsl** | Resmî Python bağlayıcısı | — |
| Kayıt | **LabRecorder** | XDF formatında çoklu akış senkron kaydı | — |
| Görselleştirme (kontrol) | **BrainVision LSL Viewer** veya `mne-lsl` viewer | Canlı sinyal kalitesi kontrolü | — |
| Sinyal işleme | **NumPy, SciPy** | Filtreler, Welch PSD | — |
| EEG analiz | **MNE-Python** + `pyxdf` | Epoklama, zaman-frekans, topografi | — |
| Sınıflandırma | **scikit-learn**, **pyRiemann** | CSP+LDA, Riemann (TS+LR, MDM) | — |
| Derin öğrenme (opsiyonel) | **braindecode** (EEGNet) | Az kanal + çok veri olursa | PyTorch doğrudan |
| Oyun | **pygame-ce** | Basit, Python'da, düşük gecikme | Unity + LSL4Unity (daha görsel) |
| Yapılandırma | **YAML** dosyaları | Parametreleri koddan ayırmak | TOML |
| Paket yönetimi | `uv` veya `venv` + `requirements.txt` | Tekrarlanabilir ortam | conda |
| Sürüm kontrolü | **git** (klasör henüz repo değil) | Deney/parametre izlenebilirliği | — |

> Büyük veri dosyalarını (`.xdf`, modeller) git'e koymayın; `.gitignore` ile hariç tutun.

---

## 6. Önerilen Klasör Yapısı

```
LSLGame/
├── PLAN.md                    ← bu belge
├── README.md                  ← kurulum ve çalıştırma kısa rehberi
├── requirements.txt
├── config/
│   ├── device_xon.yaml        ← kanal adları, örnekleme hızı, akış adı
│   ├── calibration.yaml       ← deneme sayıları, süreler, sınıflar
│   ├── decoder.yaml           ← filtre bantları, pencere boyu, eşikler
│   ├── game.yaml              ← hız, hedef boyutu, seviye ayarları
│   └── lsl_api.cfg            ← (gerekirse) KnownPeers ayarı
├── src/
│   ├── acquisition/           ← LSL alıcı, halka tampon, akış keşfi
│   ├── simulation/            ← sentetik EEG yayınlayıcı, klavye kontrol kaynağı
│   ├── signal_quality/        ← kanal kalite metrikleri, canlı panel
│   ├── calibration/           ← Graz tipi kalibrasyon arayüzü
│   ├── processing/            ← filtreler, artefakt tespiti, öznitelikler
│   ├── models/                ← CSP+LDA, Riemann, model kaydet/yükle
│   ├── online/                ← gerçek zamanlı kod çözücü servisi
│   ├── control/               ← kontrol arayüzü (ayrık/sürekli), yumuşatma
│   └── game/                  ← oyun motoru, seviyeler, HUD
├── analysis/
│   └── notebooks/             ← çevrimdışı analiz defterleri
├── data/                      ← (git dışı) ham XDF kayıtları
│   └── sub-01/ses-YYYYMMDD/
├── models/                    ← (git dışı) eğitilmiş modeller
├── logs/                      ← oturum günlükleri, oyun skorları
├── tests/
└── docs/
    ├── session_log.md         ← her oturumun elle tutulan notları
    └── results.md             ← faz sonuçları, grafikler
```

---

## Faz 0 — Ortam ve Donanım Kurulumu

**Süre:** 1–2 gün

### Görevler

> **Durum:** Mevcut XDF kaydı, X.on PC uygulaması → LSL → LabRecorder zincirinin **zaten çalıştığını** gösteriyor (Bölüm 2.2). Bu faz büyük ölçüde doğrulama ve Python ortamı kurulumundan ibarettir.

1. **X.on PC uygulaması**
   - Uygulamayı güncel tutun; örnekleme hızını **250 Hz**'te bırakın (mevcut kayıtta kusursuz çalışıyor).
   - LSL yayınını etkin tutun; akış adının `X.on-<seri no>` olduğunu doğrulayın.
   - Uygulamanın impedans ölçüm ekranının nasıl kullanıldığını öğrenin (Faz 1'deki impedans kapısı için).
2. **Bluetooth** (Bölüm 2.1)
   - Adaptörün konumunu ve güç yönetimi ayarlarını yapın.
3. **Python tarafı**
   - Python sanal ortamı oluşturun; Bölüm 5'teki paketleri kurun. (Sistemde Python 3.14 var; MNE/pyRiemann/pygame-ce için 3.14 desteği yoksa projeye özel **Python 3.12** sanal ortamı kullanın.)
   - LabRecorder zaten kurulu ve çalışıyor; aynı sürümü kullanmaya devam edin.
   - Klasörü git deposu yapın; `.gitignore` ile `data/`, `models/`, `logs/`, `*.xdf` hariç tutun.
   - Mevcut `sub-P003_…xdf` dosyasını `data/pilot/` altına taşıyın (pilot/referans kayıt).
4. **Akış keşfi ve yapılandırma**
   - `config/device_xon.yaml`'a Bölüm 2.2'deki bilgileri yazın: akış eşleme kuralı (`type=EEG`, ad `X.on` ile başlar), kanal sırası, EEG indeksleri 0–6, BIP 7, ivmeölçer 8–10, birimler, cihaz filtreleri.
   - Python'dan akışı açıp meta verideki **impedans** ve **filtre** bloklarını okuyabildiğinizi doğrulayın.

### Çıkış kriterleri
- [x] PC, X.on EEG akışını görüyor ve LabRecorder ile kaydedebiliyor *(mevcut XDF ile doğrulandı)*.
- [x] 71 sn'lik kayıtta **veri kesintisi yok**; ölçülen hız 249,996 Hz *(doğrulandı)*.
- [ ] Aynı sonuç **10 dakikalık** bir kayıtta da tekrarlanıyor (uzun sürede Bluetooth kararlılığı).
- [ ] Python ortamı kuruldu; `pylsl` ile akış canlı okunuyor.
- [ ] Akış meta verileri `device_xon.yaml`'a yazıldı.

---

## Faz 1 — Sinyal Doğrulama

**Süre:** 1–2 gün. **Amaç:** "Gerçekten beyin sinyali mi alıyorum?" sorusunu kesin olarak yanıtlamak.

### 1.1 Takma prosedürü
- Saçı elektrot bölgelerinden mümkün olduğunca ayırın; sünger elektrotları üretici talimatına göre (tuzlu su/elektrolit) nemlendirin.
- **Cz**'nin tam tepe noktasında olduğundan emin olun: burun kökü (nasion) ile ense çıkıntısı (inion) arasının ortası, iki kulak arasının ortası.
- Kulak klipsi referansını sıkıca takın.

### 1.1b İmpedans kapısı (pilot kayıttan çıkan yeni adım)

Pilot kayıtta C3/C4/P4 impedansları Cz'nin 4–5 katıydı ve bu kanallarda 50 Hz gürültü beyin ritminden güçlüydü (Bölüm 2.3). Bu nedenle:

1. X.on PC uygulamasının impedans ekranını açın.
2. **Öncelik sırası:** C3, C4, Cz (MI kanalları) → Ref, Gnd → P3, P4 → F3, F4.
3. Yüksek kanallarda: süngeri yeniden nemlendirin, elektrodu hafifçe döndürerek saçı aralayın, başlığı yeniden konumlandırın.
4. **Hedef:** C3, Cz ve C4'ün değeri, pilot kayıttaki Cz düzeyine (≈ ≤ 20 000, meta veri birimiyle) ve birbirine yakın olmalı. Diğer kanallar ≤ 40 000.
5. Son değerler LSL meta verisinden otomatik okunup oturum günlüğüne yazılır. Bu sayede **impedans ↔ sınıflandırma doğruluğu** ilişkisi zamanla izlenir.

### 1.2 Doğrulama testleri

| Test | Ne yapılacak | Beklenen sonuç | Hangi kanal |
|---|---|---|---|
| **Göz kapama alfa testi** | 30 sn gözler açık → 30 sn kapalı, 3 tekrar | Gözler kapalıyken **8–12 Hz güçte belirgin artış** (oksipital yok ama P3/P4'te genelde görülür) | P3, P4 |
| **Göz kırpma** | 10 kez sert kırpma | Büyük, yavaş, pozitif sapmalar | F3, F4 |
| **Çene sıkma** | 5 × 2 sn | Yüksek frekanslı (> 20 Hz) geniş bant gürültü | Tüm kanallar |
| **Kafa hareketi** | Başı sağa/sola çevirme | İvmeölçerde net sinyal, EEG'de yavaş kayma | ACC + tümü |
| **Gerçek el hareketi (ME)** | Sağ eli 4 sn sık-bırak, 20 tekrar; sonra sol el | **Kontralateral μ/β ERD:** sağ el → C3'te, sol el → C4'te güç düşüşü | C3, C4 |
| **Şebeke gürültüsü** | Dinlenik 1 dk | 50 Hz tepe (Türkiye şebekesi) — düşük olmalı | Tümü |

> **Gerçek hareket testi kritik:** Eğer *gerçek* el hareketinde bile C3/C4 ERD görülmüyorsa, *hayali* hareket hiç görülmeyecektir. Bu durumda elektrot teması/yerleşimi düzeltilmeden ilerlenmez.

### 1.3 Sinyal kalitesi paneli (yapılacak araç)
Canlı olarak her kanal için gösterilecekler:
- RMS genlik ve kırpılma (clipping) uyarısı
- 50 Hz bant gücü oranı
- 1/f eğimi / düz çizgi (flatline) tespiti
- Kanal başına **yeşil/sarı/kırmızı** gösterge
- İvmeölçer hareket seviyesi

### Çıkış kriterleri
- [ ] İmpedans kapısı geçildi; C3/C4'te 50 Hz gücü, 10 Hz gücünün altında (pilot kayıtta ~11–14 dB üstündeydi).
- [ ] Alfa testi en az bir parietal kanalda gözle görülür artış gösteriyor.
- [ ] Gerçek el hareketinde C3/C4'te kontralateral ERD (güç düşüşü ≥ %20) gözleniyor.
- [ ] Sinyal kalitesi paneli çalışıyor; tüm kanallar "yeşil" olana kadar takma tekrarlanabiliyor.

---

## Faz 2 — Simülasyon Altyapısı (Başlıksız Geliştirme)

**Süre:** 2–3 gün. **Amaç:** Başlık takmadan tüm sistemi geliştirebilmek ve test edebilmek.

### Görevler
1. **Sentetik EEG yayınlayıcı:** X.on ile aynı kanal sayısı/ad/örnekleme hızıyla LSL akışı yayınlar.
   - Pembe gürültü + 10 Hz μ ritmi tabanı.
   - Klavyeden basılan yön tuşuna göre ilgili kanalda μ/β gücünü düşürür (ör. "sol" → C4 gücü %40 azalır).
   - Ayarlanabilir artefakt enjeksiyonu (göz kırpma, çene sıkma).
2. **Kayıttan oynatıcı (replay):** Gerçek bir `.xdf` kaydını, orijinal zamanlamasıyla LSL'e yeniden yayınlar → kod çözücüyü gerçek veriyle tekrar tekrar test etmek için.
3. **Klavye kontrol kaynağı:** Doğrudan `BCI_Control` akışını üretir → oyunu kod çözücüden bağımsız geliştirmek için.
4. **Kontrol arayüzü sözleşmesini dondur** (Bölüm 4.3).

### Çıkış kriterleri
- [ ] Oyun prototipi klavye kontrol kaynağıyla oynanabiliyor.
- [ ] Sentetik akış → kod çözücü → oyun zinciri uçtan uca çalışıyor.
- [ ] Replay aracı bir XDF kaydını doğru zamanlamayla yayınlayabiliyor.

---

## Faz 3 — Kalibrasyon Veri Toplama

**Süre:** 3–5 oturum (farklı günlerde). **Amaç:** Kişiye özel model eğitmek için etiketli veri toplamak.

### 3.1 Deneme yapısı (Graz-BCI tipi)

```
 t (sn):  0        2      3                       7         8.5–10
          │ Sabitleme│ İpucu│     Motor İmgeleme     │  Dinlenme │
          │    +     │  ←   │  (ok kaybolur, + kalır) │  (boş ekran, rastgele süre)
          ▼          ▼      ▼                        ▼
       trial_start  cue_X  imagery_start          imagery_end
```

| Aşama | Süre | Ekranda | Kullanıcı ne yapar |
|---|---|---|---|
| Sabitleme | 2 sn | Ortada `+` | Gözü sabitle, gevşe, kırpmayı burada yap |
| İpucu | 1 sn | Ok (← → ↑ ↓) veya "dinlen" simgesi | Görevi hazırla |
| İmgeleme | 4 sn | Yalnızca `+` | Görevi **sürekli** hayal et (kinestetik: hissi hayal et, görüntüyü değil) |
| Dinlenme | 1,5–3 sn (rastgele) | Boş | Kırp, yutkun, gevşe |

- Ses ipucu (kısa bip) eklenebilir.
- Her olay `BCI_Markers` akışına yazılır.

### 3.2 Miktar

| Ölçü | Değer |
|---|---|
| Sınıf başına deneme (oturum başına) | 40 |
| Run başına deneme | 20 (sınıflar dengeli, rastgele sırada) |
| Run arası mola | 1–2 dk |
| 2 sınıf oturumu | 4 run ≈ 25 dk |
| 4 sınıf + dinlenme oturumu | 10 run ≈ 55 dk (çok uzunsa 2 güne bölün) |

### 3.3 Aşamalı genişleme
1. **Oturum 1–2:** Yalnızca sol el / sağ el (+ dinlenme).
2. **Oturum 3:** + ayak.
3. **Oturum 4–5:** + yukarı adayları (iki el / aritmetik) — ikisi de toplanır, Faz 4'te seçilir.

### 3.4 İmgeleme yönergesi (kullanıcıya)
- **Kinestetik** hayal edin: Kaslarınızın gerildiğini, bir topu sıktığınızı *hissedin*. Eli dışarıdan "görmek" daha zayıf sinyal verir.
- **Gerçek hareket yapmayın**, kas kasılmasından kaçının (EMG artefaktı yanıltıcı "başarı" yaratır).
- İmgeleme süresince **göz kırpmamaya ve yutkunmamaya** çalışın.
- Ritmik hayal etmek (ör. saniyede bir sıkma) çoğu kişide işe yarar.
- İlk denemelerde, imgelemeden önce aynı hareketi birkaç kez **gerçekten** yapıp hissi hatırlamak faydalıdır.

### 3.5 Kayıt kuralları
- Dosya adlandırma: `data/sub-01/ses-20261015/sub-01_ses-20261015_task-MI_run-01.xdf`
- Her oturumda `docs/session_log.md`'ye yazılacaklar: tarih, saat, uyku süresi, kafein, elektrot kalitesi, gözlemler, yorgunluk (1–10).

### Çıkış kriterleri
- [ ] En az 2 oturum 2-sınıf verisi (≥ 80 deneme/sınıf toplam).
- [ ] Markerlar ile EEG zaman damgaları doğru hizalı (Faz 4 kontrolü).
- [ ] Reddedilen deneme oranı < %20.

---

## Faz 4 — Çevrimdışı (Offline) Analiz ve Model Seçimi

**Süre:** 1–2 hafta (Faz 3 ile paralel ilerler).

### 4.1 Ön işleme hattı

1. XDF yükle → EEG ve marker akışlarını **ortak LSL saatine** hizala.
2. **Kanal seçimi:** 7 kanalın tamamı; ayrıca C3/Cz/C4 alt kümesi denenir.
3. **Filtreleme:**
   - Çentik (notch) 50 Hz (+ 100 Hz harmonik).
   - Bant geçiren **8–30 Hz** (temel MI bandı), 4. derece Butterworth, sıfır faz (offline) / nedensel (online uyum testi için).
4. **Uzamsal filtre seçenekleri (karşılaştırılacak):**
   - Ham (kulak referansı)
   - **Küçük Laplace:** C3' = C3 − ortalama(F3, P3, Cz); C4' = C4 − ortalama(F4, P4, Cz)
   - CAR (7 kanalla dikkatli)
   - CSP (veriye dayalı)
5. **Epoklama:** İmgeleme başlangıcından itibaren 0,5–3,5 sn (ilk 0,5 sn reaksiyon süresi atlanır).
6. **Artefakt reddi:**
   - Genlik eşiği (ör. ±100 µV, kanala göre ayarlanır).
   - F3/F4'te göz kırpma tespiti.
   - > 20 Hz yüksek güç (EMG) tespiti.
   - İvmeölçer hareket eşiği.

### 4.2 Nörofizyolojik doğrulama (sınıflandırmadan ÖNCE)
- **ERD/ERS zaman-frekans haritaları** (C3, Cz, C4; sınıf başına).
- **r² / Fisher skoru haritası** (kanal × frekans) → en ayırt edici bant/kanal kombinasyonlarını belirler.
- Beklenen: sol el ↔ C4 ERD, sağ el ↔ C3 ERD. Görülmüyorsa → kullanıcı stratejisi veya elektrot teması gözden geçirilir.
- **EMG kontrolü:** > 30 Hz bantta sınıflar arası fark varsa, "başarı" kas kasılmasından geliyor olabilir → uyarı.

### 4.3 Karşılaştırılacak modeller

| # | Yöntem | Not |
|---|---|---|
| M1 | **Log-bant gücü (C3, Cz, C4; μ ve β) + LDA** | En basit referans çizgisi |
| M2 | **CSP (8–30 Hz) + LDA** | Klasik MI; çok sınıf için OvR |
| M3 | **FBCSP** (çoklu bant: 4–8, 8–12, 12–16, …, 26–30 Hz) + MI tabanlı öznitelik seçimi + LDA | Kişiye özel bant sorununu çözer |
| M4 | **Riemann: Kovaryans → Tanjant Uzayı + Lojistik Regresyon** | Az kanalda çoğu zaman en iyi; çok sınıfa doğal |
| M5 | **Riemann MDM** | Basit, adaptasyona çok uygun |
| M6 | **EEGNet** (opsiyonel) | Ancak > 200 deneme/sınıf toplanırsa |

### 4.4 Değerlendirme protokolü
- **Oturum içi:** 5-katlı **zaman sıralı / blok** çapraz doğrulama (rastgele karıştırma sızıntı yaratır — yapmayın).
- **Oturumlar arası:** Önceki oturumlarla eğit → son oturumla test. *Online performansın gerçek göstergesi budur.*
- **Ölçütler:** Doğruluk, dengelenmiş doğruluk, Cohen's κ, karışıklık matrisi, ITR (bit/dk).
- **Şans seviyesi:** 2 sınıf %50, 4 sınıf %25, 5 sınıf %20 — ama az deneme sayısında istatistiksel şans eşiği daha yüksektir (ör. 2 sınıf ve 80 denemede ≈ %60). Permütasyon testiyle doğrulayın.
- **Zaman çözünürlüklü doğruluk:** Kayan pencereyle deneme içinde doğruluğun zamanla değişimi → online pencere boyunu seçmek için.

### 4.5 Sınıf seçimi kararı (4 yön için)
- Tüm aday sınıflar için ikili ayrışabilirlik matrisi (her sınıf çifti için doğruluk) çıkarılır.
- **"Yukarı"** için iki el vs. aritmetik → diğer sınıflardan en iyi ayrışan seçilir.
- Hiçbir 4-sınıf kombinasyonu ≥ %55 değilse → **Seviye 2'de kal** veya yukarı/aşağıyı **hibrit kontrolle** sağla (Faz 8).

### Çıkış kriterleri
- [ ] ERD haritaları beklenen lateralizasyonu gösteriyor.
- [ ] 2 sınıf, oturumlar arası doğruluk **≥ %70**.
- [ ] Seçilen model + parametreler `config/decoder.yaml`'da sabitlendi; model dosyası `models/`'ta.
- [ ] Analiz sonuçları `docs/results.md`'ye yazıldı.

---

## Faz 5 — Çevrimiçi (Online) Kod Çözücü

**Süre:** 1 hafta.

### 5.1 İşlem döngüsü

1. LSL'den **halka tampona** sürekli veri çek (son ~5 sn).
2. Her **100 ms**'de (≈ 10 Hz güncelleme):
   - Son **1,5–2 sn**'lik pencereyi al (Faz 4.4 zaman çözünürlüklü analizden seçilir).
   - **Nedensel** filtre uygula (filtre durumunu bloklar arası koru; offline'daki sıfır-faz filtre online'da kullanılamaz — eğitim de nedensel filtreyle yapılmalı ki dağılım uyuşsun).
   - Artefakt kontrolü → artefakt varsa bu güncellemede **"belirsiz"** çıkışı ver (hareket yok).
   - Modelden olasılık vektörü al.
3. **Yumuşatma:** Üstel hareketli ortalama (EMA) veya son N tahminin ortalaması.
4. **Karar mantığı (ayrık mod):**
   - Bir sınıfın yumuşatılmış olasılığı **eşik** (ör. 0,6) üzerinde ve bu durum **kalma süresi** (dwell, ör. 0,5 sn) boyunca devam ediyorsa → komut.
   - Komuttan sonra kısa **bekleme (refractory)** süresi (ör. 0,3 sn).
   - Hiçbiri eşiği aşmıyorsa → **dur** (Asenkron/kendi hızında BCI'nın temeli: "kontrol etmemeyi" de bilmeli).
5. **Sürekli mod:** Olasılık farkları veya lineer çıktılar → `(vx, vy)`; ölü bölge (dead-zone) + kazanç.
6. `BCI_Control` akışına yayınla.

### 5.2 Gecikme bütçesi

| Kaynak | Tahmini |
|---|---|
| Başlık → PC (Bluetooth LE) | 20–60 ms |
| PC uygulaması → kod çözücü (yerel LSL) | < 5 ms |
| Pencere (yapısal gecikme) | ~ pencere/2 ≈ 750–1000 ms |
| İşleme | < 20 ms |
| Yumuşatma + kalma süresi | 300–700 ms |
| **Toplam algılanan tepki** | **~1–2 sn** |

> MI-BCI'larda 1–2 sn tepki normaldir. Oyun tasarımı bunu tolere edecek şekilde yapılmalı (hızlı refleks gerektiren oyun değil).

### 5.3 Adaptasyon (oturumlar arası kaymaya karşı)
- **Oturum başı kısa yeniden kalibrasyon:** 10 deneme/sınıf (≈ 5 dk) → model ofsetlerini güncelle.
- **Denetimsiz adaptasyon:** Riemann **yeniden merkezleme** (re-centering) — oturumun dinlenme verisiyle referans kovaryansı güncellenir; etiket gerektirmez.
- **LDA ortalama/bias adaptasyonu:** Oyun sırasında bilinen hedeflerle (Faz 7) etiketli güncelleme.

### 5.4 Operatör paneli
Kod çözücünün yanında açık duran küçük bir pencere:
- Canlı sınıf olasılık çubukları
- Sinyal kalitesi göstergeleri
- Artefakt uyarıları
- Eşik / kalma süresi / kazanç kaydırıcıları (canlı ayar)
- Model sürümü ve oturum bilgisi

### Çıkış kriterleri
- [ ] Replay verisiyle çevrimiçi kod çözücü doğruluğu, offline oturumlar arası doğruluğun ± %5'i içinde.
- [ ] Uçtan uca gecikme ölçüldü ve belgelendi.
- [ ] Dinlenme sırasında yanlış komut oranı < 2 / dakika.

---

## Faz 6 — Oyun Tasarımı ve Geliştirme

**Süre:** 1–2 hafta (Faz 2'den itibaren paralel başlar).

### 6.1 Tasarım ilkeleri (BCI'ya özgü)
1. **Yavaş ve affedici:** Zaman baskısı düşük, hata cezası hafif.
2. **Sürekli geri bildirim:** Kullanıcı kod çözücünün "ne düşündüğünü" anlık görmeli (ör. nesnenin etrafında yöne göre parlayan halka, olasılık çubukları). Geri bildirim, MI öğrenmesinin en önemli bileşenidir.
3. **Göz hareketi gerektirmeyen düzen:** Hedefler ekranın ortasına yakın; kullanıcının gözlerini sürekli kaydırması artefakt üretir.
4. **Yanıp sönme yok:** Hızlı titreşen grafikler hem dikkati dağıtır hem de istenmeyen görsel uyarılmış potansiyeller üretir.
5. **Dinlenme hakkı:** "Hiçbir şey düşünmemek" = nesne durur. Oyun bunu cezalandırmamalı.
6. **Kısa turlar:** 2–3 dakikalık turlar; zihinsel yorgunluk hızla artar.
7. **Her olay marker'lanır:** Hedef görünme, hedefe ulaşma, komut uygulanması → analiz ve ko-adaptasyon için.

### 6.2 Oyun modları (aşamalı)

| Seviye | Mod | Kontrol | Açıklama |
|---|---|---|---|
| 1 | **Top Yuvarla** | Sol / Sağ | Ekranın ortasındaki top; solda veya sağda bir hedef belirir. Topu hedefe götür. Kalibrasyonla aynı yapı → geri bildirimli eğitim için ideal. |
| 1 | **Kapı Seç** | Sol / Sağ | Yukarıdan düşen nesne, sol ya da sağ kapıdan geçmeli. |
| 2 | **Üç Yol** | Sol / Sağ / Aşağı | Nesne aşağı doğru kaydırılırken engellerden kaçınılır. |
| 3 | **Hedef Avcısı** | 4 yön | Grid üzerinde rastgele beliren yıldızlara ulaş. |
| 3 | **Labirent** | 4 yön (ayrık, hücre hücre) | Basit labirentlerle başlayıp zorlaşan seviyeler. |
| 3+ | **Uzay Gezgini** | Sürekli 2B (Strateji B) | Akıcı hareketle asteroitlerden kaçarak enerji topla. |

### 6.3 Oyun bileşenleri
- **Oyun döngüsü:** Sabit 60 FPS çizim; kontrol girdisi ~10 Hz okunur, hareket enterpolasyonla yumuşatılır.
- **Kontrol kaynağı seçici:** Başlangıç menüsünde `EEG / Klavye / Sentetik / Hibrit`.
- **HUD:** Skor, kalan süre, sınıf olasılık çubukları (açılıp kapatılabilir), sinyal kalitesi ikonu.
- **Duraklat:** Tek tuş (operatör için) — elektrot kayarsa vb.
- **Zorluk ayarı:** Hedef boyutu, hedef uzaklığı, nesne hızı, kalma süresi.
- **Skor kaydı:** Her tur → `logs/` altında CSV/JSON (tarih, mod, isabet, ortalama hedefe varış süresi, yanlış komut sayısı).

### 6.4 Asist (yardım) mekanikleri — başlangıç için önemli
- **Hedef mıknatısı:** Hedefe yaklaşınca hafif çekim.
- **Yanlış yön sönümleme:** Hedeften uzaklaştıran komutlar yarı hızda uygulanır (eğitim modunda).
- Asist seviyesi zamanla azaltılır; kullanıcı ilerlemesi asistsiz skorla ölçülür.

### Çıkış kriterleri
- [ ] Seviye 1 modları klavyeyle ve sentetik akışla oynanabiliyor.
- [ ] Tüm oyun olayları LSL marker olarak kaydediliyor.
- [ ] Operatör duraklatma ve kaynak değiştirme çalışıyor.

---

## Faz 7 — Geri Bildirimli Eğitim ve Ko-adaptasyon

**Süre:** 2–6 hafta, haftada 3–4 oturum. **Amaç:** Hem modelin hem kullanıcının birbirine uyum sağlaması.

### 7.1 Eğitim döngüsü (her oturum)

```
Takma + sinyal kontrolü (10 dk)
   → Kısa kalibrasyon / yeniden merkezleme (5 dk)
   → Geri bildirimli "Top Yuvarla" (3 × 3 dk)
   → Modeli yeni etiketli veriyle güncelle (1 dk)
   → Asıl oyun turları (3–5 × 3 dk)
   → Oturum notları
Toplam: ~45–60 dk
```

### 7.2 İlerleme kuralı
- Bir seviyedeki asistsiz başarı oranı **2 ardışık oturumda ≥ %75** ise → bir sonraki seviyeye geç (yeni sınıf ekle).
- 3 oturum boyunca ilerleme yoksa → Faz 4'e dön: farklı imgeleme stratejisi (ör. sıkma yerine parmak tıklatma), farklı bant, farklı model.

### 7.3 Ko-adaptasyon yöntemleri
- Oyunda hedef bilindiği için her deneme **etiketli veri** üretir → model düzenli güncellenir (yalnızca yüksek kaliteli, artefaktsız denemeler).
- Yanlış etiket riskine karşı: Yalnızca hedefin belirdiği ilk X saniyedeki veri kullanılır (kullanıcının niyeti en net olduğu an).
- Kayan pencere: Son N oturumun verisi ağırlıklı (yeni veri daha ağırlıklı).

### 7.4 Kullanıcı stratejisi günlüğü
Hangi hayal tarzının daha iyi çalıştığını not edin (ör. "sağ el: topu sıkmak > yazı yazmak"). Bu, kişisel kontrol stratejinizin geliştiği yerdir.

### Çıkış kriterleri
- [ ] Seviye 1 asistsiz başarı ≥ %75.
- [ ] Öğrenme eğrisi grafiği (oturum × doğruluk) `docs/results.md`'de.

---

## Faz 8 — Hibrit Yedek Kontroller

**Amaç:** MI tek başına 4 yön için yetersiz kalırsa bile oyunun oynanabilir olması.

| Hibrit seçenek | Nasıl | Kullanım önerisi |
|---|---|---|
| **MI (yatay) + İvmeölçer (dikey)** | Sağ/sol el hayali → yatay; başı hafifçe öne/arkaya eğme → dikey | En güvenilir hibrit. Ama "saf düşünce" değil. |
| **MI + Çift göz kırpma** | Çift kırpma = mod değiştir (yatay ↔ dikey eksen) | 2 sınıf MI ile 4 yöne ulaşmak için: aynı sol/sağ hayali, aktif eksene göre sol/sağ veya yukarı/aşağı olur. ⭐ Yalnızca 2 iyi sınıfla 4 yön sağlar. |
| **MI + Çene sıkma** | Çene sıkma = "onayla/seç" | Labirentte kavşak seçimi gibi. |
| **MI + AUX-EMG** | AUX'a kol/yüz EMG elektrodu | Engelli kullanıcılar için değil; geliştirici testi için. |
| **MI + Kamera (FaceBlendshapes)** | Mevcut MediaPipe akışından `eyeBlink`, `jawOpen`, `browInnerUp` gibi yüz hareketleri | Laboratuvarda zaten çalışıyor. Çift kırpma veya kaş kaldırma ile eksen değiştirme/onay; EEG'deki kırpma tespitine göre daha güvenilir. |
| **Hiyerarşik MI** | Önce eksen seç (sağ el = yatay, sol el = dikey), sonra yön seç | Yavaş ama yalnızca 2 sınıfla 4 yön sağlar; saf MI'da kalır. |

> **Öneri:** "Çift kırpma ile eksen değiştirme" veya "hiyerarşik MI", 2-sınıf doğruluğu yüksek ama 4-sınıf düşük kullanıcılar için en iyi uzlaşmadır. Oyun bu modları "Hibrit" kaynağı olarak destekler.

---

## 16. Ölçütler ve Başarı Kriterleri

| Ölçüt | Tanım | Seviye 1 hedefi | Seviye 3 hedefi |
|---|---|---|---|
| Offline doğruluk (oturumlar arası) | Önceki oturumlarla eğit, yenisinde test | ≥ %70 (2 sınıf) | ≥ %55 (4 sınıf) |
| Cohen's κ | Şansa göre düzeltilmiş uyum | ≥ 0,4 | ≥ 0,4 |
| ITR | Bilgi aktarım hızı (bit/dk) | ≥ 3 | ≥ 5 |
| Online hedef isabet oranı | Süre sınırında hedefe ulaşılan tur oranı | ≥ %75 | ≥ %60 |
| Ortalama hedefe varış süresi | sn | ≤ 8 sn | ≤ 15 sn |
| Yanlış komut oranı (dinlenmede) | komut/dk | ≤ 2 | ≤ 2 |
| Uçtan uca gecikme | Niyet → ekran | ≤ 2 sn | ≤ 2 sn |
| Veri kaybı | Kayıp örnek oranı | < %0,5 | < %0,5 |

---

## 17. Test Planı

### 17.1 Birim testleri
- Filtreler: Bilinen frekanslı sinüs → beklenen bastırma/geçirme.
- Nedensel vs. sıfır-faz filtre: Online filtrenin blok blok çalıştırıldığında tek seferde çalıştırılanla aynı sonucu verdiği.
- Öznitelik çıkarımı: Sentetik μ-ERD → beklenen öznitelik değişimi.
- Karar mantığı: Eşik/kalma/bekleme senaryoları (tablo tabanlı testler).
- Kontrol arayüzü: Her kaynak sözleşmeye uygun çıktı üretiyor.

### 17.2 Entegrasyon testleri
- Sentetik EEG → kod çözücü → oyun: Klavyeden "sol" basıldığında nesne ≤ 2 sn içinde sola gidiyor.
- Replay XDF → kod çözücü: Online doğruluk, offline doğrulukla tutarlı.
- Ağ kesintisi: LSL akışı 5 sn kesilip geri geldiğinde sistem çökmeden yeniden bağlanıyor; oyun "sinyal yok" gösteriyor ve nesneyi durduruyor.

### 17.3 Doğrulama (sanity) testleri — **çok önemli**
- **Kapalı-göz / boş başlık testi:** Başlık takılı değilken (veya kafada ama dinlenmede) sistem anlamlı hareket üretmemeli.
- **Kas artefaktı testi:** Kasıtlı çene sıkma / yüz kası kasılması, yön komutu üretmemeli (artefakt reddi çalışıyor mu?).
- **Göz hareketi testi:** Hedefe bakmak tek başına hareketi tetiklememeli (frontal kanallar modele "göz yönü" öğretmiş olabilir — F3/F4 dışarıda bırakılarak karşılaştırma yapılmalı).
- **Etiket karıştırma testi:** Etiketleri rastgele karıştırarak eğitilen model şans seviyesinde kalmalı (veri sızıntısı kontrolü).

### 17.4 Kullanılabilirlik
- Her oturum sonunda: NASA-TLX kısa formu veya 1–10 arası zihinsel yük, kontrol hissi, keyif puanı.

---

## 18. Riskler ve Önlemler

| # | Risk | Olasılık | Etki | Önlem |
|---|---|---|---|---|
| R1 | Yüksek impedans → C3/C4'te şebeke gürültüsü (pilot kayıtta **gözlendi**) | **Yüksek** | Yüksek | Faz 1 impedans kapısı; 50 Hz çentik; PC'yi pilde çalıştırma; kabloları başlıktan uzak tutma |
| R2 | Bluetooth kopmaları / veri kaybı (PC'ye doğrudan BT) | Düşük–Orta | Yüksek | Pilot kayıtta kesinti yok. Uzun oturumlar için: harici BT adaptör + uzatma, güç yönetimi kapalı; kesinti tespiti ve oyunu durdurma |
| R3 | Sünger elektrotların kuruması | Yüksek | Orta | Oturumları ≤ 60 dk tut; ara kontrol; kalite paneli |
| R4 | Kullanıcı MI ile yeterli kontrol sağlayamıyor | Orta | Yüksek | Farklı imgeleme stratejileri, uzun eğitim, hibrit modlar (Faz 8) |
| R5 | "Başarı" aslında EMG/göz artefaktı | Orta | Yüksek | Sanity testleri (17.3); > 30 Hz kontrolü; F3/F4'süz model karşılaştırması |
| R6 | Oturumlar arası performans düşüşü | Yüksek | Orta | Oturum başı kısa kalibrasyon; Riemann yeniden merkezleme |
| R7 | 4. sınıf ("yukarı") ayrışmıyor | Yüksek | Orta | Hiyerarşik MI veya eksen değiştirme hibriti |
| R8 | Saat senkronizasyonu / marker kayması | Düşük | Yüksek | Tüm akışlar LSL saatinde; XDF'de clock offset düzeltmesi; Faz 3'te hizalama doğrulaması |
| R9 | Yorgunluk / motivasyon düşüşü | Orta | Orta | Kısa turlar, oyunlaştırma, ilerleme grafikleri |
| R10 | Başlık değişince akış adı değişiyor (seri no. içeriyor) | Orta | Düşük | Akışı `type=EEG` + `X.on` öneki ile bul |
| R12 | Türkçe karakterli markerların bozulması (pilot kayıtta **gözlendi**) | Yüksek | Orta | Marker adlarında yalnızca ASCII |
| R13 | Python 3.14 ile kütüphane uyumsuzluğu | Orta | Orta | Projeye özel Python 3.12 sanal ortamı |
| R11 | Kafa çevresi 54–60 cm dışında | Düşük | Yüksek | Takmadan önce ölçün; temas sorunu varsa üreticiye danışın |

---

## 19. Zaman Çizelgesi

> Haftada ~8–10 saat ayrılacağı varsayılmıştır.

| Hafta | Fazlar | Teslimat |
|---|---|---|
| 1 | Faz 0, Faz 1 | Akış PC'de; sinyal doğrulandı; kalite paneli |
| 2 | Faz 2, Faz 6 (başlangıç) | Simülatör + klavyeyle oynanan Seviye 1 oyunu |
| 3 | Faz 3 (oturum 1–2), Faz 4 (başlangıç) | İlk 2-sınıf veri; ERD haritaları; ilk modeller |
| 4 | Faz 4, Faz 5 | Seçilen model; online kod çözücü; **ilk "düşünceyle" oynanan tur** 🎯 |
| 5–6 | Faz 7 (Seviye 1), Faz 3 (oturum 3–5) | Seviye 1 akıcı; ayak/yukarı sınıf verileri |
| 7–8 | Faz 4 (4-sınıf), Faz 6 (Seviye 2–3) | 3–4 sınıflı model; Labirent / Hedef Avcısı |
| 9–10 | Faz 7 (Seviye 2–3), Faz 8 | 4 yön kontrol (saf MI veya hibrit) |
| 11+ | Strateji B, cilalama | Sürekli 2B kontrol modu; "Uzay Gezgini" |

---

## 20. Oturum Protokolü (Her Kayıtta Uygulanacak)

### Öncesi (kontrol listesi)
- [ ] Güç: dizüstünü mümkünse **pilde** çalıştırın (şarj adaptörü 50 Hz gürültüyü artırabilir), Windows güç modu "En iyi performans", X.on PC uygulaması güncel
- [ ] Başlık şarjlı
- [ ] Bluetooth adaptörü başlığa yakın (≤ 2 m), X.on PC uygulaması başlığa bağlı ve LSL yayını açık
- [ ] İmpedans kapısı geçildi (Faz 1.1b); değerler not edildi
- [ ] Ortam: sessiz, loş olmayan sabit ışık, rahat sandalye, kollar dinlenik
- [ ] Yakında elektrik gürültüsü kaynağı yok (şarj adaptörleri, monitör kabloları — mümkünse PC'yi pilde çalıştırın)
- [ ] Son 2 saatte yoğun kafein yok (not edilecek)
- [ ] Sünger elektrotlar nemlendirildi, Cz konumu ölçüldü
- [ ] Kalite paneli: tüm kanallar yeşil
- [ ] LabRecorder: tüm akışlar seçili, dosya adı doğru
- [ ] Kayıt başlatıldı → 1 dk göz açık + 1 dk göz kapalı **temel (baseline)** kaydı

### Sırası
- Run aralarında mola; sünger nemini kontrol et.
- Elektrot kayması, öksürük vb. olaylar not edilir.

### Sonrası
- [ ] Kayıt durduruldu, dosya boyutu makul
- [ ] `session_log.md` dolduruldu
- [ ] Süngerler temizlendi ve kurutuldu (üretici talimatına göre)
- [ ] Veri yedeklendi

---

## 21. Güvenlik, Etik ve Veri

- X.on bir araştırma cihazıdır; bu proje **tıbbi teşhis veya tedavi amacı taşımaz**.
- Baş ağrısı, ciltte tahriş, aşırı yorgunluk olursa oturum sonlandırılır.
- Işığa duyarlı epilepsi öyküsü varsa yanıp sönen uyaran (SSVEP vb.) kesinlikle kullanılmaz; oyun yanıp sönme içermeyecek şekilde tasarlanmıştır.
- EEG verisi kişisel sağlık verisi niteliği taşıyabilir: Kendiniz dışında katılımcı olursa (ör. bir arkadaş, öğrenciler) **KVKK** kapsamında aydınlatılmış onam alın; üniversite bünyesinde yayın amaçlı çalışma yapılacaksa **etik kurul onayı** gerekir.
- Veriler anonim katılımcı kodlarıyla (`sub-01`) saklanır; isim içeren dosya adı kullanılmaz.
- Veri biçimi olarak ileride paylaşım düşünülüyorsa **BIDS-EEG** yapısına dönüştürme planlanabilir.

---

## 22. Sözlük

| Terim | Açıklama |
|---|---|
| **LSL** (Lab Streaming Layer) | Ağ üzerinden zaman senkronize veri akışı sistemi |
| **XDF** | LSL akışlarının birlikte kaydedildiği dosya formatı |
| **MI** (Motor Imagery) | Motor imgeleme; hareketi yapmadan hayal etmek |
| **ERD / ERS** | Olaya ilişkin senkronizasyon kaybı / artışı; ritim gücünde düşüş / artış |
| **μ ritmi** | Motor korteks üzerinde 8–13 Hz ritim |
| **β ritmi** | 13–30 Hz ritim |
| **CSP** | Ortak Uzaysal Örüntüler; sınıflar arası varyans farkını en üst düzeye çıkaran uzamsal filtre |
| **FBCSP** | Filtre bankası CSP; çoklu frekans bantlarında CSP |
| **LDA** | Doğrusal Diskriminant Analizi |
| **Riemann yöntemleri** | Kovaryans matrislerini geometrik uzayda sınıflandırma |
| **ITR** | Bilgi Aktarım Hızı (bit/dk) |
| **Asenkron BCI** | Kullanıcının istediği zaman komut verdiği, "kontrol etmeme" durumunu tanıyan BCI |
| **Ko-adaptasyon** | Kullanıcı ve modelin karşılıklı uyum sağlaması |
| **Artefakt** | Beyin dışı kaynaklı sinyal (göz, kas, hareket, şebeke) |

---

## 23. Açık Sorular / Doğrulanacaklar

Faz 0'da yanıtlanması gerekenler:

**Yanıtlananlar (pilot XDF kaydından):**
- ~~LSL akış adı ve kanal düzeni~~ → `X.on-103512-0269`, 11 kanal (7 EEG + BIP + 3 ivmeölçer), tek akış, 250 Hz (Bölüm 2.2).
- ~~Bağlantı zinciri~~ → X.on PC uygulaması, Bluetooth ile doğrudan bağlanıp yerel LSL yayınlıyor; telefon/ağ gerekmiyor.

**Hâlâ açık:**
1. Meta verideki impedans değerlerinin gerçek birimi nedir ("kilo-Ohm" etiketiyle 16 300–83 200)? Üreticinin önerdiği eşik nedir? ([X.on Destek Merkezi](https://xon-eeg.com))
2. İmpedans meta verisi yalnızca akış başlarken mi yazılıyor, yoksa oturum içinde güncellenebiliyor mu?
3. PC uygulaması 500 Hz / 24 bit modunda da kesintisiz çalışıyor mu? (MI için 250 Hz yeterli; düşük öncelik.)
4. `BIP` girişine EOG elektrodu bağlamak mümkün mü, hangi aksesuar gerekiyor?
5. Kafa çevresi 54–60 cm aralığında mı?
6. Oyun yalnızca kendiniz için mi, yoksa başka katılımcılarla da test edilecek mi? (Pilot dosyadaki `sub-P003` başka katılımcıların da kaydedildiğini düşündürüyor; etik/KVKK süreçlerini belirler.)
7. Oyun motoru tercihi: hızlı ilerleme için **pygame** mi, daha zengin görsellik için **Unity** mi?
8. MediaPipe yüz akışları bu projede de çalıştırılacak mı (artefakt etiketleme / hibrit kontrol için önerilir)?

---

### Kaynaklar

- Brain Products — X.on EEG headset: https://www.brainproducts.com/new-xon-eeg-headset/
- Brain Products Shop — X.on set teknik bilgiler: https://shop.brainproducts.com/product/xon-set/
- Brain Products — X.on basın bülteni: https://pressrelease.brainproducts.com/xon-eeg-headset/
- Wolpaw, J. R., & McFarland, D. J. (2004). Control of a two-dimensional movement signal by a noninvasive brain-computer interface in humans. *PNAS*, 101(51), 17849–17854.
- Lab Streaming Layer dokümantasyonu: https://labstreaminglayer.readthedocs.io
