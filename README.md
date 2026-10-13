# LSLGame — X.on EEG ile Düşünceyle Kontrol Edilen Oyun

Brain Products **X.on** EEG başlığı kullanılarak, motor imgeleme (Motor Imagery, MI) ve duyu-motor ritimler (mu ve beta) ile ekrandaki nesnelerin zihinsel kontrolünü sağlayan BCI oyun altyapısı.

Detaylı proje yol haritası ve nörofizyolojik arka plan için [PLAN.md](file:///E:/GitHub/LSLGame/PLAN.md) belgesini inceleyebilirsiniz.

---

## 1. Kurulum

Bu proje **Python 3.12** ile çalışacak şekilde yapılandırılmıştır.

```powershell
# 1. Sanal ortamı oluşturun
py -3.12 -m venv .venv

# 2. Bağımlılıkları yükleyin
.venv\Scripts\python -m pip install -r requirements.txt
```

---

## 2. Modüller ve Çalıştırma Komutları

### 2.1 Sentetik EEG Yayınlayıcı (Simülatör)
Başlık takılı olmadan geliştirme yapmak için X.on ile birebir aynı meta veriyle (11 kanal, 250 Hz, filtreler, impedanslar) pembe gürültü ve mu ritmi yayınlar:

```powershell
.venv\Scripts\python -m src.simulation.synthetic_eeg
```
*Konsoldan `l` (sol), `r` (sağ), `d` (aşağı), `u` (yukarı), `s` (dinlenme), `b` (göz kırpma) tuşlarıyla ERD durumlarını anlık simüle edebilirsiniz.*

### 2.2 Pilot XDF Kaydından LSL Yayını (Replay)
Gerçek donanımdan kaydedilmiş pilot XDF dosyasını orijinal zamanlaması ve meta verileriyle LSL'e geri yayınlar:

```powershell
.venv\Scripts\python -m src.simulation.xdf_replay
```

### 2.3 Klavye Kontrol Kaynağı (`BCI_Control`)
Ok tuşları (veya WASD) ile `BCI_Control` akışını yayınlar. Oyunu kod çözücüden bağımsız test etmek için kullanılır:

```powershell
# Ayrık (discrete) modda çalıştırma (varsayılan)
.venv\Scripts\python -m src.control.keyboard_source

# Sürekli (continuous) 2B hız modunda çalıştırma
.venv\Scripts\python -m src.control.keyboard_source --mode continuous
```

### 2.4 Seviye 1 Oyunu: "Top Yuvarla" (Ball Roll)
`BCI_Control` akışını dinler (kaynağı bilmez). Topu sol/sağ hedefe götürünce skor artar ve olayları `BCI_Markers` akışına ASCII olarak yazar:

```powershell
# BCI_Control akışını dinleyerek oyunu başlatır
.venv\Scripts\python -m src.game.ball_roll
```

### 2.5 Sinyal Kalitesi Analizi
Bir XDF kaydındaki veya canlı akıştaki kanal başına RMS, 10 Hz mu gücü, 50 Hz şebeke gürültüsü ve flatline durumunu konsola döker:

```powershell
.venv\Scripts\python -m src.signal_quality.quality_metrics
```

---

## 3. Testleri Çalıştırma

Tüm birim, entegrasyon ve uçtan uca simülasyon testlerini çalıştırmak için:

```powershell
.venv\Scripts\python -m pytest -q
```

---

## 4. Sistem Mimarisi ve Belgeler

- [docs/control_contract.md](file:///E:/GitHub/LSLGame/docs/control_contract.md): BCI_Control LSL akışı sözleşmesi (ayrık 5 kanal ve sürekli 2 kanal arayüzü).
- [config/device_xon.yaml](file:///E:/GitHub/LSLGame/config/device_xon.yaml): X.on donanım özellikleri, kanal sırası ve filtre eşikleri.
- [docs/agy_report_01.md](file:///E:/GitHub/LSLGame/docs/agy_report_01.md): Faz 0 ve Faz 2 geliştirme raporu ve test çıktıları.
