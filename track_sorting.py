import random
from typing import List, Dict, Any

def sort_tracks(tracks: List[Dict[str, Any]], sort_by: str = "relevance") -> List[Dict[str, Any]]:
    """
    Desteklenen Sıralama Modları:
    - relevance: Anlamlılık + Tür Uyumu + Eşleşme (Varsayılan)
    - meaningful_score: En yüksek söz yapısı skoru
    - lyrics_match: En iyi söz arama eşleşmesi
    - genre_match: En iyi tür uyumu
    - popularity: En popüler parçalar (popularity güvenilir olduğunda)
    - newest: En yeni parçalar (geçerli release_date varsa)
    - random: Rastgele keşif karışımı
    """
    sorted_list = list(tracks)

    if sort_by == "meaningful_score":
        sorted_list.sort(
            key=lambda x: (
                x.get("analysis_status") == "tamamlandi",
                x.get("meaningful_score") if x.get("meaningful_score") is not None else -1
            ),
            reverse=True
        )
    elif sort_by == "lyrics_match":
        sorted_list.sort(
            key=lambda x: (x.get("match_score") or 0, bool(x.get("snippet"))),
            reverse=True
        )
    elif sort_by == "genre_match":
        sorted_list.sort(
            key=lambda x: (x.get("genre_match_score") or 0),
            reverse=True
        )
    elif sort_by == "popularity":
        sorted_list.sort(
            key=lambda x: (x.get("popularity") or 0),
            reverse=True
        )
    elif sort_by == "newest":
        sorted_list.sort(
            key=lambda x: (x.get("release_date") or ""),
            reverse=True
        )
    elif sort_by == "random":
        random.shuffle(sorted_list)
    else: # relevance
        sorted_list.sort(
            key=lambda x: (
                x.get("analysis_status") == "tamamlandi",
                x.get("components", {}).get("target_dominance_ratio", 1.0),
                x.get("meaningful_score") or 0,
                (x.get("genre_match_score") or 0.5) * 20,
                (x.get("popularity") or 0) * 0.1
            ),
            reverse=True
        )

    return sorted_list
