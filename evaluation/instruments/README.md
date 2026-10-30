# Etiketleme birimleri, değerlendirici iş yükü ve pilot formları (#18)

Bu belge insan örneklemlerinin **neyi, kaç kez, kimin** etiketleyeceğini sabitler. Dosya biçimleri
[`harness/labels.py`](../harness/labels.py) (soru-cevap) ve [`harness/pilot.py`](../harness/pilot.py) (pratik,
puanlama, anket) içinde; metrikler `python -m harness.trust` ve `python -m harness.pilot` ile hesaplanır.
Hiçbir örneklem sentetik olarak doldurulmaz: eksik etiket boşluk olarak raporlanır.

## Birimler ve sayılar

| Örneklem | Etiket birimi | Etiket | Planlanan | Değerlendirici | Dosya |
|---|---|---|---|---|---|
| Cevap doğruluğu | `full` koşulundaki bir (soru, cevap) çifti | 0 / 1 / 2 (rubrik: `rubrics/qa_answer_and_claims.md`) | 40 held-out cevap | 2 bağımsız (takma adlı) | `human_labels/<run_id>/<takma-ad>.json` |
| Hallucination | Aynı 40 cevabın her iddiası (cümle) | supported / unsupported | 40 cevaptaki tüm iddialar | aynı 2 değerlendirici | aynı dosya |
| Pratik kalitesi | Öğrenciye gösterilmiş bir pratik sorusu | kabul / ret + ret nedeni | 40 soru | eğitmen ya da TA (ikincisi isteğe bağlı) | `pilot/<DERS>/practice_review.<takma-ad>.json` |
| Puanlama uyumu | Onaylı (`research_logged`) bir öğrenci cevabı | rubrik aralığında tam sayı puan | 60 cevap | eğitmen ya da TA, **kör** | `pilot/<DERS>/grading.<takma-ad>.json` |
| Kullanılabilirlik | Bir gönüllünün anketi | SUS (10 madde, 1–5) + memnuniyet (1–5) | ≥ 20 gönüllü | gönüllünün kendisi | `pilot/<DERS>/survey.json` |

**Dört koşulun tamamı insanla etiketlenmez.** 150 soru × 4 koşulun doğruluk ve hallucination değerleri judge ile
hesaplanır; judge'a ancak `full` koşulundaki 40 cevapta insanla uyumu **κ ≥ 0,6** ise güvenilir (#13). İnsan
etiketi yalnızca `full` koşulunda toplanır. ANALYSIS §9'daki "yaklaşık 200 insan etiketi" cevap düzeyindeki
birimleri sayar: 2 × 40 cevap puanı + 40 pratik incelemesi + 60 puanlanan cevap = 180. İddia etiketleri buna ek
olarak, aynı 40 cevaptaki iddia sayısı × 2 kadardır. Bu sayı cevap uzunluğuna bağlıdır ve etiketleme
tablosundan okunur.

## İş yükü nasıl ölçülür

Birim başına süre tahmin edilmez, ölçülür:

1. Her değerlendirici ilk 10 birimi etiketler ve harcadığı süreyi dosyadaki `minutes_spent` alanına yazar.
2. `python -m harness.pilot` birim başına dakikayı raporlar ("Değerlendirici iş yükü"). Kalan iş bu ölçümle
   planlanır ve sprint kapasitesine yazılır (#3: değerlendirme iş yükü issue sayısıyla değil, ölçümle dengelenir).
3. Süresi yazılmamış etiket dosyası rapora "iş yükü ölçülemedi" boşluğu olarak düşer.

## Örneklem seçimi

- **Cevaplar:** `harness.labels sample` held-out koşu kaydından tohumlu rastgele örneklem alır (hatasız
  cevaplanabilir sorular). Seçim `sample.json`'a yazılır.
- **Pratik soruları:** öğrencilere gösterilmiş (kontrolden geçmiş) sorulardan rastgele 40 tane. Konu ve tür (çoktan
  seçmeli / açık uçlu) dağılımı raporda belirtilir.
- **Öğrenci cevapları:** yalnızca cevap anında araştırma onayı verilmiş (`research_logged`) denemelerden rastgele
  60 tane. Doğru, kısmen doğru, yanlış ve boş/ilgisiz cevaplar mümkünse dengelenir (#20 kabul kriteri).
- **Gönüllüler:** pilot oturumuna katılan, aydınlatma metninin güncel sürümünü kabul etmiş en az 20 öğrenci.

## Formlar

**Pratik sorusu incelemesi.** Soru şu üç koşulu da sağlıyorsa kabul edilir: doğru (anahtar ve seçenekler), kaynak
pasajla desteklenen ve öğretici. Değilse en az bir neden seçilir: `incorrect`, `answer_key_wrong`,
`not_supported_by_source`, `ambiguous`, `distractor_problem`, `off_topic`, `trivial`, `other`.

**Kör puanlama.** Eğitmen/TA soruyu, referans cevabı, rubriği ve öğrenci cevabını görür. Asistanın puanını ve geri
bildirimini görmez. Asistan puanı dosyaya sonradan, sistemden aktarılır. Kör olmayan puanlama `blind: false` ile
işaretlenir ve raporda not düşülür. QWK rubriğin tanımlı puan aralığıyla (`min_score`–`max_score`) hesaplanır.

**Anket.**
- SUS: Brooke'un (1996) 10 maddelik ölçeği kullanılır, 1–5 Likert. Tek numaralı maddeler olumlu, çift
  numaralılar olumsuzdur.
- Madde metinleri, ekibin seçeceği yayımlanmış Türkçe uyarlamadan alınır; madde sırası ve yönü değiştirilmez.
  Seçilen uyarlama ve form sürümü `instrument_version`'a yazılır (**henüz seçilmedi**, envanterde eksik girdi).
- Ek madde: "Genel olarak asistandan ne kadar memnun kaldın?" (1 = hiç, 5 = çok).
- Ad, öğrenci numarası ya da e-posta sorulmaz. Katılımcı kodu (`p01`…) ile kişi arasındaki eşleme repoya girmez.

**Onay.**
- Anket ve puanlama örneklemi, aydınlatma metninin sürümüyle (ADR-4) kaydedilir (`consent_version`).
- Onaysız cevap ve anket kaydedilmez.
- Pilot öncesi bölüm/etik onayı gerekir (envanterde eksik girdi).
