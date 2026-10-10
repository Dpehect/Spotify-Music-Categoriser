import re
from typing import Dict, Any, List
from taxonomy import CATEGORIES, ALL_GENRES

YEAR_PATTERNS = {
    "90'lar": (1990, 1999),
    "90lar": (1990, 1999),
    "90'lı": (1990, 1999),
    "90li": (1990, 1999),
    "doksanlar": (1990, 1999),
    "80'ler": (1980, 1989),
    "80ler": (1980, 1989),
    "seksenler": (1980, 1989),
    "70'ler": (1970, 1979),
    "2000'ler": (2000, 2009),
    "2000ler": (2000, 2009),
    "2010'lar": (2010, 2019),
    "2010lar": (2010, 2019),
    "2020'ler": (2020, 2026),
    "2020ler": (2020, 2026),
    "yeni çıkan": (2023, 2026),
    "yeni": (2023, 2026),
    "güncel": (2022, 2026),
    "nostalji": (1970, 2000),
    "eski": (1970, 2005)
}

# Kategori anahtar kelimeleri ve taksonomi ID eşlemeleri
CATEGORY_KEYWORDS = {
    "hiphop_rap": ["rap", "türkçe rap", "turkce rap", "hip hop", "hiphop", "trap", "drill", "underground rap", "boom bap"],
    "rock_metal": ["rock", "anadolu rock", "metal", "heavy metal", "punk", "hard rock", "alt rock", "grunge"],
    "pop": ["pop", "türkçe pop", "turkce pop", "dans", "dance pop", "synth pop", "k-pop", "j-pop"],
    "electronic_dance": ["elektronik", "electronic", "edm", "house", "techno", "deep house", "trance", "dubstep"],
    "rnb_soul": ["r&b", "rnb", "soul", "funk", "groove", "neo soul"],
    "acoustic_chill": ["akustik", "acoustic", "lo-fi", "lofi", "chill", "sakin", "huzurlu", "dinlendirici", "ambient", "singer-songwriter"],
    "jazz_blues": ["caz", "jazz", "blues", "bossa nova"],
    "latin_reggae": ["latin", "reggae", "reggaeton", "afrobeat", "salsa", "dancehall"],
    "classical_soundtrack": ["klasik", "classical", "soundtrack", "dizi müzik", "film müzik", "enstrümantal", "piyano"],
    "traditional_folk": ["türkü", "turku", "halk müziği", "özgün müzik", "etnik", "folk", "bağlama"]
}

# Alt Tür eşlemeleri (özellikle çok arananlar)
GENRE_KEYWORDS = {
    "anadolu rock": "anatolian-rock",
    "anatolian rock": "anatolian-rock",
    "türkçe rap": "turkish-rap",
    "turkce rap": "turkish-rap",
    "türkçe pop": "turkish-pop",
    "turkce pop": "turkish-pop",
    "türkçe rock": "turkish-rock",
    "turkce rock": "turkish-rock",
    "boom bap": "boom-bap",
    "boombap": "boom-bap",
    "old school": "old-school-hip-hop",
    "underground": "underground-hip-hop",
    "drill": "drill",
    "trap": "trap",
    "hip hop": "hip-hop",
    "hiphop": "hip-hop",
    "rap": "rap",
    "metal": "metal",
    "heavy metal": "heavy-metal",
    "punk": "punk",
    "grunge": "grunge",
    "indie rock": "indie-rock",
    "indie pop": "indie-pop",
    "indie": "indie",
    "lo-fi": "lo-fi",
    "lofi": "lo-fi",
    "chill": "chill",
    "akustik": "acoustic",
    "acoustic": "acoustic",
    "deep house": "deep-house",
    "techno": "techno",
    "edm": "edm",
    "house": "house",
    "türkü": "turku",
    "turku": "turku",
    "caz": "jazz",
    "jazz": "jazz",
    "blues": "blues"
}

