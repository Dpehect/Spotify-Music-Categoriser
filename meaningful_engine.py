import re
from typing import Dict, Any, List
from langdetect import detect

# 1. Junk / Ad-lib & Lüks Marka Sözlüğü (Anti-Mumble)
JUNK_ADLIBS = [
    r"\bgrr+\b", r"\bskr+t\b", r"\bpaw+\b", r"\bbrr+\b", r"\byeah yeah\b",
    r"\blil\b", r"\baye aye\b", r"\buh uh\b", r"\bla la la\b", r"\bpew pew\b",
    r"\bgucci\b", r"\bprada\b", r"\bbalenciaga\b", r"\blouis vuitton\b",
    r"\brolex\b", r"\bversace\b", r"\blambo\b", r"\bferrari\b", r"\bmaybach\b"
]

# 2. Çok Dilli (TR, EN, ES, DE, FR) Ağırlıklı Pozitif Tema Sözlüğü
# Tier 3 (3.0x): Çekirdek & Kesin Kanıt
# Tier 2 (2.0x): Güçlü Bağlam
# Tier 1 (1.0x): Genel / Bağlamsal
THEME_WEIGHTED_KEYWORDS: Dict[str, Dict[str, float]] = {
    "aşk": {
        # Türkçe
        "aşk": 3.0, "ask": 3.0, "aşık": 3.0, "aşığım": 3.0, "sevgilim": 3.0, "sevgili": 2.0,
        "seviyorum": 3.0, "ayrılık": 3.0, "ayrilik": 3.0, "terk ettin": 3.0, "kalbimi kırdın": 3.0,
        "romantik": 3.0, "vuslat": 3.0, "hasret": 2.0, "kavuşmak": 2.0, "sensizlik": 2.0,
        "sensiz": 2.0, "sevda": 2.0, "öpüş": 2.0, "tutku": 2.0, "bağlandım": 2.0, "kalp": 1.0, "özlem": 1.0,
        # İngilizce (English)
        "love": 3.0, "lover": 3.0, "baby": 1.5, "darling": 3.0, "sweetheart": 3.0,
        "kiss": 2.5, "hug": 2.0, "breakup": 3.0, "broken heart": 3.0, "heartbreak": 3.0,
        "miss you": 3.0, "loving you": 3.0, "romance": 3.0, "passion": 2.0, "affection": 2.0,
        # İspanyolca (Español)
        "amor": 3.0, "amarte": 3.0, "te amo": 3.0, "te quiero": 3.0, "corazón": 2.0,
        "cariño": 2.5, "beso": 2.5, "desamor": 3.0, "ruptura": 3.0, "enamorado": 3.0,
        # Almanca (Deutsch)
        "liebe": 3.0, "liebling": 3.0, "ich liebe dich": 3.0, "herz": 2.0, "kuss": 2.5, "sehnsucht": 2.5,
        # Fransızca (Français)
        "amour": 3.0, "je t'aime": 3.0, "chéri": 3.0, "coeur": 2.0, "bisou": 2.5, "passion": 2.0
    },
    "sokak": {
        # Türkçe
        "getto": 3.0, "varoş": 3.0, "varos": 3.0, "gecekondu": 3.0, "çete": 3.0, "cete": 3.0,
        "torbacı": 3.0, "pusu": 3.0, "köşebaşı": 3.0, "karakol": 3.0, "mahalle": 2.0,
        "semt": 2.0, "sokak": 2.0, "kaldırım": 2.0, "cadde": 2.0, "polis": 2.0, "kurşun": 2.0,
        "asfalt": 2.0, "blok": 2.0, "karanlık": 1.0, "gece": 1.0, "meydan": 1.0, "beton": 1.0,
        # İngilizce (English)
        "ghetto": 3.0, "gang": 3.0, "gangster": 3.0, "hood": 3.0, "block": 2.5,
        "street": 2.5, "cop": 2.5, "police": 2.0, "bullet": 2.5, "gunshot": 2.5,
        "alley": 2.0, "sidewalk": 2.0, "hustle": 2.5, "slums": 3.0,
        # İspanyolca (Español)
        "calle": 2.5, "barrio": 3.0, "pandilla": 3.0, "pistola": 2.5, "policía": 2.0, "esquina": 2.0,
        # Almanca & Fransızca
        "straße": 2.5, "kiez": 3.0, "rue": 2.5, "banlieue": 3.0, "quartier": 2.5
    },
    "dert": {
        # Türkçe
        "çile": 3.0, "cile": 3.0, "efkar": 3.0, "efkarlı": 3.0, "hüsran": 3.0, "kahır": 3.0,
        "kahr": 3.0, "gözyaşı": 3.0, "gozyasi": 3.0, "tükenmiş": 3.0, "keder": 2.0, "dert": 2.0,
        "acı": 2.0, "aci": 2.0, "hüzün": 2.0, "yalnızlık": 2.0, "ağlamak": 2.0, "çaresiz": 2.0,
        "yıkık": 2.0, "gam": 1.0, "dertli": 1.0, "karanlık": 1.0,
        # İngilizce (English)
        "sorrow": 3.0, "grief": 3.0, "pain": 2.5, "tears": 3.0, "crying": 2.5,
        "sadness": 2.5, "melancholy": 3.0, "misery": 3.0, "depressed": 3.0, "lonely": 2.5,
        "despair": 3.0, "hopeless": 2.5, "agony": 3.0, "suffering": 2.5,
        # İspanyolca & Diğer
        "tristeza": 3.0, "dolor": 2.5, "lágrimas": 3.0, "soledad": 2.5, "pena": 2.5,
        "schmerz": 2.5, "trauer": 3.0, "tristesse": 3.0, "douleur": 2.5
    },
    "toplumsal": {
        # Türkçe
        "adalet": 3.0, "sistem": 3.0, "düzen": 3.0, "sömürü": 3.0, "direniş": 3.0,
        "direnis": 3.0, "devrim": 3.0, "haksızlık": 3.0, "yoksulluk": 3.0, "baskı": 2.0,
        "özgürlük": 2.0, "halk": 2.0, "emek": 2.0, "isyan": 2.0, "eşitlik": 2.0,
        "zincir": 2.0, "politika": 2.0, "fakirlik": 1.0, "kanun": 1.0, "eleştiri": 1.0,
        # İngilizce (English)
        "justice": 3.0, "system": 2.5, "revolution": 3.0, "oppression": 3.0, "resistance": 3.0,
        "freedom": 2.5, "liberty": 2.5, "poverty": 3.0, "corruption": 3.0, "society": 2.0,
        "rebellion": 3.0, "protest": 3.0, "inequality": 3.0, "regime": 2.5,
        # İspanyolca & Diğer
        "justicia": 3.0, "revolución": 3.0, "libertad": 2.5, "opresión": 3.0, "pueblo": 2.0,
        "gerechtigkeit": 3.0, "freiheit": 2.5
    },
    "motivasyon": {
        # Türkçe
        "zirve": 3.0, "başarı": 3.0, "basari": 3.0, "zafer": 3.0, "şampiyon": 3.0,
        "asla pes": 3.0, "vazgeçme": 3.0, "pes etme": 3.0, "küllerinden": 3.0,
        "mücadele": 2.0, "kazanmak": 2.0, "yükseliş": 2.0, "azim": 2.0, "inanç": 2.0,
        "çaba": 1.0, "güç": 1.0, "hedef": 1.0,
        # İngilizce (English)
        "victory": 3.0, "champion": 3.0, "success": 3.0, "win": 2.0, "winner": 2.5,
        "never give up": 3.0, "unstoppable": 3.0, "glory": 2.5, "triumph": 3.0,
        "motivate": 2.5, "ambition": 2.5, "power": 1.5, "conquer": 2.5, "rise": 2.0,
        # İspanyolca & Diğer
        "victoria": 3.0, "campeón": 3.0, "éxito": 3.0, "luchar": 2.0, "ganar": 2.0,
        "sieg": 3.0, "erfolg": 3.0, "victoire": 3.0
    },
    "nostalji": {
        # Türkçe
        "mazi": 3.0, "çocukluk": 3.0, "cocukluk": 3.0, "hatıra": 3.0, "hatira": 3.0,
        "eskiden": 3.0, "o günler": 3.0, "unutulmaz": 3.0, "geçmiş": 2.0, "anılar": 2.0,
        "anilar": 2.0, "gençlik": 2.0, "dün": 2.0, "eski": 1.0, "yıllar": 1.0, "zaman": 1.0,
        # İngilizce (English)
        "nostalgia": 3.0, "childhood": 3.0, "memories": 3.0, "yesterday": 2.5, "good old days": 3.0,
        "flashback": 2.5, "remember": 2.0, "past": 2.0, "years ago": 2.5, "remind me": 2.0,
        # İspanyolca & Diğer
        "recuerdos": 3.0, "infancia": 3.0, "pasado": 2.0, "ayer": 2.5, "nostalgie": 3.0
    }
}

