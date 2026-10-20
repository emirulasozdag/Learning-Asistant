# Rubrik: soru-cevap puanı ve iddia etiketi

İnsan değerlendiriciler ve judge aynı rubriği kullanır (judge prompt'u: [`harness/judge.py`](../harness/judge.py)).
Rubrik değişirse judge prompt'u da değişir ve kalibrasyon yeniden yapılır.

## Cevap puanı (`score`): eğitmenin referans cevabına göre

| Puan | Anlamı |
|---|---|
| **2** | Tamamen doğru: referanstaki temel noktaların hepsi var, referansla çelişen bir ifade yok |
| **1** | Kısmen doğru: doğru ama eksik ya da küçük bir hata içeriyor |
| **0** | Yanlış: temel nokta yok, referansla çelişiyor ya da soruyu cevaplamıyor |

Yalnızca içeriğin doğruluğu puanlanır. Üslup, uzunluk ve alıntı işaretleri ([1], [2]) puanı etkilemez.
Reddedilen cevaplar tabloya girmez, 0 sayılır.

## İddia etiketi (`label`): getirilen pasajlara göre

Cevap, `harness/claims.py` kuralıyla cümlelere bölünür. Her cümle ayrı etiketlenir:

- **supported** (`s`): iddia pasajlardan en az birinde açıkça yazıyor ya da doğrudan çıkarılabiliyor.
- **unsupported** (`u`): pasajlarda yok, pasajlarla çelişiyor ya da pasajların ötesinde bilgi ekliyor. Genel
  bilgi olarak doğru olsa bile pasajda yoksa `unsupported`.

İddia, referans cevaba göre değil, **sistemin o soruda getirdiği pasajlara** göre etiketlenir (tablodaki
`passages` sütunu). Pasaj kesilmişse ya da eksikse materyalin ilgili sayfasına bakılır.

## Kurallar

- Değerlendiriciler birbirinden bağımsız etiketler; etiketleme bitmeden tartışılmaz.
- `note` sütununa ders içeriği ya da kişisel veri yazılmaz (etiket dosyası git'e girer, not dosyaya alınmaz).