# Genişletilmiş Tema Anahtar Kelimeleri
THEME_KEYWORDS = {
    "sokak": [
        "sokak", "mahalle", "getto", "varoş", "gecekondu", "köşe", "semt", "kaldırım", "polis", 
        "çete", "arka sokak", "cadde", "varos"
    ],
    "aşk": [
        "aşk", "ask", "sevgi", "sevgili", "özlem", "kalp", "ayrılık", "ayrilik", "hasret", "yarim",
        "gözlerin", "gülüm", "seviyorum", "romantik", "tutku", "bağlılık"
    ],
    "dert": [
        "dert", "hüzün", "huzun", "keder", "acı", "aci", "çile", "cile", "efkar", "efkarlı", "karanlık",
        "yalnızlık", "yalnizlik", "gözyaşı", "gozyasi", "ağlamak", "depresif", "çaresiz", "yıkık"
    ],
    "toplumsal": [
        "toplumsal", "düzen", "duzen", "sistem", "adalet", "baskı", "baski", "özgürlük", "ozgurluk",
        "halk", "emek", "isyan", "yoksulluk", "politika", "direniş", "direnis", "haksızlık", "eleştiri"
    ],
    "motivasyon": [
        "motivasyon", "başarı", "basari", "zirve", "çaba", "mücadele", "mücadeleci", "asla pes",
        "zafer", "kazanmak", "yükseliş", "yukselis", "güç", "hedef", "azim", "vazgeçme"
    ],
    "nostalji": [
        "nostalji", "eski", "mazi", "geçmiş", "gecmis", "çocukluk", "cocukluk", "hatıra", "hatira",
        "anılar", "anilar", "yıllar", "dün", "hatırla"
    ]
}

