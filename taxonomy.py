# Kategori, Tür ve Dil Listeleri (Geniş Yelpaze)

LANGUAGES = [
    {"code": "all", "name": "Tüm Diller (Global)"},
    {"code": "tr", "name": "Türkçe", "market": "TR", "suffix": "Türkçe şarkı sözleri"},
    {"code": "en", "name": "İngilizce (English)", "market": "US", "suffix": "lyrics"},
    {"code": "es", "name": "İspanyolca (Español)", "market": "ES", "suffix": "letra"},
    {"code": "de", "name": "Almanca (Deutsch)", "market": "DE", "suffix": "songtext"},
    {"code": "fr", "name": "Fransızca (Français)", "market": "FR", "suffix": "paroles"},
    {"code": "it", "name": "İtalyanca (Italiano)", "market": "IT", "suffix": "testo"},
    {"code": "ru", "name": "Rusça (Русский)", "market": "RU", "suffix": "слова песни"},
    {"code": "ko", "name": "Korece (K-Pop)", "market": "KR", "suffix": "korean lyrics"},
    {"code": "ja", "name": "Japonca (J-Pop)", "market": "JP", "suffix": "japanese lyrics"},
    {"code": "ar", "name": "Arapça (العربية)", "market": "EG", "suffix": "كلمات أغنية"}
]

CATEGORIES = [
    {"id": "all", "name": "✨ Tüm Kategoriler", "icon": "fa-globe"},
    {"id": "hiphop_rap", "name": "🎤 Hip-Hop & Rap", "icon": "fa-microphone-lines", "genres": ["hip-hop", "rap", "trap", "drill", "underground-hip-hop", "old-school-hip-hop"]},
    {"id": "rock_metal", "name": "🎸 Rock & Metal", "icon": "fa-guitar", "genres": ["rock", "alt-rock", "hard-rock", "punk-rock", "metal", "heavy-metal", "indie-rock", "grunge"]},
    {"id": "pop", "name": "🌟 Pop Müzik", "icon": "fa-star", "genres": ["pop", "synth-pop", "indie-pop", "dance-pop", "electropop", "k-pop", "j-pop"]},
    {"id": "electronic_dance", "name": "⚡ Elektronik & Dans (EDM)", "icon": "fa-bolt", "genres": ["electronic", "edm", "house", "deep-house", "techno", "minimal-techno", "drum-and-bass", "dubstep", "trance"]},
    {"id": "rnb_soul", "name": "🎷 R&B & Soul", "icon": "fa-compact-disc", "genres": ["r-n-b", "soul", "neo-soul", "funk", "groove", "motown"]},
    {"id": "acoustic_chill", "name": "☕ Akustik, Lo-Fi & Chill", "icon": "fa-mug-hot", "genres": ["acoustic", "chill", "lo-fi", "ambient", "singer-songwriter", "folk", "piano"]},
    {"id": "jazz_blues", "name": "🎺 Caz & Blues", "icon": "fa-music", "genres": ["jazz", "blues", "bossanova", "bebop", "vocal-jazz"]},
    {"id": "latin_reggae", "name": "🌴 Latin & Reggae", "icon": "fa-drum", "genres": ["latin", "latino", "reggae", "reggaeton", "salsa", "samba", "dancehall", "afrobeat"]},
    {"id": "classical_soundtrack", "name": "🎻 Klasik & Film Müzikleri", "icon": "fa-film", "genres": ["classical", "soundtracks", "opera", "cinematic", "orchestral", "piano"]},
    {"id": "traditional_folk", "name": "🪕 Geleneksel & Etnik", "icon": "fa-earth-americas", "genres": ["folk", "world-music", "anatolian-rock", "turku", "flamenco", "tango"]}
]

ALL_GENRES = [
    "Tümü",
    # Rap & Hip-Hop
    "hip-hop", "rap", "trap", "drill", "underground-hip-hop", "boom-bap",
    # Rock & Metal
    "rock", "alternative", "alt-rock", "indie-rock", "hard-rock", "punk", "punk-rock", "grunge", "metal", "heavy-metal", "death-metal", "black-metal", "metalcore", "psychedelic-rock", "post-punk",
    # Pop
    "pop", "synth-pop", "indie-pop", "dance-pop", "electropop", "power-pop", "k-pop", "j-pop",
    # Elektronik
    "electronic", "edm", "house", "deep-house", "tech-house", "techno", "minimal-techno", "acid-techno", "drum-and-bass", "dubstep", "trance", "progressive-house", "garage", "ambient", "idm",
    # R&B & Soul
    "r-n-b", "soul", "neo-soul", "funk", "disco", "groove", "gospel",
    # Akustik & Lo-Fi
    "acoustic", "lo-fi", "chill", "folk", "singer-songwriter", "indie", "bluegrass", "country",
    # Caz & Blues
    "jazz", "blues", "bossanova",
    # Latin & Dünya
    "latin", "latino", "reggaeton", "reggae", "dancehall", "afrobeat", "salsa", "samba", "bossa-nova", "flamenco", "tango",
    # Türkçe Özel Türler
    "turkish", "turkish-pop", "turkish-rock", "turkish-rap", "turkish-trap", "turkish-indie", "anatolian-rock", "turku",
    # Klasik & Enstrümantal
    "classical", "soundtracks", "piano", "new-age"
]
