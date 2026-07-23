"""İşletme tipi başına online hizmet ve cinsiyet tercihi kuralları.

Bu alanlar da LLM'e bırakılmıyor; kategoriye göre önceden belirleniyor.
"""

DEFAULT_GENDER_PREFERENCE_WEIGHTS: dict[str, float] = {"unisex": 1.0}

# İşletme tipi -> online hizmet verebilir mi
ONLINE_AVAILABLE: dict[str, bool] = {
    "Diş Kliniği": False,
    "Göz Doktoru": False,
    "Psikolog": True,
    "Fizyoterapist": False,
    "Kuaför": False,
    "Berber": False,
    "Güzellik Salonu": False,
    "Nail Salon": False,
    "Epilasyon Merkezi": False,
    "Cilt Bakım Merkezi": False,
    "Spor Salonu": False,
    "Yüzme Havuzu": False,
    "Yoga Stüdyosu": True,
    "Özel Ders": True,
    "Dil Kursu": True,
    "Sürücü Kursu": False,
    "Müzik Kursu": True,
    "Oto Servis": False,
    "Elektrikçi": False,
    "Tesisatçı": False,
    "Klima Servisi": False,
    "Telefon Tamiri": False,
    "Veteriner": False,
    "Fotoğrafçı": False,
    "Noter": False,
    "Muhasebeci": True,
    "Avukat": True,
}

# İşletme tipi -> {cinsiyet: olasılık} (toplamı 1.0 olmalı)
# Her işletme için random.choices ile ağırlıklı seçim yapılır, LLM'e bırakılmaz.
# Belirtilmeyen tipler DEFAULT_GENDER_PREFERENCE_WEIGHTS kullanır.
GENDER_PREFERENCE_WEIGHTS: dict[str, dict[str, float]] = {
    "Kuaför": {"female": 0.7, "unisex": 0.3},
    "Berber": {"male": 0.8, "unisex": 0.2},
    "Güzellik Salonu": {"female": 0.8, "unisex": 0.2},
    "Nail Salon": {"female": 0.85, "unisex": 0.15},
    "Epilasyon Merkezi": {"female": 0.8, "unisex": 0.2},
}
