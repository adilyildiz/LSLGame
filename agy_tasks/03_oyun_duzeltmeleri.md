# Görev 03 — "Top Yuvarla" Oyun Düzeltmeleri (Kullanıcı Geri Bildirimi)

Kullanıcı oyunu oynadı ve iki sorun bildirdi. Yalnızca `src/game/ball_roll.py` ve ilgili testleri değiştir.

## O1 — Metinler bozuk
- "SAGA GIT ►" metnindeki ► karakteri kutu olarak görünüyor. pygame'in varsayılan yazı tipinde bu glif yok.
- Türkçe karakterler kullanılmamış ("SAG", "SAGA GIT").

**Düzeltme:**
- Türkçe karakterleri destekleyen bir sistem yazı tipi kullan: `pygame.font.SysFont` ile sırayla "segoeui", "arial", "dejavusans" dene. Hiçbiri yoksa varsayılana dön.
- Tüm metinleri doğru Türkçe yaz: "Skor", "Hedef: SAĞ" / "Hedef: SOL", "SAĞA GİT" / "SOLA GİT", "SİNYAL YOK", "SİMÜLASYON", "BCI Komut: SAĞ / SOL / DİNLENME".
- Ok işaretini yazı karakteriyle değil, `pygame.draw.polygon` ile çizilmiş bir üçgenle göster.
- Not: LSL **marker** adları ASCII kalmalı (`cue_left` vb.). Türkçe karakterler yalnızca ekranda görünen metinlerde kullanılacak.

## O2 — Oyun hile yapılabilir durumda (DOĞRULANDI)
- Hedefler kesin olarak sırayla geliyor: sağ, sol, sağ, sol... Kullanıcı düşünmeden tuşları sırayla basarak puan topluyor.
- Top yanlış duvara gidince orada sonsuza kadar kalıyor ve bu bir hata sayılmıyor.

Bu, BCI eğitimi açısından da kritik. Hedef sırası tahmin edilebilirse, kullanıcı (ve ileride sınıflandırıcı) beyin sinyali yerine sırayı öğrenir.

**Düzeltme:**
1. **Rastgele ama dengeli hedef sırası:** Hedefleri 4'lük bloklar halinde üret; her blokta 2 sol + 2 sağ, karıştırılmış. Aynı taraf en fazla 3 kez üst üste gelebilir. `random_seed` ile tekrarlanabilir olsun.
2. **Iska:** Top yanlış taraftaki duvara (veya hedefin karşı tarafındaki bir ıska bölgesine) ulaşırsa deneme ıska sayılır. Puan verilmez, `target_miss` marker'ı gönderilir, deneme biter.
3. **Zaman aşımı:** Bir deneme `trial_timeout` (varsayılan 10 sn) içinde bitmezse ıska sayılır ve `trial_timeout` marker'ı gönderilir.
4. **Denemeler arası mola:** Her denemeden sonra `inter_trial_pause` (varsayılan 1.5 sn) boyunca top ortada durur ve kontrol yok sayılır, sonra yeni hedef belirir. Bu süre PLAN.md'deki dinlenme aralığına karşılık gelir.
5. **HUD:** Puan yerine "İsabet: X / Iska: Y / Doğruluk: %Z" göster. Kısa geri bildirim de ver: isabette yeşil, ıskada kırmızı, ~0.5 sn.
6. Mevcut marker sırası korunsun: `trial_start`, `cue_left|cue_right`, ardından `target_hit|target_miss|trial_timeout`, en son `trial_end`.

## Testler (headless)
- 40 denemelik bir sırada sol/sağ sayıları eşit, en uzun aynı-taraf serisi ≤ 3. Sıra kesin sağ-sol değişimi DEĞİL.
- Yanlış yöne sürekli giden oyuncu: isabet 0, ıska > 0.
- Hiç hareket etmeyen oyuncu: 10 sn sonra `trial_timeout`.
- Mola sırasında gelen komutlar topu hareket ettirmiyor.
- Ekranda kullanılan metinlerin Türkçe karakter içerdiğini kontrol eden basit bir test. Pencere açma; metinleri bir sabit/fonksiyondan oku.

## Kurallar
- `PLAN.md`'yi değiştirme. Dosya silme. Git commit yapma.
- Tüm testler geçmeli: `.venv\Scripts\python -m pytest -q`.
- Çalıştırdığın her komuta zaman sınırı koy; hiçbiri 60 sn'den uzun beklememeli.
- Bitince `docs/agy_report_03.md` yaz: ne değişti, hangi test kanıtlıyor, pytest çıktısı.
