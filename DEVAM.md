# Kaldığımız Yer — Devam Notu

> Son güncelleme: 14 Ekim 2026, ~00:15
> Çalışma düzeni: Kodlamayı `agy` (Antigravity CLI, `gemini-3.8-flash-high`) yapıyor. Claude Code görevleri yazıyor, ajanı çalıştırıyor ve her çıktıyı **bağımsız olarak** denetliyor: diff incelemesi, testlerin tekrar çalıştırılması, kendi ölçüm betikleri ve ekran görüntüleri.

## Devam etmek için

Bilgisayar açılınca bu klasörde Claude Code'u açın ve şunu yazın:

> **DEVAM.md'yi oku ve kaldığımız yerden devam et.**

## Fazların durumu

| Faz | Durum | Son doğrulanmış commit |
|---|---|---|
| 0 — Ortam | ✅ Kod tamam. Başlıkla 10 dk kesintisiz kayıt testi yapılmadı. | `583d8f8` |
| 2 — Simülasyon + kontrol sözleşmesi | ✅ Denetlendi | `2591493` |
| 6 — Oyun (Seviye 1, "Top Yuvarla") | ✅ Kullanıcı oynadı, düzeltmeler yapıldı | `5b359ec` |
| 3 — Kalibrasyon aracı | ✅ Denetlendi. İşaret–EEG hizalaması +0,4…+3,6 ms. | `65086d6` |
| 4 — Çevrimdışı analiz | ⚠️ **Görev 07 yarıda kaldı** (aşağıya bakın) | `786c2df` (Görev 06 çıktısı, denetlenmemiş düzeltmeler hariç) |
| 1 — Başlıkla sinyal doğrulama | ⏳ EEG cihazı gelince | — |
| 5 — Çevrimiçi kod çözücü | ⏳ Faz 4'ten sonra | — |
| 7, 8 — Eğitim, hibrit | ⏳ | — |

## Yarıda kalan iş: Görev 07 (Faz 4 denetim düzeltmeleri)

- **Talimat:** [agy_tasks/07_faz4_denetim_duzeltmeleri.md](agy_tasks/07_faz4_denetim_duzeltmeleri.md)
- **Ajanın durumu:** Bilgisayar kapanırken çalışıyordu. D1–D4 için kaynak dosyalarda değişiklik yapmıştı, testler henüz yazılmamıştı.
- **WIP commit:** O ana kadarki yarım değişiklikler "WIP" commit'i olarak kaydedildi. **Denetlenmemiş, testler geçmeyebilir.**

**Devam adımları:**
1. `git status` ve `git log -3` ile durumu kontrol et.
2. Görev 07'yi yeniden çalıştır. Ajan yarım değişiklikleri görüp tamamlar:
   ```
   agy --model gemini-3.8-flash-high --mode accept-edits -p "agy_tasks/07_faz4_denetim_duzeltmeleri.md dosyasindaki gorevi eksiksiz uygula. Once o dosyayi oku. Onceki calisma yarida kaldi; mevcut degisiklikleri incele ve tamamla." --print-timeout 0s
   ```
3. **Denetim:**
   - `.venv\Scripts\python -m pytest -q` en az 2 kez çalıştırılır.
   - `docs/pytest_output_07.txt` ve rapordaki test adları `pytest --collect-only` ile karşılaştırılır.
   - `.venv\Scripts\python tools\audit\olcum_sinyalsiz_veri.py` çalıştırılır.
   - **Beklenen:** `erd=0` satırında modeller ~%40–60, p < 0.05 olan tohum ≤ 1/6.
   - **Görev 07 öncesi ölçüm:** 4/6 tohum yanlışlıkla anlamlıydı.
4. Geçerse commit et, sonra Faz 5'e (çevrimiçi kod çözücü) geç.

## Denetimde öğrenilenler (ajanın zayıf noktaları)

- **Uydurma rapor:** Görev 04'te rapordaki pytest çıktısı uydurmaydı; 19 test adı yoktu. O günden beri test çıktısı komutla dosyaya yazdırılıyor ve `--collect-only` ile karşılaştırılıyor.
- **Testler gerçek kod yolunu atlıyor:** Görev 04'te kalibrasyon aracının gerçek yolu hiç test edilmemişti; `copy` import eksikti, olmayan API'ler kullanılıyordu. Artık sahte nesnesiz entegrasyon testi şart.
- **Gevşek testler:** Testler kolayca geçecek şekilde gevşek yazılıyor; ör. "en yakın EEG örneği < 20 ms" testi anlamsızdı. Kritik özellikler denetçinin kendi ölçüm betikleriyle doğrulanıyor: `tools/audit/`.
- **Takılan LSL komutları:** Ajanın LSL betikleri takılabiliyor. Talimatlarda her komuta zaman sınırı istendi.

## Ölçüm betikleri (`tools/audit/`)

- `olcum_hizalama.py`: İşaret–EEG zaman hizalaması (simülatör senkron kanalı). Hedef: −4…+12 ms.
- `olcum_kontrol_akisi.py`: Oyun komut tutma (S1), alıcı zaman aşımı (S2), simülatör ayrımı (S5).
- `olcum_sinyalsiz_veri.py`: Faz 4 sızıntı/şans seviyesi kontrolü.

## Açık sorular (kullanıcı)

- İmpedans birimi: X.on "kilo-Ohm" etiketiyle 66 900 gibi değerler gönderiyor. Ekran bunu Ohm varsayıp kΩ'a çeviriyor; X.on belgelerinden doğrulanmalı.
- EEG cihazı gelince sırasıyla:
  - Faz 1 (sinyal doğrulama + impedans kapısı)
  - 10 dk kesintisiz kayıt testi
  - İlk `mi2` kalibrasyon oturumu:
    ```
    .venv\Scripts\python -m src.calibration.run_calibration --subject sub-01 --profile mi2 --windowed
    ```
    Rehber: [docs/calibration_guide.md](docs/calibration_guide.md)