# 3. Çok Dilli Negatif Çelişki / Ceza Matrisi (Anti-Keywords Penalty Matrix)
THEME_CONFLICT_PENALTIES: Dict[str, Dict[str, float]] = {
    "aşk": {
        # Türkçe
        "çete": 3.0, "cete": 3.0, "mermi": 3.0, "pusu": 3.0, "torbacı": 3.0,
        "getto": 2.5, "varoş": 2.5, "varos": 2.5, "silah": 2.5, "semt": 2.0,
        "karakol": 2.0, "blok": 2.0, "kurşun": 2.0, "lambo": 1.5, "rolex": 1.5,
        # İngilizce & Diğer
        "gang": 3.0, "gangster": 3.0, "bullet": 3.0, "gun": 2.5, "shoot": 2.5,
        "dealer": 2.5, "pistol": 2.5, "gLock": 2.5, "cop": 2.0, "slums": 2.0
    },
    "sokak": {
        "romantik": 2.5, "sevgilim": 2.0, "kalbimi kırdın": 2.0, "öpüş": 2.0,
        "romance": 2.5, "sweetheart": 2.0, "broken heart": 2.0
    },
    "motivasyon": {
        "çaresiz": 2.5, "tükenmiş": 2.5, "yıkık": 2.0, "intihar": 3.0,
        "hopeless": 2.5, "give up": 3.0, "suicide": 3.0, "despair": 2.5
    },
    "dert": {
        "şampiyon": 2.5, "zafer": 2.5, "zirve": 2.0, "kazandım": 2.0,
        "champion": 2.5, "victory": 2.5, "triumph": 2.5
    }
}

