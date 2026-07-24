"""Kategori grupları, sorgu terimleri ve standart işletme tipleri.

SerpAPI'nin ham `type` alanı çok dağınık olduğu için (aynı kategori
onlarca farklı şekilde etiketlenmiş olabiliyor), normalizasyon için
SerpAPI'nin değil, bizim fetch_serpapi.py'de kullandığımız sabit
query_term'lerin kaynak alınması tercih edildi.
"""

# Kategori grubu -> [türkçe terim, ...]
CATEGORIES: dict[str, list[str]] = {
    "saglik": ["dişçi", "göz doktoru", "psikolog", "fizyoterapist"],
    "guzellik_bakim": [
        "kuaför",
        "berber",
        "güzellik salonu",
        "nail salon",
        "epilasyon",
        "cilt bakımı",
    ],
    "fitness": ["spor salonu", "yüzme havuzu", "yoga"],
    "egitim": ["özel ders", "dil kursu", "sürücü kursu", "müzik kursu"],
    "tamir_bakim": [
        "oto servis",
        "elektrikçi",
        "tesisatçı",
        "klima servisi",
        "telefon tamiri",
    ],
    "diger": ["veteriner", "fotoğrafçı", "noter", "muhasebeci", "avukat"],
}

QUERY_TERM_TO_TYPE: dict[str, str] = {
    "dişçi": "Diş Kliniği",
    "göz doktoru": "Göz Doktoru",
    "psikolog": "Psikolog",
    "fizyoterapist": "Fizyoterapist",
    "kuaför": "Kuaför",
    "berber": "Berber",
    "güzellik salonu": "Güzellik Salonu",
    "nail salon": "Nail Salon",
    "epilasyon": "Epilasyon Merkezi",
    "cilt bakımı": "Cilt Bakım Merkezi",
    "spor salonu": "Spor Salonu",
    "yüzme havuzu": "Yüzme Havuzu",
    "yoga": "Yoga Stüdyosu",
    "özel ders": "Özel Ders",
    "dil kursu": "Dil Kursu",
    "sürücü kursu": "Sürücü Kursu",
    "müzik kursu": "Müzik Kursu",
    "oto servis": "Oto Servis",
    "elektrikçi": "Elektrikçi",
    "tesisatçı": "Tesisatçı",
    "klima servisi": "Klima Servisi",
    "telefon tamiri": "Telefon Tamiri",
    "veteriner": "Veteriner",
    "fotoğrafçı": "Fotoğrafçı",
    "noter": "Noter",
    "muhasebeci": "Muhasebeci",
    "avukat": "Avukat",
}


def get_type_to_category_group() -> dict[str, str]:
    """type_normalized -> category_group eşlemesini üretir (örn. business_types tablosu için)."""
    query_term_to_group = {term: group for group, terms in CATEGORIES.items() for term in terms}
    return {QUERY_TERM_TO_TYPE[term]: group for term, group in query_term_to_group.items()}
