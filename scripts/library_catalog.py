"""The song library's fixed lists: which modern songs get a description, and the genre/mood/energy values for every song.

Three kinds of value live here, and songs.json labels each one:
  genre_label   the song's real genre. Copied from the Wikipedia infobox (or article intro) where one was found;
                otherwise an estimate. genre_label_source says which.
  genre         the nearest word in data/songs.csv's 16-word vocabulary. It only exists so the Project 3 scorer can
                use it (the optional playlist link). It is a mapping, not a claim about the song.
  mood, energy  estimates (energy 0 to 1). No source exists for them. Proposed by the build session on Nov 17, 2026;
                Danny decided on Nov 18, 2026 to keep them as they are and label them as estimates.
"""
import re


def slugify(text: str) -> str:
    """'St. Louis Blues' -> 'st-louis-blues' (also how lyric titles are matched to PUBLIC_DOMAIN_ATTRS)."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


INFOBOX = "Wikipedia infobox"
INTRO = "Wikipedia article intro"
ESTIMATE = "estimate"

# One entry per song that gets a `description` document. `sections` are the article headings sent to Gemini beside
# the summary, because several summaries say nothing about what the song is about (Fast Car, What Was I Made For?).
# `use_summary` False = the summary is left out (the parody lives only in Jingle Bells' "Parodies and homages").
# `max_paragraphs` keeps only the first N paragraphs of the section text (that section's later paragraphs are about
# other parodies, which would leak into the description).
MODERN = [
    {"id": "changes", "title": "Changes", "artist": "2Pac", "year": 1998,
     "wiki_title": "Changes (Tupac Shakur song)", "sections": ("Overview",), "use_summary": True,
     "genre_label": "Conscious hip-hop", "genre_label_source": INFOBOX,
     "genre": "hip-hop", "mood": "moody", "energy": 0.55, "starter": True},
    {"id": "fast-car", "title": "Fast Car", "artist": "Tracy Chapman", "year": 1988,
     "wiki_title": "Fast Car", "sections": ("Music and lyrics",), "use_summary": True,
     "genre_label": "Folk rock", "genre_label_source": INFOBOX,
     "genre": "folk", "mood": "sad", "energy": 0.45, "starter": True},
    {"id": "jolene", "title": "Jolene", "artist": "Dolly Parton", "year": 1973,
     "wiki_title": "Jolene", "sections": ("Background", "Content"), "use_summary": True,
     "genre_label": "Country", "genre_label_source": INFOBOX,
     "genre": "country", "mood": "sad", "energy": 0.55, "starter": True},
    {"id": "what-was-i-made-for", "title": "What Was I Made For?", "artist": "Billie Eilish", "year": 2023,
     "wiki_title": "What Was I Made For?", "sections": ("Background and release", "Production", "Critical reception"),
     "use_summary": True,
     "genre_label": "Pop", "genre_label_source": INFOBOX,
     "genre": "pop", "mood": "sad", "energy": 0.2, "starter": True},
    {"id": "jingle-bells-batman-parody", "title": "Jingle Bells (the Batman playground parody)", "artist": None,
     "year": None, "wiki_title": "Jingle Bells", "sections": ("Parodies and homages",), "use_summary": False,
     "max_paragraphs": 1,
     "extra": "This is about the playground parody of Jingle Bells, not the original carol. Do not quote or "
              "reproduce any line or title of the parody; describe it in your own words.",
     "genre_label": "Playground parody", "genre_label_source": ESTIMATE,
     "genre": "folk", "mood": "playful", "energy": 0.7, "starter": True},
    # The other four from the prompt's list: drafted only with --all. Their genre labels have not been looked up.
    {"id": "alright", "title": "Alright", "artist": "Kendrick Lamar", "year": 2015,
     "wiki_title": "Alright (Kendrick Lamar song)", "sections": (), "use_summary": True,
     "genre_label": None, "genre_label_source": None,
     "genre": "hip-hop", "mood": "hopeful", "energy": 0.7, "starter": False},
    {"id": "drivers-license", "title": "Drivers License", "artist": "Olivia Rodrigo", "year": 2021,
     "wiki_title": "Drivers License (song)", "sections": (), "use_summary": True,
     "genre_label": None, "genre_label_source": None,
     "genre": "pop", "mood": "sad", "energy": 0.3, "starter": False},
    {"id": "flowers", "title": "Flowers", "artist": "Miley Cyrus", "year": 2023,
     "wiki_title": "Flowers (Miley Cyrus song)", "sections": (), "use_summary": True,
     "genre_label": None, "genre_label_source": None,
     "genre": "pop", "mood": "confident", "energy": 0.75, "starter": False},
    {"id": "not-like-us", "title": "Not Like Us", "artist": "Kendrick Lamar", "year": 2024,
     "wiki_title": "Not Like Us", "sections": (), "use_summary": True,
     "genre_label": None, "genre_label_source": None,
     "genre": "hip-hop", "mood": "confident", "energy": 0.85, "starter": False},
]
STARTER_IDS = [e["id"] for e in MODERN if e["starter"]]


def _pd(label, source, genre, mood, energy):
    return {"genre_label": label, "genre_label_source": source, "genre": genre, "mood": mood, "energy": energy}


# Public-domain lyric songs, keyed by slugified title. A lyric file whose title is not here gets None for every
# value in songs.json so Danny fills it in; nothing is guessed at run time.
PUBLIC_DOMAIN_ATTRS = {
    "take-me-out-to-the-ball-game": _pd("Waltz", INFOBOX, "pop", "playful", 0.7),
    "yes-we-have-no-bananas": _pd("Novelty song", INTRO, "jazz", "playful", 0.7),
    "go-down-moses": _pd("Spiritual", INFOBOX, "folk", "hopeful", 0.45),
    "auld-lang-syne": _pd("Scots song", ESTIMATE, "folk", "nostalgic", 0.35),
    "john-henry": _pd("Folk ballad", ESTIMATE, "folk", "intense", 0.6),
    "happy-birthday-to-you": _pd("Children's song", ESTIMATE, "pop", "happy", 0.6),
    "amazing-grace": _pd("Christian hymn", INFOBOX, "folk", "hopeful", 0.25),
    "swing-low-sweet-chariot": _pd("Spiritual", ESTIMATE, "folk", "hopeful", 0.35),
    "danny-boy": _pd("Folk", INFOBOX, "folk", "sad", 0.25),
    "st-louis-blues": _pd("Blues", ESTIMATE, "jazz", "sad", 0.5),
    "frankie-and-johnny": _pd("Folk ballad", ESTIMATE, "folk", "moody", 0.5),
    "jingle-bells": _pd("Christmas song", ESTIMATE, "pop", "happy", 0.7),
    "singin-in-the-rain": _pd("Show tune", ESTIMATE, "jazz", "happy", 0.65),
    "georgia-on-my-mind": _pd("Jazz standard", ESTIMATE, "jazz", "nostalgic", 0.3),
}
