import re
from typing import List, Dict, Any, Tuple
from taxonomy import CATEGORIES

# Kategori anahtar kelime ve sanatçı profili eşleme sözlüğü
CATEGORY_TAG_MAP = {
    "hiphop_rap": [
        "hip-hop", "hip hop", "hiphop", "rap", "trap", "drill", "underground rap", "boom bap",
        "türkçe rap", "turkce rap", "rhyme", "mc", "beat", "freestyle", "oldschool",
        # Popüler Türkçe Hip-Hop & Rap Sanatçıları (Tür kesinliği sağlayan anahtar isimler)
        "ceza", "sagopa", "ezhel", "uzi", "batuflex", "motive", "ati242", "cakal", "reckol",
        "şanışer", "saniser", "defkhan", "hidra", "şehinşah", "sehinsah", "no.1", "no 1", "anıl piyancı",
        "anil piyanci", "server uraz", "hayki", "contra", "khontkar", "killa hakan", "blok3",
        "heijan", "muti", "aspova", "tepki", "baneva", "swirf", "velet", "massaka", "canbay", "wolker"
    ],
    "rock_metal": [
        "rock", "metal", "alternative", "punk", "grunge", "anadolu rock", "hard rock",
        "indie rock", "heavy metal", "gitar", "elektro", "rock'n'roll",
        "duman", "mor ve ötesi", "şebnem ferah", "manga", "hayko cepkin", "barış manço",
        "cem karaca", "erkin koray", "kurban", "pentagram", "teoman", "haluk levent", "ogün sanlısoy"
    ],
    "pop": [
        "pop", "synth-pop", "dance-pop", "türkçe pop", "turkce pop", "electropop",
        "hit", "dans", "single",
        "tarkan", "sezen aksu", "murat boz", "hadise", "edis", "sıla", "kenan doğulu",
        "gülşen", "simge", "aleyna tilki", "mustafa sandal", "sertab erener", "mabel matiz"
    ],
    "electronic_dance": [
        "electronic", "edm", "house", "techno", "dance", "club", "trance",
        "deep house", "dubstep", "remix", "dj", "elektronik", "drop", "beat"
    ],
    "rnb_soul": [
        "r&b", "rnb", "soul", "funk", "groove", "neo soul", "motown"
    ],
    "acoustic_chill": [
        "acoustic", "chill", "lo-fi", "lofi", "ambient", "folk", "akustik",
        "dinlendirici", "unplugged", "sakin", "piyano"
    ],
    "jazz_blues": [
        "jazz", "blues", "bossa nova", "caz", "swing", "saksafon"
    ],
    "latin_reggae": [
        "latin", "reggae", "reggaeton", "salsa", "afrobeat", "dancehall", "bachata"
    ],
    "classical_soundtrack": [
        "classical", "soundtrack", "ost", "orchestral", "piano", "klasik",
        "orkestra", "dizi müzik", "film müzik", "enstrümantal"
    ],
    "traditional_folk": [
        "folk", "türkü", "turku", "etnik", "anadolu", "bağlama", "halk müziği", "ozan", "aşık",
        "neşet ertaş", "aşık veysel", "musa eroğlu", "arif sağ", "selda bağcan", "erdal erzincan",
        "cengiz özkan", "kubat", "sabahat akkiraz", "özlem özdil", "yavuz bingöl"
    ]
}

# Çelişen Kategori / Tür Cezalandırma Matrisi (Category Conflicts)
# Örneğin kullanıcı Hip-Hop seçtiğinde Türk Halk Müziği / Türkü / Bağlama kesinlikle elenmeli
CATEGORY_CONFLICTS = {
    "hiphop_rap": [
        "türkü", "turku", "bağlama", "baglama", "halk müziği", "halk muzigi", "oyun havası", "bozlak",
        "türk sanat müziği", "fasıl", "fasli", "ilahiler", "ilahi", "tasavvuf", "mehter",
        "ağıt", "semah", "deyiş", "türküler", "türküleri"
    ],
    "rock_metal": [
        "türkü", "turku", "oyun havası", "fasıl", "türk sanat müziği", "ilahi"
    ],
    "electronic_dance": [
        "türkü", "turku", "bağlama", "halk müziği", "tasavvuf", "ilahi", "türk sanat müziği"
    ],
    "classical_soundtrack": [
        "trap", "drill", "gangsta", "diss", "freestyle", "oyun havası"
    ],
    "traditional_folk": [
        "trap", "drill", "techno", "edm", "heavy metal", "death metal"
    ]
}

def calculate_genre_match_score(
    track_item: Dict[str, Any],
    selected_category: str = "all",
    selected_genres: List[str] = None
) -> Tuple[float, str]:
    """
    Spotify'ın parça ve albüm metadata'sına göre tür uyum skoru (0.0 - 1.0) ve rozet metni döner.
    Zıt/çelişen tür tespit edilirse (örn: Hip-Hop seçilmişken 'türkü' geçmesi) skor 0.10'a düşürülerek elenir.
    """
    has_category = selected_category and selected_category != "all"
    has_genres = selected_genres and any(g != "Tümü" for g in selected_genres)

    if not has_category and not has_genres:
        return 1.0, "Genel Uyumlu"

    # Albüm adı ve sanatçı adında tür ipuçları
    album_name = (track_item.get("album", "") or "").lower()
    track_name = (track_item.get("name", "") or "").lower()
    artist_name = (track_item.get("artist", "") or "").lower()
    combined_text = f"{album_name} {track_name} {artist_name}"

    # 1. Çelişki / Negatif Tür Kontrolü (Hard Negative Filter)
    if has_category and selected_category in CATEGORY_CONFLICTS:
        for conflict_kw in CATEGORY_CONFLICTS[selected_category]:
            if re.search(r'\b' + re.escape(conflict_kw) + r'\b', combined_text):
                return 0.10, f"Uyuşmazlık ({conflict_kw.title()})"

    target_keywords = set()
    if has_category and selected_category in CATEGORY_TAG_MAP:
        target_keywords.update(CATEGORY_TAG_MAP[selected_category])

    if has_genres:
        for g in selected_genres:
            if g and g != "Tümü":
                target_keywords.add(g.replace("-", " ").lower())
                # Eğer turkish-rap gibi bileşikse parçalarını da ekle
                if "turkish" in g:
                    target_keywords.add(g.replace("turkish-", "").lower())

    # Eşleşme kontrolü (kelime sınırlarıyla)
    matched_keywords = []
    for kw in target_keywords:
        if re.search(r'\b' + re.escape(kw) + r'\b', combined_text):
            matched_keywords.append(kw)

    if matched_keywords:
        return 0.95, f"Doğrulandı ({matched_keywords[0].title()})"

    # Sadece tür/kategori odaklı sorgudan geldiyse
    if track_item.get("_sourced_from_genre_query"):
        return 0.80, "Olası Eşleşme"

    return 0.50, "Belirsiz"
