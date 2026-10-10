import re

# Şarkı sözlerinde yüzeysel / mumble / anlamsız ad-lib ve marka sayıklamalarını filtreleme listesi
JUNK_ADLIBS = [
    r"\bgrr+\b", r"\bskr+t\b", r"\bpaw+\b", r"\bbrr+\b", r"\byeah yeah\b",
    r"\blil\b", r"\baye aye\b", r"\buh uh\b", r"\bla la la\b", r"\bpew pew\b",
    r"\bgucci\b", r"\bprada\b", r"\bbalenciaga\b", r"\blouis vuitton\b",
    r"\brolex\b", r"\bversace\b", r"\blambo\b", r"\bferrari\b"
]

def evaluate_lyric_quality(lyrics_text: str) -> dict:
    """
    Şarkı sözünün kalitesini, anlamlılığını ve 'boş laf / ad-lib' yoğunluğunu analiz eder.
    Dönen sonuç:
    - is_meaningful: bool (Anlamlı ve derinlikli mi?)
    - junk_score: float (0 ile 1 arası çöp/ad-lib oranı)
    - vocabulary_richness: float (Benzersiz kelime çeşitliliği)
    - reason: str
    """
    if not lyrics_text or len(lyrics_text.strip()) < 50:
        return {"is_meaningful": False, "junk_score": 1.0, "reason": "Sözler çok kısa veya eksik"}

    text_lower = lyrics_text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    total_words = len(words)
    if total_words < 20:
        return {"is_meaningful": False, "junk_score": 1.0, "reason": "Yetersiz kelime sayısı"}

    # 1. Junk / Ad-lib / Marka tekrarı sayımı
    junk_matches = 0
    for pattern in JUNK_ADLIBS:
        matches = len(re.findall(pattern, text_lower))
        junk_matches += matches

    junk_ratio = junk_matches / total_words

    # 2. Kelime zenginliği (Benzersiz kelime / Toplam kelime oranı)
    unique_words = len(set(words))
    vocab_richness = unique_words / total_words

    # Eğer kelime zenginliği çok düşükse (aynı kelime 50 kere tekrarlanıyorsa) veya junk_ratio yüksekse
    is_meaningful = True
    reason = "Anlamlı ve zengin sözler"

    if junk_ratio > 0.05: # %5'ten fazla grr, skrt, marka vb.
        is_meaningful = False
        reason = f"Yüksek ad-lib / marka yoğunluğu (%{int(junk_ratio * 100)})"
    elif vocab_richness < 0.25: # Çok aşırı kendini tekrar eden nakarat
        is_meaningful = False
        reason = "Aşırı nakarat tekrarı, düşük kelime çeşitliliği"

    return {
        "is_meaningful": is_meaningful,
        "junk_ratio": round(junk_ratio, 3),
        "vocab_richness": round(vocab_richness, 3),
        "reason": reason
    }
