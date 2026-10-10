import re

# Şarkı varyasyon regex'leri
VERSION_PATTERNS = [
    (r'(?i)\b(radio\s+edit|radio\s+version)\b', 'radio_edit'),
    (r'(?i)\b(remaster(ed)?(\s+\d{4})?)\b', 'remaster'),
    (r'(?i)\b(remix|rmx)\b', 'remix'),
    (r'(?i)\b(live(\s+at|\s+version|\s+\d{4})?)\b', 'live'),
    (r'(?i)\b(instrumental|enstrümantal|beat)\b', 'instrumental'),
    (r'(?i)\b(karaoke)\b', 'karaoke'),
    (r'(?i)\b(acoustic|akustik)\b', 'acoustic'),
    (r'(?i)\b(clean(\s+version)?)\b', 'clean'),
    (r'(?i)\b(explicit(\s+version)?)\b', 'explicit'),
]

def clean_song_title(title: str) -> tuple[str, list[str]]:
    """
    Şarkı başlığını varyasyon eklerinden temizler ve tespit edilen etiketleri döner.
    Örn: 'Cambaz - Live 2008 (Remastered)' -> ('cambaz', ['live', 'remaster'])
    """
    detected_versions = []
    clean = title

    for pattern, tag in VERSION_PATTERNS:
        if re.search(pattern, clean):
            detected_versions.append(tag)
            clean = re.sub(pattern, '', clean)

    # Parantez içindeki gereksiz ifadeleri ve artık sembolleri temizle
    clean = re.sub(r'[\(\[\{][^\)\]\}]*[\)\]\}]', '', clean)
    clean = re.sub(r'[-–—:]+', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip().lower()

    return clean, detected_versions

def deduplicate_tracks(
    tracks: list[dict],
    preferred_version: str = "original",
    allow_instrumental: bool = False
) -> list[dict]:
    """
    ISRC ve normalize edilmiş başlık + ana sanatçı ikilisiyle şarkıları tekilleştirir.
    - spotify_track_id asla ISRC olarak kullanılmaz.
    - ISRC mevcutsa önce ISRC bazlı tekilleştirme yapılır.
    - ISRC yoksa normalize başlık ve ana sanatçı çifti gruplanır.
    - preferred_version: 'original', 'radio_edit', 'remaster', 'remix', 'live', 'any'
    - allow_instrumental: False ise Karaoke ve Instrumental sürümler elenir.
    """
    seen_isrcs = set()
    cleaned_candidates = []

    # 1. Aşama: Enstrümantal/Karaoke filtreleme ve ön temizlik
    for track in tracks:
        raw_name = track.get("name", "")
        norm_title, tags = clean_song_title(raw_name)

        if not allow_instrumental and any(t in tags for t in ["instrumental", "karaoke"]):
            continue

        track["_detected_tags"] = tags
        track["_norm_title"] = norm_title
        cleaned_candidates.append(track)

    # 2. Aşama: Şarkıları normalize başlık + ana sanatçı bazında grupla
    grouped_tracks = {} # (norm_title, primary_artist) -> list of tracks

    for track in cleaned_candidates:
        primary_artist = track.get("artist", "").split(",")[0].strip().lower()
        norm_title = track.get("_norm_title", "")
        key = (norm_title, primary_artist)

        if key not in grouped_tracks:
            grouped_tracks[key] = []
        grouped_tracks[key].append(track)

    # 3. Aşama: Her grup içinden preferred_version'a göre en uygun kaydı seç
    final_tracks = []
    for key, candidate_list in grouped_tracks.items():
        # ISRC'si olanları önceliklendirerek veya preferred_version'a göre seç
        best_track = candidate_list[0]
        if len(candidate_list) > 1 and preferred_version != "any":
            for cand in candidate_list:
                tags = cand.get("_detected_tags", [])
                if preferred_version in tags:
                    best_track = cand
                    break
                elif preferred_version == "original" and len(tags) == 0:
                    best_track = cand
                    break

        # ISRC kontrolü (farklı gruplar aynı ISRC'yi paylaşamaz)
        track_isrc = best_track.get("isrc")
        if track_isrc and track_isrc != best_track.get("id"):
            if track_isrc.upper() in seen_isrcs:
                continue
            seen_isrcs.add(track_isrc.upper())

        final_tracks.append(best_track)

    return final_tracks
