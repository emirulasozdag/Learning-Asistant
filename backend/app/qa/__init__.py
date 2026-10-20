"""Soru-cevap akışı: sohbet geçmişi → hibrit arama → cite-or-decline cevap → kayıt.

Giriş noktası: `service.ask_stream` (olay akışı) ve `service.ask` (tek cevap). Kaydetmeyen hat
`service.answer_stream`; AI Tutor'un `answer_from_course` aracı bunu kullanır.
"""
