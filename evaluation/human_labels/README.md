# human_labels/

İnsan değerlendirici etiketleri ve judge kalibrasyonu. Buradaki dosyalar **metin içermez** (soru id'si, iddia
sırası, iddia metninin SHA-256'sı, puan ve etiket) ve git'e girer. Soru, cevap ve pasaj metni yalnızca
etiketleme tablosunda (`runs/<run_id>.sheet.csv`, git'e girmez) bulunur.

| Dosya | İçerik |
|---|---|
| `<run_id>/sample.json` | Belgelenmiş örneklem: çerçeve (hatasız cevaplanabilir sorular), boyut, tohum, seçilen id'ler |
| `<run_id>/<takma-ad>.json` | Bir değerlendiricinin etiketleri (`LabelSet`, şema: [`harness/labels.py`](../harness/labels.py)) |
| `judge_calibration.json` | Son judge kalibrasyonu: judge modeli, prompt parmak izi, κ'lar, geçti/geçmedi ve nedenleri |
| `pilot/<DERS>/practice_review.<takma-ad>.json` | Pratik sorusu incelemesi: soru kimliği, kabul, ret nedenleri, harcanan süre (`PracticeReviewSet`) |
| `pilot/<DERS>/grading.<takma-ad>.json` | Öğrenci cevabı puanlaması: deneme kimliği, asistan ve eğitmen puanı, kör mü, süre (`GradingSet`) |
| `pilot/<DERS>/survey.json` | Anket: katılımcı kodu (`p01`), onay sürümü, SUS ve memnuniyet (`SurveySet`) |

Pilot dosyalarının şeması [`harness/pilot.py`](../harness/pilot.py); birimler ve iş yükü
[`instruments/README.md`](../instruments/README.md). Katılımcı kodu ile kişi arasındaki eşleme repoya girmez.

Değerlendirici adı yerine **takma ad** kullanılır (`rater-a`, `ta-1`; küçük harf, rakam, tire). Gerçek ad,
öğrenci numarası ya da e-posta yazılmaz.

Akış ve komutlar: [`../README.md`](../README.md) ("İnsan etiketleri ve judge"). Rubrik:
[`../rubrics/qa_answer_and_claims.md`](../rubrics/qa_answer_and_claims.md).

**Durum:** henüz gerçek etiket yok. Pilot dersin gold set'i ve eğitmen onaylı materyali gelince calibration ve
held-out koşuları yapılıp iki değerlendirici etiketleyecek.
