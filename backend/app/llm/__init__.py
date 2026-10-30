"""Model gateway — sağlayıcıdan bağımsız LLM erişimi (sunum slayt 11, 14).

Sorumluluk: kural tabanlı model seçimi (hassas / rutin işler local LLM,
karmaşık / düşük güvenli işler hosted API); tüm çıktılar aynı JSON şemasında.

Durum: hosted istemciler (Gemini, OpenRouter, Anthropic) çalışıyor; anahtar yoksa
`select_client()` None döner ve sistem LLM'siz modda çalışır. Veri sınıfına göre hosted/local
rota ve judge seçimi: ADR-8.
"""