# Müstehcenlik / Küfür Kelimeleri (Temiz / Orta / Serbest filtresi için)
PROFANITY_WORDS = [
    r"\bsik\b", r"\borospu\b", r"\bpiç\b", r"\bamk\b", r"\baq\b", r"\byarrak\b",
    r"\bgöt\b", r"\bfuck\b", r"\bbitch\b", r"\bshit\b", r"\bass\b", r"\bdick\b",
    r"\bputa\b", r"\bmierda\b", r"\bscheiße\b", r"\bmerde\b"
]

def detect_lyrics_language(lyrics_text: str) -> str:
    """Sözlerin dilini tespit eder (tr, en, de, es, fr vb.)."""
    if not lyrics_text:
        return "unknown"
    
    text_lower = lyrics_text.lower()
    
    # 1. Karakter ve Tipik Türkçe Belirteçleri
    turkish_chars = set("çğıöşü")
    if any(c in turkish_chars for c in text_lower):
        # Türkçe karakterler varsa ağırlıklı olarak Türkçedir
        tr_chars_count = sum(text_lower.count(c) for c in turkish_chars)
        if tr_chars_count >= 2:
            return "tr"

    # Türkçe temel bağlaç ve kelimeler kontrolü
    tr_stop_markers = [r"\bbir\b", r"\bben\b", r"\bsen\b", r"\bve\b", r"\bbu\b", r"\biçin\b", r"\byok\b", r"\bvar\b", r"\bgibi\b", r"\bkadar\b", r"\bde\b", r"\bda\b", r"\bama\b"]
    tr_hits = sum(1 for p in tr_stop_markers if re.search(p, text_lower))
    if tr_hits >= 3:
        return "tr"

    # 2. İngilizce belirteçler
    en_stop_markers = [r"\bthe\b", r"\band\b", r"\byou\b", r"\bthat\b", r"\bwith\b", r"\bthis\b", r"\bfrom\b", r"\bhave\b", r"\bfor\b"]
    en_hits = sum(1 for p in en_stop_markers if re.search(p, text_lower))
    if en_hits >= 4 and tr_hits == 0:
        return "en"

    # 3. İspanyolca belirteçler
    es_stop_markers = [r"\bel\b", r"\bla\b", r"\bque\b", r"\by\b", r"\ben\b", r"\buna\b", r"\bpor\b", r"\bpara\b"]
    es_hits = sum(1 for p in es_stop_markers if re.search(p, text_lower))
    if es_hits >= 4 and tr_hits == 0:
        return "es"

    # 4. langdetect ile daha geniş örneklem
    try:
        sample_lines = [line.strip() for line in lyrics_text.splitlines() if len(line.strip()) > 10][:12]
        sample = " ".join(sample_lines)
        if sample and len(sample) >= 20:
            detected = detect(sample)
            # langdetect bazen kısa Türkçe metinleri tl, az, so olarak etiketler
            if detected in ["tl", "az", "uz"] and (tr_hits >= 1 or any(c in turkish_chars for c in text_lower)):
                return "tr"
            return detected
    except Exception:
        pass
    return "unknown"

