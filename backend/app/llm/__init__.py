"""Model gateway — sağlayıcıdan bağımsız LLM erişimi (sunum slayt 11, 14).

Sorumluluk: kural tabanlı model seçimi (hassas / rutin işler local LLM,
karmaşık / düşük güvenli işler hosted API); tüm çıktılar aynı JSON şemasında.

Durum: Claude (hosted) istemcisi çalışıyor; anahtar yoksa `select_client()` None döner
ve sistem LLM'siz modda çalışır. Local model ve kural tabanlı yönlendirme sonraki adım.
"""
