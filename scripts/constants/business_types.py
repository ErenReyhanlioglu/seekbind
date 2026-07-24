"""Sorgu terimlerini standart işletme tiplerine eşler.

SerpAPI'nin ham `type` alanı çok dağınık olduğu için (aynı kategori
onlarca farklı şekilde etiketlenmiş olabiliyor), normalizasyon için
SerpAPI'nin değil, bizim fetch_serpapi.py'de kullandığımız sabit
query_term'lerin kaynak alınması tercih edildi.
"""

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
