"""Verification — otomatik denetleyici (sunum slayt 11, 12).

Sorumluluk: JSON şema + kaynak ID doğrulaması, cevabı atomik iddialara bölüp
her iddiayı getirilen pasajlara göre supported / unsupported etiketleme
(farklı model ailesinden judge), hallucination oranını loglama.

Durum: kaynak ID doğrulaması (`citations.py`) ve iddia kontrolü (`claims.py`, `judge.py`, #10)
çalışıyor; hallucination oranı `hallucination.py`. Kareye dayanan iddialar karenin görüntüsüyle
kontrol edilir (`visual.py`, #26). Karar: DECISIONS.md ADR-8.
"""
