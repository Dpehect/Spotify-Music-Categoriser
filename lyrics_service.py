import re
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
import syncedlyrics

from taxonomy import LANGUAGES

_LYRICS_CACHE = {}

def get_song_lyrics(track_name: str, artist_name: str) -> str:
    clean_name = re.sub(r'\(.*?\)|\[.*?\]', '', track_name).strip()
    primary_artist = artist_name.split(',')[0].strip()
    cache_key = f"{primary_artist} - {clean_name}".lower()
    
    if cache_key in _LYRICS_CACHE:
        return _LYRICS_CACHE[cache_key]

    search_term = f"{primary_artist} {clean_name}"
    
    try:
        raw_lrc = syncedlyrics.search(search_term)
        if raw_lrc:
            cleaned_lines = []
            for line in raw_lrc.splitlines():
                clean_line = re.sub(r'\[\d+:\d+(?:\.\d+)?\]', '', line).strip()
                if clean_line:
                    cleaned_lines.append(clean_line)
            lyrics = "\n".join(cleaned_lines)
            if len(lyrics) > 30:
                _LYRICS_CACHE[cache_key] = lyrics
                return lyrics
    except Exception:
        pass

    return ""


def search_songs_by_lyrics_web(lyrics_phrase: str, lang_code: str = "all", limit: int = 15):
    """
    Şarkı sözü (lyrics) aramasını seçilen dile göre optimize eder.
    """
    if not lyrics_phrase:
        return []

    # Dile özel arama eki
    suffix = "şarkı sözleri lyrics"
    for l in LANGUAGES:
        if l["code"] == lang_code and lang_code != "all":
            suffix = l.get("suffix", "lyrics")
            break

    query_str = f"{lyrics_phrase} {suffix}".strip()
    url = 'https://lite.duckduckgo.com/lite/'
    data = urllib.parse.urlencode({'q': query_str}).encode('utf-8')
    req = urllib.request.Request(
        url, 
        data=data, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )

    found_songs = []
    seen = set()

    try:
        with urllib.request.urlopen(req, timeout=4) as response:
            html = response.read().decode('utf-8')
            soup = BeautifulSoup(html, 'html.parser')
            snippets = soup.find_all('td', class_='result-snippet')
            links = soup.find_all('a', class_='result-link')

            for link_tag, snip_tag in zip(links, snippets):
                link_text = link_tag.get_text().strip()
                snippet_text = snip_tag.get_text().strip()

                title_clean = re.sub(r'\|.*$', '', link_text)
                title_clean = re.sub(r'(?i)(şarkı sözleri|lyrics|lyric|sözleri|songtext|letra|paroles|testo)', '', title_clean).strip(' -:\'"')

                parts = re.split(r'[-–—:]', title_clean, maxsplit=1)
                if len(parts) == 2:
                    artist = parts[0].strip(' "\'')
                    title = parts[1].strip(' "\'')
                else:
                    artist = ""
                    title = parts[0].strip(' "\'')

                title = re.sub(r'["\']', '', title).strip()
                artist = re.sub(r'["\']', '', artist).strip()

                key = f"{artist}_{title}".lower()
                if key not in seen and len(title) > 1 and "youtube" not in artist.lower():
                    seen.add(key)
                    found_songs.append({
                        "artist": artist,
                        "title": title,
                        "snippet": snippet_text
                    })

                if len(found_songs) >= limit:
                    break
    except Exception as e:
        print(f"Lyrics web search error: {e}")

    return found_songs
