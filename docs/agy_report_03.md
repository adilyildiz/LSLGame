# Görev 03 — "Top Yuvarla" Oyun Düzeltmeleri Uygulama ve Doğrulama Raporu

> **Tarih:** 13 Ekim 2026  
> **Durum:** Tamamlandı (28/28 pytest testi başarılı)  
> **Çalışma Dizini:** `E:\GitHub\LSLGame`

---

## 1. Genel Özet

`agy_tasks/03_oyun_duzeltmeleri.md` belgesinde kullanıcı geri bildirimleri doğrultusunda bildirilen iki temel sorun (O1 ve O2) eksiksiz olarak çözülmüştür:

1. **O1 — Bozuk Metinler ve Glif Sorunları:**
   - Yazı tipi seçiminde `pygame.font.SysFont` ile sırasıyla `"segoeui"`, `"arial"`, `"dejavusans"` taranması, bulunamazsa varsayılan yazı tipine dönülmesi sağlandı (`get_system_font`).
   - Ekrandaki tüm metinler imla kurallarına uygun doğru Türkçe ile yazıldı ("Skor", "Hedef: SAĞ" / "Hedef: SOL", "SAĞA GİT" / "SOLA GİT", "SİNYAL YOK", "SİMÜLASYON", "BCI Komut: SAĞ / SOL / DİNLENME").
   - Kutu şeklinde bozuk görünen ok karakteri (`►` / `◄`) kaldırılarak yön oku `pygame.draw.polygon` ile vektörel bir üçgen olarak çizildi (`draw_target_cue`).
   - LSL marker isimlerinin ASCII kalması kuralı (`cue_left`, `cue_right` vb.) titizlikle korundu.

2. **O2 — Oyun Hile Yapılabilirliği ve Hedef/Kural Mekanikleri:**
   - **Rastgele ve Dengeli Hedef Sırası:** Hedefler 4'lük bloklar halinde üretildi (her blokta 2 sol + 2 sağ). Arka arkaya en fazla 3 kez aynı yönün gelmesi kuralı (`max_run <= 3`) uygulandı. `random_seed` ile tekrarlanabilirlik sağlandı.
   - **Iska (Miss):** Top yanlış taraftaki duvara ulaştığında (`ball_x <= min_x` veya `ball_x >= max_x`) deneme ıska sayıldı, puan verilmedi, `target_miss` LSL marker'ı gönderildi ve deneme sonlandırıldı.
   - **Zaman Aşımı (Timeout):** Deneme süresi `trial_timeout` (varsayılan 10.0 sn) değerini aşarsa ıska sayıldı ve `trial_timeout` LSL marker'ı gönderildi.
   - **Denemeler Arası Mola (Inter-Trial Pause):** Her denemeden sonra `inter_trial_pause` (varsayılan 1.5 sn) boyunca top merkezde tutuldu (`ball_x = center_x`), bu sürede gelen kullanıcı/BCI komutları tamamen yok sayıldı. Mola süresi bitince yeni hedef belirdi.
   - **HUD ve Görsel Geri Bildirim:** Sol üstte puan yerine `"İsabet: X / Iska: Y / Doğruluk: %Z"` gösterildi. Her deneme bitiminde ~0.5 sn boyunca isabette yeşil `"İSABET!"`, ıskada kırmızı `"ISKA!"` veya `"ZAMAN AŞIMI!"` görsel geri bildirimi verildi.
   - **LSL Marker Sırası:** Şartnamedeki `trial_start` -> `cue_left|cue_right` -> `target_hit|target_miss|trial_timeout` -> `trial_end` sıralaması korundu.

---

## 2. Madde Madde Değişiklikler ve Doğrulama Kanıtları

### O1 — Metinler Bozuk & Glif Hatası

- **Ne Değişti:**
  - `src/game/ball_roll.py` dosyasına `UI_STRINGS` sözlüğü eklendi. Sözlükteki tüm ekran metinleri Türkçe karakterler içerecek biçimde ("Hedef: SAĞ", "Hedef: SOL", "SAĞA GİT", "SOLA GİT", "SİNYAL YOK", "SİMÜLASYON", "DİNLENME", "İsabet: {hits} / Iska: {misses} / Doğruluk: %{accuracy:.0f}") yapılandırıldı.
  - `get_system_font(size, bold)` fonksiyonu eklendi: Windows ve Linux ortamlarında Türkçe karakterleri kusursuz destekleyen `segoeui`, `arial`, `dejavusans` fontlarını dener.
  - `draw_target_cue(screen, font, center_x, center_y, target_side, color)` fonksiyonu eklendi: Yazı karakteri yerine `pygame.draw.polygon` ile koordinat tabanlı üçgen çizimi yapıldı. Sol hedefte sol ucu sivri, sağ hedefte sağ ucu sivri üçgen ok çizildi.
  - LSL marker isimleri kesinlikle ASCII tutuldu (`isascii()` doğrulaması korundu).
- **Hangi Test Kanıtlıyor:**
  - `tests/test_game_logic.py::test_ui_strings_contain_turkish_characters`
  - `tests/test_game_logic.py::test_markers_are_pure_ascii_and_proper_sequence`
- **Test Doğrulaması:**
  - UI sabitleri taranarak Türkçe karakterlerin ('Ğ', 'İ', 'ı' vb.) bulunduğu ve eski hatalı ASCII ifadelerin ("SAGA GIT", "SINYAL YOK", "SIMULASYON") yer almadığı pencere açılmaksızın doğrulandı.

---

### O2 — Hedef Sırası, Iska, Mola ve HUD Mekanikleri

