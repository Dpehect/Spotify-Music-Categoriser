import math
import re
from typing import Dict, List, Tuple, Any, Optional

# 1. Söz Yapısı Segmentasyon Ayırıcı
def segment_lyrics_structure(lyrics_text: str) -> Dict[str, str]:
    """
    Şarkı sözlerini yapısal bölümlere ayırır:
    - Chorus (Nakarat / Hook): %60 Ağırlık
    - Verses (Kıtalar): %30 Ağırlık
    - Bridge / Outro (Köprü & Çıkış): %10 Ağırlık
    """
    if not lyrics_text:
        return {"chorus": "", "verses": "", "bridge": ""}

    sections = {"chorus": [], "verses": [], "bridge": []}
    lines = [line.strip() for line in lyrics_text.splitlines() if line.strip()]

    current_section = "verses"
    chorus_markers = [r"\[nakarat\]", r"\[chorus\]", r"\[hook\]", r"^nakarat:?", r"^chorus:?"]
    verse_markers = [r"\[verse", r"\[kıta", r"^verse:?", r"\[bölüm"]
    bridge_markers = [r"\[bridge\]", r"\[köprü\]", r"\[outro\]", r"^outro:?"]

    has_markers = False
    for line in lines:
        line_lower = line.lower()
        if any(re.search(p, line_lower) for p in chorus_markers):
            current_section = "chorus"
            has_markers = True
            continue
        elif any(re.search(p, line_lower) for p in verse_markers):
            current_section = "verses"
            has_markers = True
            continue
        elif any(re.search(p, line_lower) for p in bridge_markers):
            current_section = "bridge"
            has_markers = True
            continue

        sections[current_section].append(line)

    # Eğer şarkıda açık [Chorus] / [Verse] etiketleri yoksa, nakarat tekrarlayan satırlardan çıkarılır
    if not has_markers or not sections["chorus"]:
        line_counts: Dict[str, int] = {}
        for l in lines:
            line_counts[l] = line_counts.get(l, 0) + 1

        chorus_lines = [l for l in lines if line_counts[l] >= 2 and len(l) > 10]
        verse_lines = [l for l in lines if l not in chorus_lines]

        if chorus_lines:
            sections["chorus"] = chorus_lines
            sections["verses"] = verse_lines
        else:
            # Standart dağılım (İlk 1/3 kıta, orta 1/3 nakarat)
            split_idx = max(1, len(lines) // 3)
            sections["chorus"] = lines[split_idx:split_idx*2]
            sections["verses"] = lines[:split_idx] + lines[split_idx*2:]

    return {
        "chorus": "\n".join(sections["chorus"]),
        "verses": "\n".join(sections["verses"]),
        "bridge": "\n".join(sections["bridge"])
    }

# 2. Akustik ve Müzikal Uyumluluk Doğrulayıcı (Acoustic Cross-Validation Gate)
def evaluate_acoustic_features(
    track_item: Dict[str, Any],
    target_theme: str = "all",
    audio_features: Dict[str, Any] = None
) -> Tuple[float, str]:
    """
    Spotify Audio Features veya parça temposu/süresi üzerinden akustik doğrulama yapar.
    - Hüzün / Aşk şarkısında aşırı dans edilebilir/parti enerjisi varsa negatif ceza uygular.
    - Sokak / Trap şarkısında aşırı sakinlik/enstrümantal durgunluk varsa ceza uygular.
    """
    if target_theme == "all":
        return 1.0, "Akustik Nötr"

    # Eğer Spotify audio_features mevcutsa (Token yetkisi dahilinde)
    if audio_features:
        valence = audio_features.get("valence", 0.5) # Neşe
        energy = audio_features.get("energy", 0.5)   # Enerji
        speechiness = audio_features.get("speechiness", 0.1)

        if target_theme in ["aşk", "dert", "melankoli"]:
            if valence > 0.70:
                penalty = (valence - 0.70) * 1.8
                return max(0.2, round(1.0 - penalty, 2)), "Aşırı yüksek neşe/valence uyumsuzluğu"
            if energy > 0.80:
                penalty = (energy - 0.80) * 1.5
                return max(0.3, round(1.0 - penalty, 2)), "Aşırı yüksek parti/kulüp enerjisi"

        elif target_theme in ["sokak", "motivasyon"]:
            if energy < 0.25:
                return 0.4, "Yetersiz tempo/durgunluk"

        if speechiness > 0.70:
            return 0.1, "Konuşma kaydı (Podcast)"

    # Audio features API kısıtlı olduğunda parça metadata'sı üzerinden sezgisel akustik filtre:
    track_name = (track_item.get("name") or "").lower()
    
    # Hüzün/Aşk ararken remix/club versiyonu cezalandır
    if target_theme in ["aşk", "dert"]:
        party_indicators = ["club mix", "remix", "dance mix", "party edit", "speed up", "extended mix"]
        if any(ind in track_name for ind in party_indicators):
            return 0.35, "Akustik Çelişki (Club/Dance Remix)"

    # Sokak/Trap ararken akustik/ninni cezalandır
    elif target_theme in ["sokak", "motivasyon"]:
        calm_indicators = ["lullaby", "ninni", "sleep", "meditation"]
        if any(ind in calm_indicators for ind in calm_indicators):
            return 0.2, "Akustik Çelişki (Aşırı Sakin/Meditasyon)"

    return 1.0, "Akustik Doğrulandı"
