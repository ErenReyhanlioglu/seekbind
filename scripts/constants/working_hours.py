"""İşletme tipi başına haftalık çalışma saati şablonu.

SerpAPI'nin `hours` alanı ("Kapanmak üzere · 22:00" gibi) o anki
anlık durumu anlatıyor, düzenli haftalık programı vermiyor. Bu yüzden
available_slots üretimi için kategori bazlı bir taban şablon tanımlanır.
Her işletmenin gerçek açılış/kapanış saati, bu taban üzerine
generate_synthetic.py'de WORKING_HOURS_JITTER_OPTIONS_MIN'den seçilen
bir sapma eklenerek üretilir (aynı kategorideki işletmeler birebir aynı
saatte açılmasın diye). Açılış ve kapanış için ayrı ayrı, birbirinden
bağımsız seçim yapılır.
"""

# İşletmenin taban saatine eklenecek olası sapma büyüklükleri (dakika).
# Hepsi 5'in katı olduğu için (taban saatler de öyle), sonuç hep düzgün
# bir dakikada olur, ":52" gibi tuhaf değerler oluşmaz.
WORKING_HOURS_JITTER_OPTIONS_MIN: list[int] = [5, 10, 15, 30, 45, 60, 75, 90]

# İşletme tipi -> {"weekday"/"saturday"/"sunday": (açılış, kapanış) ya da None (kapalı)}
WORKING_HOURS_TEMPLATE: dict[str, dict[str, tuple[str, str] | None]] = {
    "Diş Kliniği": {
        "weekday": ("09:00", "18:00"),
        "saturday": ("09:00", "14:00"),
        "sunday": None,
    },
    "Göz Doktoru": {
        "weekday": ("09:00", "17:30"),
        "saturday": ("09:00", "13:00"),
        "sunday": None,
    },
    "Psikolog": {
        "weekday": ("10:00", "19:00"),
        "saturday": ("10:00", "14:00"),
        "sunday": None,
    },
    "Fizyoterapist": {
        "weekday": ("09:00", "18:00"),
        "saturday": ("09:00", "14:00"),
        "sunday": None,
    },
    "Kuaför": {
        "weekday": ("09:00", "20:00"),
        "saturday": ("09:00", "20:00"),
        "sunday": ("10:00", "18:00"),
    },
    "Berber": {
        "weekday": ("08:00", "20:00"),
        "saturday": ("08:00", "20:00"),
        "sunday": ("10:00", "16:00"),
    },
    "Güzellik Salonu": {
        "weekday": ("09:00", "20:00"),
        "saturday": ("09:00", "20:00"),
        "sunday": ("10:00", "18:00"),
    },
    "Nail Salon": {
        "weekday": ("09:00", "19:00"),
        "saturday": ("09:00", "19:00"),
        "sunday": ("11:00", "17:00"),
    },
    "Epilasyon Merkezi": {
        "weekday": ("09:00", "19:00"),
        "saturday": ("09:00", "17:00"),
        "sunday": None,
    },
    "Cilt Bakım Merkezi": {
        "weekday": ("09:00", "19:00"),
        "saturday": ("09:00", "17:00"),
        "sunday": None,
    },
    "Spor Salonu": {
        "weekday": ("07:00", "23:00"),
        "saturday": ("08:00", "22:00"),
        "sunday": ("09:00", "20:00"),
    },
    "Yüzme Havuzu": {
        "weekday": ("07:00", "22:00"),
        "saturday": ("08:00", "21:00"),
        "sunday": ("08:00", "21:00"),
    },
    "Yoga Stüdyosu": {
        "weekday": ("08:00", "21:00"),
        "saturday": ("09:00", "14:00"),
        "sunday": None,
    },
    "Özel Ders": {
        "weekday": ("14:00", "21:00"),
        "saturday": ("10:00", "18:00"),
        "sunday": ("10:00", "16:00"),
    },
    "Dil Kursu": {
        "weekday": ("09:00", "21:00"),
        "saturday": ("09:00", "17:00"),
        "sunday": None,
    },
    "Sürücü Kursu": {
        "weekday": ("09:00", "19:00"),
        "saturday": ("09:00", "15:00"),
        "sunday": None,
    },
    "Müzik Kursu": {
        "weekday": ("10:00", "20:00"),
        "saturday": ("10:00", "16:00"),
        "sunday": None,
    },
    "Oto Servis": {
        "weekday": ("08:00", "18:00"),
        "saturday": ("08:00", "14:00"),
        "sunday": None,
    },
    "Elektrikçi": {
        "weekday": ("08:00", "18:00"),
        "saturday": ("08:00", "14:00"),
        "sunday": None,
    },
    "Tesisatçı": {
        "weekday": ("08:00", "18:00"),
        "saturday": ("08:00", "14:00"),
        "sunday": None,
    },
    "Klima Servisi": {
        "weekday": ("08:00", "18:00"),
        "saturday": ("08:00", "14:00"),
        "sunday": None,
    },
    "Telefon Tamiri": {
        "weekday": ("09:00", "19:00"),
        "saturday": ("09:00", "17:00"),
        "sunday": None,
    },
    "Veteriner": {
        "weekday": ("09:00", "19:00"),
        "saturday": ("09:00", "15:00"),
        "sunday": None,
    },
    "Fotoğrafçı": {
        "weekday": ("10:00", "19:00"),
        "saturday": ("10:00", "17:00"),
        "sunday": None,
    },
    "Noter": {
        "weekday": ("09:00", "17:00"),
        "saturday": None,
        "sunday": None,
    },
    "Muhasebeci": {
        "weekday": ("09:00", "18:00"),
        "saturday": None,
        "sunday": None,
    },
    "Avukat": {
        "weekday": ("09:00", "18:00"),
        "saturday": None,
        "sunday": None,
    },
}

# İşletme tipi -> o gün gerçekten açık olma olasılığı (0.0-1.0).
# Sadece WORKING_HOURS_TEMPLATE'de o gün için saat tanımlı olan tipler için
# geçerlidir — şablonda zaten None (kapalı) olan tipler için istisna yok.
# generate_synthetic.py'de her işletme için ayrı ayrı zar atılır.
SATURDAY_OPEN_PROBABILITY: dict[str, float] = {
    "Diş Kliniği": 0.6,
    "Göz Doktoru": 0.5,
    "Psikolog": 0.5,
    "Fizyoterapist": 0.6,
    "Kuaför": 0.95,
    "Berber": 0.95,
    "Güzellik Salonu": 0.9,
    "Nail Salon": 0.9,
    "Epilasyon Merkezi": 0.85,
    "Cilt Bakım Merkezi": 0.8,
    "Spor Salonu": 0.95,
    "Yüzme Havuzu": 0.9,
    "Yoga Stüdyosu": 0.7,
    "Özel Ders": 0.7,
    "Dil Kursu": 0.6,
    "Sürücü Kursu": 0.6,
    "Müzik Kursu": 0.6,
    "Oto Servis": 0.85,
    "Elektrikçi": 0.5,
    "Tesisatçı": 0.5,
    "Klima Servisi": 0.5,
    "Telefon Tamiri": 0.8,
    "Veteriner": 0.7,
    "Fotoğrafçı": 0.8,
}

SUNDAY_OPEN_PROBABILITY: dict[str, float] = {
    "Kuaför": 0.5,
    "Berber": 0.4,
    "Güzellik Salonu": 0.4,
    "Nail Salon": 0.45,
    "Spor Salonu": 0.7,
    "Yüzme Havuzu": 0.6,
    "Özel Ders": 0.4,
}
