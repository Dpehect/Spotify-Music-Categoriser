from abc import ABC, abstractmethod
from typing import Optional, List, Dict
import urllib.request
import urllib.parse
import json
import re
import os
import requests
from bs4 import BeautifulSoup
import syncedlyrics

class BaseLyricsProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def get_lyrics(self, artist: str, title: str) -> Optional[str]:
        """Sanatçı ve şarkı adı için tam sözleri döner (yalnızca analiz amaçlı)."""
        pass

    @abstractmethod
    def search_by_phrase(self, phrase: str, lang: str = "all", limit: int = 10) -> List[Dict[str, str]]:
        """Verilen söz öbeğini içeren şarkı ve sanatçıları listeler."""
        pass


class LRCLIBProvider(BaseLyricsProvider):
    """
    LRCLIB: Açık kaynak, tamamen ücretsiz ve telif/rate limit dostu lirik sağlayıcısı.
    """
    @property
    def name(self) -> str:
        return "LRCLIB"

    def get_lyrics(self, artist: str, title: str) -> Optional[str]:
        clean_title = re.sub(r'\(.*?\)|\[.*?\]', '', title).strip()
        params = urllib.parse.urlencode({
            "artist_name": artist.split(",")[0].strip(),
            "track_name": clean_title
        })
        url = f"https://lrclib.net/api/get?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "SpotifyLyricsFinder/2.0"})
        try:
            with urllib.request.urlopen(req, timeout=4) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    plain = data.get("plainLyrics")
                    synced = data.get("syncedLyrics")
                    if plain:
                        return plain
                    if synced:
                        return re.sub(r'\[\d+:\d+(?:\.\d+)?\]', '', synced).strip()
        except Exception:
            pass
        return None

    def search_by_phrase(self, phrase: str, lang: str = "all", limit: int = 10) -> List[Dict[str, str]]:
        params = urllib.parse.urlencode({"q": phrase})
        url = f"https://lrclib.net/api/search?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "SpotifyLyricsFinder/2.0"})
        results = []
        try:
            with urllib.request.urlopen(req, timeout=4) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    for item in data[:limit]:
                        results.append({
                            "artist": item.get("artistName", ""),
                            "title": item.get("trackName", ""),
                            "snippet": (item.get("plainLyrics") or "")[:80]
                        })
        except Exception:
            pass
        return results


class SyncedLyricsProvider(BaseLyricsProvider):
    """
    Musixmatch, Deezer, NetEase ve birden fazla servisi kapsayan çoklu sağlayıcı.
    """
    @property
    def name(self) -> str:
        return "SyncedLyrics(Musixmatch/Deezer)"

    def get_lyrics(self, artist: str, title: str) -> Optional[str]:
        clean_title = re.sub(r'\(.*?\)|\[.*?\]', '', title).strip()
        primary_artist = artist.split(",")[0].strip()
        search_term = f"{primary_artist} {clean_title}"
        
        # Kesin Zaman Aşımı: syncedlyrics ağda takılırsa azami 3.0 saniye sonra kesilir
        import concurrent.futures
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(syncedlyrics.search, search_term)
                raw = future.result(timeout=3.0)
                if raw:
                    cleaned = re.sub(r'\[\d+:\d+(?:\.\d+)?\]', '', raw).strip()
                    if len(cleaned) > 30:
                        return cleaned
        except Exception:
            pass
        return None

    def search_by_phrase(self, phrase: str, lang: str = "all", limit: int = 10) -> List[Dict[str, str]]:
        # Syncedlyrics direkt şarkı ismi arar, phrase için duckduckgo/web fallback'i kullanır
        return []


class WebGeniusFallbackProvider(BaseLyricsProvider):
    """
    Genius & Web Lirik Arşivleri (DuckDuckGo Lite Web Parser).
    """
    @property
    def name(self) -> str:
        return "WebGeniusFallback"

    def get_lyrics(self, artist: str, title: str) -> Optional[str]:
        # Genius API token varsa doğrudan çekebilir, yoksa fallback
        return None

    def search_by_phrase(self, phrase: str, lang: str = "all", limit: int = 10) -> List[Dict[str, str]]:
        suffix = "lyrics" if lang == "en" else "şarkı sözleri"
        query_str = f"{phrase} {suffix}".strip()
        url = 'https://lite.duckduckgo.com/lite/'
        data = urllib.parse.urlencode({'q': query_str}).encode('utf-8')
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        found = []
        seen = set()
        try:
            with urllib.request.urlopen(req, timeout=4) as response:
                html = response.read().decode('utf-8')
                soup = BeautifulSoup(html, 'html.parser')
                snippets = soup.find_all('td', class_='result-snippet')
                links = soup.find_all('a', class_='result-link')

                for link_tag, snip_tag in zip(links, snippets):
                    link_text = link_tag.get_text().strip()
                    snip_text = snip_tag.get_text().strip()

                    title_clean = re.sub(r'\|.*$', '', link_text)
                    title_clean = re.sub(r'(?i)(şarkı sözleri|lyrics|lyric|sözleri)', '', title_clean).strip(' -:\'"')

                    parts = re.split(r'[-–—:]', title_clean, maxsplit=1)
                    if len(parts) == 2:
                        art = parts[0].strip(' "\'')
                        tit = parts[1].strip(' "\'')
                    else:
                        art = ""
                        tit = parts[0].strip(' "\'')

                    key = f"{art}_{tit}".lower()
                    if key not in seen and len(tit) > 1 and "youtube" not in art.lower():
                        seen.add(key)
                        found.append({
                            "artist": art,
                            "title": tit,
                            "snippet": snip_text
                        })
                    if len(found) >= limit:
                        break
        except Exception:
            pass
        return found


class LyricsManager:
    """
    Söz sağlayıcıları zincirleme (Fallback) yönetir:
    1. LRCLIB dener (Hızlı & Ücretsiz)
    2. SyncedLyrics dener (Musixmatch / Deezer)
    3. Web / Genius Fallback dener
    """
    def __init__(self):
        self.providers: List[BaseLyricsProvider] = [
            LRCLIBProvider(),
            SyncedLyricsProvider(),
            WebGeniusFallbackProvider()
        ]

    def get_lyrics(self, artist: str, title: str) -> Optional[str]:
        for provider in self.providers:
            try:
                res = provider.get_lyrics(artist, title)
                if res and len(res) > 30:
                    return res
            except Exception:
                continue
        return None

    def search_by_phrase(self, phrase: str, lang: str = "all", limit: int = 15) -> List[Dict[str, str]]:
        all_hits = []
        seen = set()

        # 1. LRCLIB doğrudan ara
        lrclib_hits = self.providers[0].search_by_phrase(phrase, lang=lang, limit=limit)
        for h in lrclib_hits:
            key = f"{h['artist']}_{h['title']}".lower()
            if key not in seen:
                seen.add(key)
                all_hits.append(h)

        # 2. Web / Genius Fallback ile zenginleştir
        if len(all_hits) < limit:
            web_hits = self.providers[2].search_by_phrase(phrase, lang=lang, limit=limit - len(all_hits))
            for h in web_hits:
                key = f"{h['artist']}_{h['title']}".lower()
                if key not in seen:
                    seen.add(key)
                    all_hits.append(h)

        return all_hits[:limit]
