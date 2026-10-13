# BCI_Control Arayüz Sözleşmesi (Control Interface Contract)

> **Belge Sürümü:** 1.0  
> **İlgili Faz:** Faz 2 (Simülasyon Altyapısı)  
> **Kaynak:** PLAN.md Bölüm 4.2 ve Bölüm 4.3

---

## 1. Amaç ve Tasarım Felsefesi

BCI (Beyin-Bilgisayar Arayüzü) oyunlarında kod çözücü (decoder / signal processing) ile oyun motoru (game engine / UI) kesin bir sınırla birbirinden ayrılmalıdır.

**Temel ilkeler:**
1. **Kaynak Bağımsızlığı:** Oyun motoru, girdinin nereden geldiğini **asla bilmez** (X.on EEG-MI modeli, klavye kaynağı, sentetik simülatör, ivmeölçer veya hibrit kontrol).
2. **Süreç İzolasyonu:** Kod çözücü veya oyun motorundan biri çökerse ya da donarsa diğeri etkilenmez; ikisi bağımsız işletim sistemi süreçleridir.
3. **Senkron Kayıt ve Analiz:** Kontrol sinyali LSL üzerinden aktığı için LabRecorder ile EEG ve oyun markerlarıyla milisaniyelik hassasiyetle ortak bir `.xdf` dosyasına kaydedilir.

---

## 2. LSL Akış Tanımı

| Alan | Değer | Açıklama |
|---|---|---|
| **Akış Adı (`name`)** | `BCI_Control` | Sabit akış adı. |
| **Akış Türü (`type`)** | `Control` | Standart LSL türü. |
| **Veri Biçimi (`format`)** | `cf_float32` | 32-bit kayan noktalı sayı dizisi. |
| **Nominal Hız (`srate`)** | `20.0 Hz` | Önerilen güncelleme hızı (10–20 Hz aralığı). |
| **Kanal Sayısı** | 5 (Ayrık) veya 2 (Sürekli) | Çalışma moduna bağlıdır. |

---

## 3. Çalışma Modları

### 3.1 Ayrık Mod (Discrete Mode — 5 Kanal)

Sınıflandırıcı tabanlı MI modelleri (CSP+LDA, Riemann) ve klavye ayrık kontrolü için standart mod.

| Kanal İndeksi | Kanal Etiketi | Anlamı | Değer Aralığı |
|---|---|---|---|
| 0 | `p_left` | Sol yön komut olasılığı | $[0.0, 1.0]$ |
| 1 | `p_right` | Sağ yön komut olasılığı | $[0.0, 1.0]$ |
| 2 | `p_up` | Yukarı yön komut olasılığı | $[0.0, 1.0]$ |
| 3 | `p_down` | Aşağı yön komut olasılığı | $[0.0, 1.0]$ |
| 4 | `p_rest` | Dinlenme / nötr / boşta kalma olasılığı | $[0.0, 1.0]$ |

**Yorumlama Kuralları:**
- Olasılıkların toplamı teorik olarak $1.0$ olmalıdır ($\sum_{i=0}^4 p_i \approx 1.0$).
- **Karar Eşiği ($th$):** Tipik değer $0.50$ – $0.60$.
- Bir yönün ($p_k$, $k \in \{\text{left}, \text{right}, \text{up}, \text{down}\}$) olasılığı eşiği aşıyorsa aktif komut olarak kabul edilir.
- Hiçbir yön eşiği aşmıyorsa veya $p_{\text{rest}}$ en yüksekse oyun nesnesi **hareketsiz kalır (nötr)**.
- Bu özellik, asenkron BCI tasarımının temelidir: Kullanıcı bir şey düşünmediğinde nesne durmalıdır.

---

### 3.2 Sürekli Mod (Continuous Mode — 2 Kanal)

Wolpaw & McFarland 2B imleç kontrolü veya oransal klavye/joystick kontrolü için standart mod.

| Kanal İndeksi | Kanal Etiketi | Anlamı | Değer Aralığı |
|---|---|---|---|
| 0 | `vx` | Yatay hız bileşeni | $[-1.0, +1.0]$ |
| 1 | `vy` | Dikey hız bileşeni | $[-1.0, +1.0]$ |

**Koordinat Sözleşmesi:**
- `vx < 0`: Sola hareket ($vx = -1.0$ maksimum sol hız).
- `vx > 0`: Sağa hareket ($vx = +1.0$ maksimum sağ hız).
- `vy > 0`: Yukarı hareket ($vy = +1.0$ maksimum yukarı hız).
- `vy < 0`: Aşağı hareket ($vy = -1.0$ maksimum aşağı hız).
- $(vx, vy) = (0.0, 0.0)$: Durma / nötr durum.
- **Ölü Bölge (Dead-zone):** Gürültüden kaynaklanan titremeleri önlemek için $|v| < 0.15$ aralığı sıfır kabul edilir.

---

## 4. Tak-Çıkar Kontrol Kaynakları (Sources)

Aşağıdaki tüm kaynaklar aynı `BCI_Control` akışını yayınlar ve oyun tarafında hiçbir değişiklik gerektirmeden birbirinin yerine geçebilir:

1. **`KeyboardControlSource` (`src/control/keyboard_source.py`):**
   - Ok tuşlarıyla ayrık veya sürekli kontrol yayını.
   - Geliştirme, hata ayıklama ve oyun mekaniği testleri için birincil araç.
2. **`SyntheticEEGSource` + Online Decoder:**
   - Sentetik pembe gürültü + ERD sinyali üzerinden uçtan uca simülasyon.
3. **`OnlineDecoder` (`src/online/` — Faz 5):**
   - Gerçek X.on başlığından gelen canlı EEG'yi sınıflandırıp `BCI_Control` yayını yapan servis.
4. **`AccelerometerHybridSource` (Faz 8):**
   - Baş eğme hareketlerini sürekli veya ayrık hız sinyaline çeviren yedek kontrol.

---

## 5. Örnek Kullanım (Python)

### Yayınlama (Sender):
```python
from src.control.contract import ControlSender

# Ayrık mod yayını (20 Hz)
sender = ControlSender(mode="discrete", srate=20.0)
sender.send_discrete(p_left=0.85, p_right=0.05, p_up=0.0, p_down=0.0, p_rest=0.10)
```

### Okuma (Receiver):
```python
from src.control.contract import ControlReceiver

receiver = ControlReceiver(timeout=5.0)
cmd = receiver.get_command(timeout=0.0, threshold=0.6)

if cmd["direction"] == "left":
    # Topu sola hareket ettir
    move_ball(dx=-1)
elif cmd["direction"] == "rest":
    # Dur
    pass
```
