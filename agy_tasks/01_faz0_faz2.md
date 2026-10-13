# Görev 01 — Faz 0 ve Faz 2

Proje kökü: `E:\GitHub\LSLGame`. Önce `PLAN.md`'yi baştan sona oku. Özellikle Bölüm 2.2, 2.3, 2.4, 4, 5, 6, Faz 0 ve Faz 2.

## Kapsam (yalnızca bunlar)

### Faz 0
1. `py -3.12` ile proje kökünde `.venv` sanal ortamı oluştur. Paketleri yalnızca bu ortama kur (global kurulum yok).
2. `requirements.txt` yaz: pylsl, numpy, scipy, pyxdf, pyyaml, pygame-ce, pytest. (MNE/pyRiemann/scikit-learn bu görevde gerekmez.)
3. Bölüm 6'daki klasör yapısını oluştur (`config/`, `src/...`, `tests/`, `docs/`, `analysis/notebooks/`).
4. `config/device_xon.yaml`: Bölüm 2.2'deki bilgiler. Akış eşleme kuralı (`type=EEG`, adı `X.on` ile başlar), 11 kanalın sırası ve etiketleri (F3,F4,C3,Cz,C4,P3,P4,BIP,accX,accY,accZ), EEG indeksleri 0–6, BIP 7, ivmeölçer 8–10, birimler, 250 Hz, cihaz filtreleri (HP 0.5, LP 65).
5. Pilot XDF dosyasını (`sub-P003_ses-S001_task-Default_run-001_eeg.xdf`) **taşı**: `data/pilot/` altına. Silme, kopyalama değil taşıma.
6. `src/acquisition/`: X.on akışını yapılandırmadaki kurala göre bulan, halka tamponlu (son ~5 sn) bir LSL alıcı. Akış meta verisinden impedans ve filtre bloklarını okuyan bir fonksiyon.
7. `README.md`: kurulum ve çalıştırma komutları.

### Faz 2
1. `src/simulation/synthetic_eeg.py`: X.on ile **aynı** akış meta verisiyle (ad `X.on-SIM-0000`, type EEG, 11 kanal, 250 Hz, kanal etiketleri) LSL yayınlayan sentetik EEG. Pembe gürültü + 10 Hz μ ritmi. Seçilen sınıfa göre ilgili kanalda 8–30 Hz gücü ~%40 düşür: sol → C4, sağ → C3, aşağı → Cz, yukarı → C3+C4. İvmeölçerde ~1 g sabit + küçük gürültü. Göz kırpma artefaktı enjeksiyonu (F3/F4) opsiyonel.
2. `src/simulation/xdf_replay.py`: Bir XDF'deki X.on akışını, orijinal zamanlamasıyla ve orijinal meta veriyle LSL'e yeniden yayınlar. Pilot XDF ile çalışmalı.
3. `src/control/`: Bölüm 4.3'teki **kontrol arayüzü sözleşmesi**. `BCI_Control` LSL akışı: ayrık mod `[p_left, p_right, p_up, p_down, p_rest]`, sürekli mod `[vx, vy]`. Sözleşmeyi `docs/control_contract.md`'de belgele.
4. `src/control/keyboard_source.py`: Ok tuşlarıyla `BCI_Control` yayınlayan klavye kaynağı.
5. `src/game/`: Bölüm 6.2'deki Seviye 1 **"Top Yuvarla"** oyununun minimal prototipi (pygame-ce). Yalnızca `BCI_Control` akışını okur, kaynağı bilmez. Hedef sol/sağda belirir, top hedefe gidince skor artar. Oyun olaylarını `BCI_Markers` akışına yazar.
6. Bir **sinyal kalitesi** yardımcı fonksiyonu: kanal başına RMS, 50 Hz bant gücü, 10 Hz bant gücü, flatline tespiti. (GUI şart değil; konsol çıktısı yeterli.)

## Kurallar
- Marker adları yalnızca ASCII (`cue_left`, `target_hit` vb.).
- `PLAN.md`'yi değiştirme. Mevcut hiçbir dosyayı silme.
- Git commit yapma; değişiklikleri ben inceleyeceğim.
- Her modül için `tests/` altında pytest testleri yaz. LSL gerektiren testler gerçek akış açıp kapatabilir. Testler 2 dakikadan kısa sürmeli.
- Sentetik akış için bir uçtan uca test: sentetik EEG yayınla → acquisition modülü akışı bulsun → 2 sn veri alsın → sol sınıfında C4'ün 8–30 Hz gücü C3'ünkünden belirgin düşük olsun.
- Pilot XDF için bir test: dosya okunsun, X.on akışı 11 kanal, ~250 Hz, ~17754 örnek.
- Oyun penceresini testlerde açma (headless / mantık testleri yeterli).

## Bitince
- `.venv\Scripts\python -m pytest -q` çalıştır ve çıktısını raporla.
- Yaptığın her şeyin kısa özetini, oluşturduğun dosyaların listesini ve çalışmayan/eksik kalan noktaları **dürüstçe** `docs/agy_report_01.md` dosyasına yaz.