def parse_natural_language_prompt(prompt: str) -> Dict[str, Any]:
    """
    Doğal dil arama ayrıştırıcısı (v2.1 PRO):
    Örn: '90'lar Türkçe rap, sokak hikâyesi anlatan, küfürsüz, derin sözler'
    Çıktı:
    - language: 'tr'
    - category: 'hiphop_rap'
    - genres: ['turkish-rap', 'rap']
    - year_start: 1990, year_end: 1999
    - target_theme: 'sokak'
    - profanity_mode: 'clean'
    - strictness: 'strict'
    - filter_meaningful: True
    """
    prompt_lower = prompt.lower().strip()

    # 1. Dil Tespiti
    lang = "all"
    if any(w in prompt_lower for w in ["türkçe", "turkce", "yerli", "tr"]):
        lang = "tr"
    elif any(w in prompt_lower for w in ["ingilizce", "english", "yabancı", "yabanci", "en"]):
        lang = "en"
    elif any(w in prompt_lower for w in ["ispanyolca", "spanish", "es"]):
        lang = "es"
    elif any(w in prompt_lower for w in ["almanca", "german", "de"]):
        lang = "de"
    elif any(w in prompt_lower for w in ["fransızca", "fransizca", "french", "fr"]):
        lang = "fr"

    # 2. Yıl Aralığı (Örn: 90'lar, 2000-2010 veya regex yıl tespiti)
    year_start = 1990
    year_end = 2026
    year_matched = False

    # Önce on yıllık veya dönem kalıplarını kontrol et (Örn: 90'lar, 2000'ler, 80ler)
    for k, (s, e) in YEAR_PATTERNS.items():
        if k in prompt_lower:
            year_start = s
            year_end = e
            year_matched = True
            break

    # Regex ile doğrudan yıl veya yıl aralığı kontrolü (Örn: "1995 ile 2005", "2015-2020", "2005 yılı")
    if not year_matched:
        year_range_match = re.search(r'\b(19\d\d|20\d\d)\s*(?:-|ile|ve|ila|\.\.)\s*(19\d\d|20\d\d)\b', prompt_lower)
        if year_range_match:
            y1, y2 = int(year_range_match.group(1)), int(year_range_match.group(2))
            year_start, year_end = min(y1, y2), max(y1, y2)
            year_matched = True
        else:
            single_year_match = re.search(r'\b(19\d\d|20\d\d)\b', prompt_lower)
            if single_year_match:
                y = int(single_year_match.group(1))
                year_start, year_end = max(1950, y - 2), min(2026, y + 2)
                year_matched = True

    # 3. Kategori Tespiti
    matched_category = "all"
    for cat_id, kws in CATEGORY_KEYWORDS.items():
        if any(kw in prompt_lower for kw in kws):
            matched_category = cat_id
            break

    # 4. Alt Tür (Genres) Tespiti
    matched_genres = []
    # Uzun anahtar kelimelere öncelik ver ("anadolu rock" önce, "rock" sonra)
    sorted_genre_kws = sorted(GENRE_KEYWORDS.keys(), key=len, reverse=True)
    for kw in sorted_genre_kws:
        if kw in prompt_lower:
            g_tag = GENRE_KEYWORDS[kw]
            # Eğer dil Türkçe ise ve generic rap/pop/rock gelmişse dil özelini ekle
            if lang == "tr" and g_tag in ["rap", "pop", "rock"]:
                tr_tag = f"turkish-{g_tag}"
                if tr_tag not in matched_genres:
                    matched_genres.append(tr_tag)
            if g_tag not in matched_genres:
                matched_genres.append(g_tag)

    # Eğer kategori seçilmiş ama alt tür bulunamamışsa, kategorinin varsayılan ilk 2 türünü koy
    if matched_category != "all" and not matched_genres:
        for cat in CATEGORIES:
            if cat["id"] == matched_category and cat.get("genres"):
                matched_genres = cat["genres"][:2]
                break

    # 5. Tema Tespiti (Çoklu anahtar kelime eşleme)
    matched_theme = "all"
    theme_hit_counts = {}
    for theme_name, kws in THEME_KEYWORDS.items():
        cnt = sum(1 for kw in kws if kw in prompt_lower)
        if cnt > 0:
            theme_hit_counts[theme_name] = cnt

    if theme_hit_counts:
        matched_theme = max(theme_hit_counts, key=theme_hit_counts.get)

    # 6. Küfür / Müstehcenlik Seviyesi
    profanity_mode = "all"
    if any(w in prompt_lower for w in ["küfürsüz", "kufursuz", "temiz", "sansürlü", "sansurlu", "clean", "aile"]):
        profanity_mode = "clean"
    elif any(w in prompt_lower for w in ["orta", "hafif", "az küfür"]):
        profanity_mode = "moderate"

    # 7. Anlamlılık Filtresi ve Katılık (Strictness)
    filter_meaningful = True
    strictness = "balanced"
    if any(w in prompt_lower for w in ["derin", "anlamlı", "anlamli", "felsefi", "şiirsel", "siirsel", "hikaye", "ağır", "agir", "edebi"]):
        strictness = "strict"
    elif any(w in prompt_lower for w in ["gevşek", "gevsek", "hafif", "fark etmez", "serbest", "her şey"]):
        strictness = "loose"

    # 8. Serbest Arama Sözü (Eğer spesifik söz öbeği tırnak içindeyse veya şarkı sözü aranıyorsa)
    lyrics_query = ""
    quote_match = re.search(r'["\']([^"\']+)["\']', prompt)
    if quote_match:
        lyrics_query = quote_match.group(1).strip()

    # 9. Negatif İstem & Kaçınılacak Temalar (Negative Constraints / avoid_themes)
    # Örn: "sokak olmasın", "uyuşturucu hariç", "şiddet istemiyorum", "without gang"
    avoid_themes = []
    avoid_patterns = [
        r"(?:olmasın|olmasin|istemiyorum|hariç|haric|içermeyen|icermeyen|anlatmasın|anlatmasin|without|no)\s+([a-zA-ZçğıöşüÇĞİÖŞÜ]+)",
        r"([a-zA-ZçğıöşüÇĞİÖŞÜ]+)\s+(?:olmasın|olmasin|istemiyorum|hariç|haric|anlatmasın|anlatmasin)"
    ]
    for p in avoid_patterns:
        for m in re.finditer(p, prompt_lower):
            word = m.group(1).strip()
            # Eşleşen kelime bir tema ise veya anahtar kelimesi ise avoid_themes'e ekle
            for t_name, kws in THEME_KEYWORDS.items():
                if word == t_name or word in kws:
                    if t_name not in avoid_themes:
                        avoid_themes.append(t_name)

    # İkincil tema tespiti (Varsa)
    secondary_theme = None
    if len(theme_hit_counts) > 1:
        sorted_themes = sorted(theme_hit_counts.items(), key=lambda x: x[1], reverse=True)
        if sorted_themes[1][0] != matched_theme:
            secondary_theme = sorted_themes[1][0]

    return {
        "language": lang,
        "category": matched_category,
        "genre": matched_genres[0] if matched_genres else "Tümü",
        "genres": matched_genres,
        "year_start": year_start,
        "year_end": year_end,
        "target_theme": matched_theme,
        "secondary_theme": secondary_theme,
        "avoid_themes": avoid_themes,
        "profanity_mode": profanity_mode,
        "strictness": strictness,
        "filter_meaningful": filter_meaningful,
        "lyrics_query": lyrics_query
    }
