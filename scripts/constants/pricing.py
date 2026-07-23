"""İşletme tipi başına makul fiyat aralığı ve randevu süresi seçenekleri.

LLM'e serbest fiyat/süre ürettirmek tutarsızlığa yol açar (bir işletme
500-3000 TL derken diğeri 200-5000 TL diyebilir). Bunun yerine LLM,
burada tanımlı aralık/liste içinden seçim yapar.
"""

# İşletme tipi -> {"min": ..., "max": ...} (TL)
PRICE_RANGES_TL: dict[str, dict[str, int]] = {
    "Diş Kliniği": {"min": 500, "max": 8000},
    "Göz Doktoru": {"min": 300, "max": 1500},
    "Psikolog": {"min": 600, "max": 2500},
    "Fizyoterapist": {"min": 400, "max": 1500},
    "Kuaför": {"min": 150, "max": 1200},
    "Berber": {"min": 100, "max": 400},
    "Güzellik Salonu": {"min": 200, "max": 2000},
    "Nail Salon": {"min": 150, "max": 600},
    "Epilasyon Merkezi": {"min": 200, "max": 1500},
    "Cilt Bakım Merkezi": {"min": 300, "max": 2000},
    "Spor Salonu": {"min": 500, "max": 3000},
    "Yüzme Havuzu": {"min": 300, "max": 1500},
    "Yoga Stüdyosu": {"min": 300, "max": 1200},
    "Özel Ders": {"min": 300, "max": 1000},
    "Dil Kursu": {"min": 1500, "max": 8000},
    "Sürücü Kursu": {"min": 8000, "max": 20000},
    "Müzik Kursu": {"min": 400, "max": 1200},
    "Oto Servis": {"min": 500, "max": 15000},
    "Elektrikçi": {"min": 300, "max": 3000},
    "Tesisatçı": {"min": 300, "max": 3000},
    "Klima Servisi": {"min": 400, "max": 4000},
    "Telefon Tamiri": {"min": 300, "max": 5000},
    "Veteriner": {"min": 300, "max": 3000},
    "Fotoğrafçı": {"min": 1000, "max": 15000},
    "Noter": {"min": 200, "max": 2000},
    "Muhasebeci": {"min": 1000, "max": 5000},
    "Avukat": {"min": 2000, "max": 20000},
}

# İşletme tipi -> olası randevu süreleri (dakika)
APPOINTMENT_DURATIONS_MIN: dict[str, list[int]] = {
    "Diş Kliniği": [30, 45, 60, 90],
    "Göz Doktoru": [20, 30, 45],
    "Psikolog": [50, 60],
    "Fizyoterapist": [30, 45, 60],
    "Kuaför": [30, 45, 60, 90],
    "Berber": [20, 30, 45],
    "Güzellik Salonu": [45, 60, 90, 120],
    "Nail Salon": [30, 45, 60],
    "Epilasyon Merkezi": [20, 30, 45],
    "Cilt Bakım Merkezi": [30, 45, 60],
    "Spor Salonu": [60, 90, 120],
    "Yüzme Havuzu": [45, 60],
    "Yoga Stüdyosu": [60, 75, 90],
    "Özel Ders": [45, 60, 90],
    "Dil Kursu": [60, 90],
    "Sürücü Kursu": [45, 60],
    "Müzik Kursu": [30, 45, 60],
    "Oto Servis": [60, 120, 180, 240],
    "Elektrikçi": [30, 60, 90, 120],
    "Tesisatçı": [30, 60, 90, 120],
    "Klima Servisi": [45, 60, 90],
    "Telefon Tamiri": [20, 30, 45, 60],
    "Veteriner": [20, 30, 45],
    "Fotoğrafçı": [60, 90, 120, 180],
    "Noter": [15, 20, 30],
    "Muhasebeci": [30, 45, 60],
    "Avukat": [30, 45, 60],
}