def analyze_lyrics_comprehensive(
    lyrics_text: str, 
    strictness: str = "balanced", 
    profanity_mode: str = "all", 
    target_theme: str = "all"
) -> Dict[str, Any]:
    """
    Hibrit Çok Dilli TF-IDF & Negatif Ceza Puanı (Anti-Keywords) Destekli Semantik Motor v2.3 PRO
    """
    if not lyrics_text or len(lyrics_text.strip()) < 50:
        return {
            "score": 20.0,
            "is_passed": False,
            "reason": "Sözler çok kısa veya arşivde bulunamadı",
            "theme": "belirsiz",
            "profanity_count": 0,
            "detected_lang": "unknown",
            "components": {
                "vocab_diversity": 20.0,
                "repetition": 20.0,
                "adlib_cleanliness": 100.0,
                "theme_depth": 0.0,
                "net_theme_score": 0.0,
                "target_dominance_ratio": 0.0
            }
        }

    text_lower = lyrics_text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    total_words = len(words)
    if total_words < 25:
        return {
            "score": 30.0,
            "is_passed": False,
            "reason": "Yetersiz kelime sayısı",
            "theme": "belirsiz",
            "profanity_count": 0,
            "detected_lang": "unknown",
            "components": {
                "vocab_diversity": 30.0,
                "repetition": 30.0,
                "adlib_cleanliness": 100.0,
                "theme_depth": 0.0,
                "net_theme_score": 0.0,
                "target_dominance_ratio": 0.0
            }
        }

    # 1. Dil Tespiti
    detected_lang = detect_lyrics_language(lyrics_text)

    # 2. Junk / Ad-lib & Marka Oranı
    junk_count = 0
    for pat in JUNK_ADLIBS:
        junk_count += len(re.findall(pat, text_lower))
    junk_ratio = junk_count / total_words
    adlib_score = max(0.0, min(100.0, round(100.0 - (junk_ratio * 1000.0), 1)))

    # 3. Kelime Çeşitliliği (Type-Token Ratio)
    unique_words = len(set(words))
    vocab_richness = unique_words / total_words
    vocab_score = max(10.0, min(100.0, round((vocab_richness / 0.55) * 100.0, 1)))

    # 4. Satır Tekrar Oranı (Chorus Repetition)
    lines = [l.strip() for l in text_lower.splitlines() if len(l.strip()) > 5]
    total_lines = len(lines)
    unique_lines = len(set(lines))
    line_diversity = (unique_lines / total_lines) if total_lines > 0 else 1.0
    line_score = max(10.0, min(100.0, round((line_diversity / 0.85) * 100.0, 1)))

    # 5. Müstehcenlik / Küfür Sayımı
    profanity_count = 0
    for p in PROFANITY_WORDS:
        profanity_count += len(re.findall(p, text_lower))

    # 6. Çok Dilli Ağırlıklı TF-IDF & Negatif Ceza Hesabı
    net_theme_scores: Dict[str, float] = {}
    raw_theme_scores: Dict[str, float] = {}

    for theme_name, weighted_dict in THEME_WEIGHTED_KEYWORDS.items():
        # A. Pozitif Ağırlıklı Skor
        pos_raw = 0.0
        for kw, weight in weighted_dict.items():
            cnt = len(re.findall(r'\b' + re.escape(kw) + r'\b', text_lower))
            if cnt > 0:
                tf = cnt / total_words
                pos_raw += (tf * 1000.0 * weight)
        raw_theme_scores[theme_name] = pos_raw

        # B. Negatif Çelişki Cezası
        penalty_val = 0.0
        conflict_dict = THEME_CONFLICT_PENALTIES.get(theme_name, {})
        for anti_kw, p_weight in conflict_dict.items():
            cnt = len(re.findall(r'\b' + re.escape(anti_kw) + r'\b', text_lower))
            if cnt > 0:
                tf = cnt / total_words
                penalty_val += (tf * 1000.0 * p_weight)

        # Net Skor (1.5 çarpanıyla ceza düşülür)
        net_score = max(0.0, pos_raw - (1.5 * penalty_val))
        net_theme_scores[theme_name] = round(net_score, 2)

    # En yüksek net skora sahip tema (Baskın Tema)
    top_net_score = max(net_theme_scores.values()) if net_theme_scores else 0.0
    detected_theme = max(net_theme_scores, key=net_theme_scores.get) if top_net_score > 1.2 else "genel"
    theme_depth_score = min(100.0, round(top_net_score * 15.0, 1))

    # 7. Hedef Tema Karar Mekanizması (Dominance Ratio & Strictness Gate)
    theme_matches_target = True
    target_dominance_ratio = 1.0

    if target_theme != "all":
        target_net = net_theme_scores.get(target_theme, 0.0)
        other_scores = [score for t, score in net_theme_scores.items() if t != target_theme]
        max_other = max(other_scores) if other_scores else 0.0
        
        target_dominance_ratio = (target_net / (max_other + 0.1)) if max_other > 0 else (target_net * 2.0)

        # Eşik Değerler:
        if strictness == "strict":
            theme_matches_target = (target_net >= 3.0 and target_dominance_ratio >= 1.5)
        elif strictness == "loose":
            theme_matches_target = (target_net >= 1.2 and target_net >= (max_other * 0.7))
        else: # balanced
            theme_matches_target = (target_net >= 2.0 and target_dominance_ratio >= 1.1)

    # 8. Toplam Skor Formülü
    score = (vocab_score * 0.40) + (line_score * 0.30) + (adlib_score * 0.20) + (theme_depth_score * 0.10)
    score = max(5.0, min(99.0, round(score, 1)))

    thresholds = {"loose": 40.0, "balanced": 60.0, "strict": 75.0}
    required_score = thresholds.get(strictness, 60.0)

    is_passed = (score >= required_score)
    reason_parts = []

    if junk_ratio > 0.04:
        reason_parts.append(f"Yüksek ad-lib/marka oranı (%{int(junk_ratio*100)})")
    if vocab_richness > 0.40:
        reason_parts.append("Zengin kelime haznesi")
    if line_diversity > 0.75:
        reason_parts.append("Düşük nakarat tekrarı")
    if detected_theme != "genel":
        reason_parts.append(f"Baskın Tema: {detected_theme.capitalize()} (Net: {top_net_score})")

    # Küfür filtre kontrolü
    if profanity_mode == "clean" and profanity_count > 0:
        is_passed = False
        reason_parts.append(f"Temiz mod: {profanity_count} argo ifade elendi")
    elif profanity_mode == "moderate" and profanity_count > 3:
        is_passed = False
        reason_parts.append(f"Orta mod eşiği aşıldı ({profanity_count} küfür)")

    # Tema filtresi seçilmişse kontrolü
    if target_theme != "all" and not theme_matches_target:
        is_passed = False
        reason_parts.append(f"Tema uyuşmazlığı: İstenen '{target_theme}', tespit edilen '{detected_theme}'")

    final_reason = ", ".join(reason_parts) if reason_parts else ("Yüksek söz yapısı kalitesi" if is_passed else "Standart söz kalitesi")

    return {
        "score": score,
        "is_passed": bool(is_passed),
        "reason": final_reason,
        "theme": detected_theme,
        "profanity_count": profanity_count,
        "detected_lang": detected_lang,
        "vocab_richness": round(vocab_richness, 3),
        "junk_ratio": round(junk_ratio, 3),
        "components": {
            "vocab_diversity": vocab_score,
            "repetition": line_score,
            "adlib_cleanliness": adlib_score,
            "theme_depth": theme_depth_score,
            "net_theme_score": top_net_score,
            "target_dominance_ratio": round(target_dominance_ratio, 2)
        }
    }
