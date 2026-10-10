import math
from typing import Dict, Any, List

def calculate_similarity(track_a: Dict[str, Any], track_b: Dict[str, Any]) -> Dict[str, Any]:
    """
    İki şarkı arasındaki anlamsal ve müzikal benzerlik skorlarını hesaplar (0-100).
    Spotify'ın kapatılan recommendations / audio-features endpoint'leri KULLANILMAZ.
    Boyutlar:
    1. Tema benzerliği (Theme Similarity): %35
    2. Kelime yapısı & Söz Zenginliği benzerliği (Vocab Diversity Similarity): %25
    3. Dil uyumu (Language Compatibility): %20
    4. Tür / Kategori uyumu (Genre Compatibility): %20
    """
    # 1. Tema Benzerliği
    theme_a = track_a.get("theme", "genel")
    theme_b = track_b.get("theme", "genel")
    if theme_a == theme_b and theme_a != "genel":
        theme_sim = 100.0
    elif theme_a == theme_b and theme_a == "genel":
        theme_sim = 60.0
    else:
        theme_sim = 20.0

    # 2. Kelime Yapısı & Anlam Skoru Benzerliği
    score_a = track_a.get("meaningful_score") or 50.0
    score_b = track_b.get("meaningful_score") or 50.0
    diff = abs(score_a - score_b)
    vocab_sim = max(0.0, 100.0 - (diff * 2.5))

    # 3. Dil Uyumu
    lang_a = track_a.get("detected_lang", "unknown")
    lang_b = track_b.get("detected_lang", "unknown")
    if lang_a == lang_b and lang_a != "unknown":
        lang_sim = 100.0
    elif lang_a == "unknown" or lang_b == "unknown":
        lang_sim = 50.0
    else:
        lang_sim = 0.0

    # 4. Tür / Sanatçı Benzerliği
    artist_a = track_a.get("artist", "").lower()
    artist_b = track_b.get("artist", "").lower()
    genre_score_a = track_a.get("genre_match_score", 0.5)
    genre_score_b = track_b.get("genre_match_score", 0.5)

    if any(art.strip() in artist_b for art in artist_a.split(",") if len(art.strip()) > 2):
        genre_sim = 95.0
    else:
        genre_diff = abs(genre_score_a - genre_score_b)
        genre_sim = max(30.0, 100.0 - (genre_diff * 100.0))

    # Ağırlıklı Toplam Benzerlik Skoru
    overall_score = (theme_sim * 0.35) + (vocab_sim * 0.25) + (lang_sim * 0.20) + (genre_sim * 0.20)
    overall_score = round(max(0.0, min(100.0, overall_score)), 1)

    # Açıklanabilir Nedenler
    reasons = []
    if theme_sim >= 80:
        reasons.append(f"Aynı tema (#{theme_a})")
    if vocab_sim >= 80:
        reasons.append("Benzer söz yapısı ve zenginlik")
    if lang_sim == 100:
        reasons.append(f"Aynı dil ({lang_a})")
    if genre_sim >= 80:
        reasons.append("Uyumlu müzik türü")

    return {
        "overall_similarity": overall_score,
        "theme_similarity": theme_sim,
        "vocab_similarity": round(vocab_sim, 1),
        "language_similarity": lang_sim,
        "genre_similarity": round(genre_sim, 1),
        "explanation": ", ".join(reasons) if reasons else "Genel anlamsal yakınlık"
    }

def find_similar_tracks(target_track: Dict[str, Any], candidate_pool: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    """
    Hedef parçaya aday havuzundan en çok benzeyen parçaları sıralar.
    Aynı şarkı veya versiyonları kontrolsüz biçimde önermez.
    """
    target_id = target_track.get("id")
    target_name = target_track.get("name", "").lower()

    scored = []
    for cand in candidate_pool:
        if cand.get("id") == target_id:
            continue
        if cand.get("name", "").lower() == target_name:
            continue

        sim = calculate_similarity(target_track, cand)
        cand_copy = dict(cand)
        cand_copy["similarity_info"] = sim
        scored.append(cand_copy)

    scored.sort(key=lambda x: x["similarity_info"]["overall_similarity"], reverse=True)
    return scored[:limit]