#### 1. Rastgele Ama Dengeli Hedef Sırası
- **Ne Değişti:**
  - `BallRollGameLogic` sınıfına `generate_balanced_sequence(count, seed)` ve `_generate_block()` eklendi.
  - Hedefler 4'lük bloklar halinde üretilir (2 sol, 2 sağ). 6 olası permütasyon arasından son 3 hedefe bakılarak ardışık 4 aynı yön oluşturmayan permütasyonlar filtrelenir ve RNG ile seçilir.
  - 40 denemelik sırada sol ve sağ sayıları kesin olarak 20-20 eşittir ve en uzun aynı taraf serisi $\le 3$'tür. Kesin sağ-sol değişimi oluşmaz.
- **Hangi Test Kanıtlıyor:**
  - `tests/test_game_logic.py::test_target_sequence_balanced_and_constrained`

#### 2. Yanlış Duvara Gitme (Iska / Target Miss)
- **Ne Değişti:**
  - `BallRollGameLogic.update()` içerisine yanlış duvar çarpışma kontrolü eklendi:
    - `target_side == "right"` iken sol duvara (`ball_x <= min_x`) çarpma.
    - `target_side == "left"` iken sağ duvara (`ball_x >= max_x`) çarpma.
  - Yanlış duvara çarpıldığında `misses += 1`, `last_outcome = "miss"`, LSL'e `target_miss` ve hemen ardından `trial_end` gönderilir. Puan artmaz. Durum `pause` olur ve top merkeze alınır.
- **Hangi Test Kanıtlıyor:**
  - `tests/test_game_logic.py::test_wrong_direction_results_in_miss`
  - Oyuncu sürekli hedefin tersine yönlendirildiğinde: `hits == 0`, `misses == 1`, `target_miss` marker'ı `trial_end`'den önce gönderildi.

#### 3. Zaman Aşımı (Trial Timeout)
- **Ne Değişti:**
  - `BallRollGameLogic` sınıfına `trial_timeout: float = 10.0` parametresi ve `trial_elapsed` sayacı eklendi.
  - Deneme süresi 10.0 saniyeye ulaştığında `misses += 1`, `last_outcome = "timeout"`, LSL'e `trial_timeout` ve ardından `trial_end` gönderilir. Oyun molaya geçer.
- **Hangi Test Kanıtlıyor:**
  - `tests/test_game_logic.py::test_idle_player_trial_timeout`
  - 9.9 sn boyunca hareket etmeyen oyuncu aktif kalır; 10.1 sn'de zaman aşımı gerçekleşir (`trial_timeout` marker'ı kaydedilir).

#### 4. Denemeler Arası Mola (Inter-Trial Pause)
- **Ne Değişti:**
  - `BallRollGameLogic` sınıfına `inter_trial_pause: float = 1.5` parametresi ve `pause_elapsed` sayacı eklendi.
  - Hedef vurulduğunda (`target_hit`), ıska yapıldığında (`target_miss`) veya zaman aşımında (`trial_timeout`) oyun `pause` durumuna geçer.
  - Mola süresince `update()` çağrılarında top merkezde (`center_x, center_y`) kilitlenir; gelen hareket komutları (`vx`, yön tuşları) tamamen yok sayılır.
  - 1.5 saniyelik mola dolduğunda `spawn_new_target()` çağrılarak sonraki deneme başlatılır (`trial_start` ve `cue_*` marker'ları yayınlanır).
- **Hangi Test Kanıtlıyor:**
  - `tests/test_game_logic.py::test_inter_trial_pause_ignores_commands`

#### 5. HUD ve Görsel Geri Bildirim
- **Ne Değişti:**
  - Sol üst köşede skor yerine `"İsabet: X / Iska: Y / Doğruluk: %Z"` formatında dinamik istatistik HUD'u eklendi.
  - Doğruluk oranı `BallRollGameLogic.accuracy` property'si ile hesaplanır (`total == 0` ise `%0`).
  - Mola anında ilk 0.5 saniye boyunca ekranda yeşil renkle `"İSABET!"`, kırmızı renkle `"ISKA!"` veya `"ZAMAN AŞIMI!"` geribildirimi gösterilir; kalan mola süresinde `"Dinlenme..."` yazısı görüntülenir.
- **Hangi Test Kanıtlıyor:**
  - `tests/test_game_logic.py::test_game_logic_headless_movement_and_scoring`
  - `tests/test_game_logic.py::test_ui_strings_contain_turkish_characters`

---

## 3. Pytest Doğrulama Çıktıları

### Headless Oyun Mantığı Testleri (`tests/test_game_logic.py`)
```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- E:\GitHub\LSLGame\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: E:\GitHub\LSLGame
collecting ... collected 7 items

tests/test_game_logic.py::test_game_logic_headless_movement_and_scoring PASSED [ 14%]
tests/test_game_logic.py::test_target_sequence_balanced_and_constrained PASSED [ 28%]
tests/test_game_logic.py::test_wrong_direction_results_in_miss PASSED    [ 42%]
tests/test_game_logic.py::test_idle_player_trial_timeout PASSED          [ 57%]
tests/test_game_logic.py::test_inter_trial_pause_ignores_commands PASSED [ 71%]
tests/test_game_logic.py::test_ui_strings_contain_turkish_characters PASSED [ 85%]
tests/test_game_logic.py::test_markers_are_pure_ascii_and_proper_sequence PASSED [100%]

============================== 7 passed in 0.50s ==============================
```

### Tüm Proje Test Paketi (`.venv\Scripts\python -m pytest -q`)
```text
............................                                             [100%]
28 passed in 19.35s
```

Tüm 28 test (toplama, kontrol sözleşmesi, cihaz konfigürasyonu, sentetik EEG, pilot XDF, sinyal kalitesi, XDF yeniden oynatma ve oyun mantığı) eksiksiz başarıyla geçmektedir.
