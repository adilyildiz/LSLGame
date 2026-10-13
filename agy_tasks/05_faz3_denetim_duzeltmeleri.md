# Görev 05 — Faz 3 Denetim Düzeltmeleri

Görev 04'ün çıktısı bağımsız olarak denetlendi. 35 test geçiyor, ancak **kalibrasyon aracı gerçekte çalışmıyordu**. Testler aracın gerçek kod yollarını hiç çalıştırmıyor.

Ayrıca `docs/agy_report_04.md` içindeki "pytest çıktısı" gerçek değil: listelenen 19 test adı projede yok. Bu görevde rapora yazılan her test çıktısı, aşağıda tarif edildiği gibi bir dosyaya **komutla** yazılacak ve elle yazılmayacak.

## K1 — `run_calibration.py` gerçek API ile uyumsuz (DOĞRULANDI)
1. `import copy` eksikti; bu yüzden `search_eeg_stream()` her zaman başarısız oluyordu. Denetçi bunu ekledi. Ama hata `except Exception` ile yutulup "akış bulunamadı" gibi gösteriliyordu. Akış bulunamadığında ayrı, kod hatasında ayrı mesaj olsun. Beklenmeyen istisnaları yutma; logla ve göster.
2. `self.receiver.is_running` kullanılıyor ama `XonStreamReceiver`'da böyle bir özellik yok (`_running` var). `self.receiver.get_window` da yok; tampon `get_latest_window` ile okunuyor. `XonStreamReceiver`'ın gerçek API'sini oku. Gerekirse oraya açık bir `is_running` property'si ekle, ve tüm çağrıları gerçek API'ye uydur.
3. Dosyadaki her dış çağrıyı (`receiver.*`, `marker_pub.*`, `sm.*`, `compute_signal_quality`, `parse_xon_metadata`) gerçek tanımlarıyla karşılaştır. Var olmayan metot/özellik kalmasın.

## K2 — Gerçek entegrasyon testi (mock yok)
`tests/test_calibration_app.py` yaz. Pencere açılmasın: `os.environ["SDL_VIDEODRIVER"] = "dummy"` pygame import edilmeden önce ayarlansın. Test, **gerçek** `CalibrationApp` nesnesini **gerçek** `SyntheticEEGSource` ile uçtan uca koştursun:
1. `search_eeg_stream()` True dönmeli.
2. `update_live_quality()` hatasız çalışmalı ve 7 EEG kanalı için metrik üretmeli.
3. `draw_check_screen()` hatasız çalışmalı.
4. Paradigma kısa sürelerle (aşama başına ~0.1–0.2 sn, 1 run, `mi2`) **gerçek `run()` döngüsü** üzerinden tamamlanmalı. Klavye olaylarını (SPACE ile başlat) `pygame.event.post` ile enjekte et. Gerekirse `run()`'a test için `max_seconds` veya benzeri bir güvenlik parametresi ekle.
5. Oturum JSON günlüğü `logs/` altında oluşmalı ve deneme listesini içermeli. Test sonunda yalnızca kendi oluşturduğu günlük dosyasını temizlesin.
6. Her `draw_cue(sinif)` (`left`, `right`, `feet`, `both_hands`, `arithmetic`, `rest`) ve `draw_pause_screen()` hatasız çalışmalı.

Testin üst süresi 30 sn olsun.

## K3 — Simülatör zaman damgaları gerçekçi değil (DOĞRULANDI)
- **Ölçüm:** `SyntheticEEGSource` örnekleri 10'luk paketlerle zaman damgası vermeden gönderiyor; LSL, damgaları gönderim anına göre geriye tahmin ediyor. Sonuç: örnekler arası boşluk 58 ms'ye kadar çıkıyor. Sınıf değişimi, olay işaretinden 0–33 ms *önce* görünüyor. Bu yüzden simülatörle hizalama ölçmek mümkün değil.
- **Düzeltme:**
  - Simülatör sabit bir örnek sayacıyla çalışsın. Örnek n'nin zaman damgası = `t0 + n / fs` olsun; `t0` başlangıçta `pylsl.local_clock()` ile alınır.
  - `push_chunk` her pakete açık zaman damgasıyla gönderilsin (ör. paketin son örneğinin damgası).
  - Üretim döngüsü gerçek zamandan ileri gitmesin. Bir örnek ancak damga zamanı geldiğinde üretilsin.
  - `set_class()` çağrısının zamanı kaydedilsin. Sınıf değişimi, damgası bu zamandan büyük/eşit olan **ilk örnekten** itibaren uygulansın (örnek düzeyinde, paket düzeyinde değil).
- **İsteğe bağlı senkron kanalı:** `SyntheticEEGSource(sync_channel=True)` verildiğinde BIP kanalına (indeks 7) aktif sınıfın sayısal kodu yazılsın, ör. rest=0, left=1, right=2, … Varsayılan False olsun; BIP 0 kalsın.

## K4 — Gerçek hizalama testi
Mevcut E2E testindeki "en yakın EEG örneği < 20 ms" kontrolü anlamsız: 250 Hz'de örnekler zaten 4 ms aralıklı, hizalama yanlış olsa bile geçer. Yerine şu testi yaz:
1. `sync_channel=True` ile simülatör başlatılır.
2. En az 10 olayda zaman damgası `ts = pylsl.local_clock()` alınır, hemen ardından `set_class(...)` çağrılır ve `cue_*` marker'ı `timestamp=ts` ile gönderilir. Bu sıra kalibrasyon aracındakiyle aynı.
3. Kaydedilen EEG'de BIP kanalındaki basamağın ilk örneğinin zaman damgası bulunur.
4. Her olay için `gecikme = basamak_ts - marker_ts`.
5. **Kabul:** tüm olaylarda `-4 ms ≤ gecikme ≤ 12 ms`. EEG ardışık damga farkı en fazla 6 ms.
6. Denetçinin kendi ölçüm betiği aynı yöntemi kullanıyor; bu kriterleri o betikle tekrar kontrol edeceğim.

## Kurallar
- `PLAN.md`'yi değiştirme. Dosya silme (kendi test günlüğü hariç). Git commit yapma.
- Testleri çalıştırırken çıktıyı **komutla** dosyaya yaz:
  ```
  .venv\Scripts\python -m pytest -q -rA > docs/pytest_output_05.txt 2>&1
  ```
  Raporda bu dosyaya referans ver. Rapora test adı veya çıktı **uydurma**. Denetçi `--collect-only` ile karşılaştıracak.
- Tüm testler geçmeli; toplam süre < 2 dk.
- Çalıştırdığın her komuta zaman sınırı koy; hiçbiri 60 sn'den uzun beklememeli.
- Bitince `docs/agy_report_05.md` yaz: her madde (K1–K4) için ne değişti, hangi test kanıtlıyor. Ölçtüğün gecikme değerlerini (min/ortalama/max) yaz.
