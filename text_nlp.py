import re
from rapidfuzz import fuzz

TURKISH_CHAR_MAP = {
    'ı': 'i', 'İ': 'i', 'I': 'i',
    'ğ': 'g', 'Ğ': 'g',
    'ü': 'u', 'Ü': 'u',
    'ş': 's', 'Ş': 's',
    'ö': 'o', 'Ö': 'o',
    'ç': 'c', 'Ç': 'c'
}

def normalize_turkish(text: str) -> str:
    """
    Türkçe karakterleri ve argo/yazım varyasyonlarını arama için normalize eder.
    'sıfırdan' -> 'sifirdan'
    'gözler' -> 'gozler'
    """
    if not text:
        return ""
    text = text.lower().strip()
    for tr_char, latin_char in TURKISH_CHAR_MAP.items():
        text = text.replace(tr_char.lower(), latin_char)
    # Noktalama ve fazla boşlukları temizle
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def parse_boolean_query(query: str) -> dict:
    """
    Çoklu söz arama için Boolean ayrıştırıcı:
    - Tırnak içinde tam ifade: "sıfırdan zirveye"
    - Hariç tutma: -kelime
    - VE / VEYA mantığı
    """
    exact_phrases = re.findall(r'"([^"]*)"', query)
    remainder = re.sub(r'"[^"]*"', '', query).strip()

    excluded_words = []
    required_words = []
    optional_words = []

    tokens = remainder.split()
    for t in tokens:
        if t.startswith("-") and len(t) > 1:
            excluded_words.append(normalize_turkish(t[1:]))
        elif t.upper() in ["VE", "AND"]:
            continue
        elif t.upper() in ["VEYA", "OR"]:
            continue
        else:
            required_words.append(normalize_turkish(t))

    return {
        "exact_phrases": [normalize_turkish(p) for p in exact_phrases],
        "required_words": required_words,
        "excluded_words": excluded_words
    }

def fuzzy_lyric_match_score(query: str, lyrics_text: str) -> float:
    """
    Bulanık eşleşme skoru (0.0 - 1.0).
    Kullanıcı sözü eksik veya hatalı hatırlasa bile en yüksek benzerliği hesaplar.
    """
    if not query or not lyrics_text:
        return 0.0

    norm_query = normalize_turkish(query)
    norm_lyrics = normalize_turkish(lyrics_text)

    # 1. Tam alt dizi eşleşmesi varsa
    if norm_query in norm_lyrics:
        return 1.0

    # 2. Rapidfuzz partial ratio & token set ratio ile bulanık eşleşme
    ratio = fuzz.partial_ratio(norm_query, norm_lyrics)
    token_ratio = fuzz.token_set_ratio(norm_query, norm_lyrics)

    max_ratio = max(ratio, token_ratio)
    return round(max_ratio / 100.0, 3)

def extract_match_snippet(query: str, lyrics_text: str, max_words: int = 8) -> str:
    """
    Telif kuralı: Şarkı sözünün tamamı yerine sadece eşleşen 5-8 kelimelik kısa alıntı döner.
    """
    if not query or not lyrics_text:
        return ""

    norm_query = normalize_turkish(query)
    lines = lyrics_text.splitlines()

    best_line = ""
    best_score = 0

    for line in lines:
        cleaned_line = re.sub(r'\[\d+:\d+(?:\.\d+)?\]', '', line).strip()
        if not cleaned_line:
            continue
        score = fuzz.partial_ratio(norm_query, normalize_turkish(cleaned_line))
        if score > best_score:
            best_score = score
            best_line = cleaned_line

    if best_line:
        words = best_line.split()
        if len(words) > max_words:
            return " ".join(words[:max_words]) + "..."
        return best_line

    return ""
