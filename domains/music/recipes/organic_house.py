"""Organic House genre recipe."""

from domains.music.recipes import ArrangementSection, GenreRecipe

ORGANIC_HOUSE: GenreRecipe = GenreRecipe(
    genre_id="organic_house",
    display_name="Organic House",
    bpm_range=(120, 128),
    typical_bpm=124,
    key_conventions=(
        "A minor",
        "D minor",
        "E minor",
        "G major",
        "C major",
    ),
    time_signature=(4, 4),
    arrangement=(
        ArrangementSection(name="intro", bars=16),
        ArrangementSection(name="buildup", bars=8),
        ArrangementSection(name="drop", bars=32),
        ArrangementSection(name="breakdown", bars=16),
        ArrangementSection(name="drop_2", bars=32),
        ArrangementSection(name="outro", bars=16),
    ),
    mixing_notes=(
        "sidechain pump",
        "sub bass below 60Hz",
        "reverb pre-delay 20-30ms",
        "mono below 150Hz",
    ),
    sound_palette=(
        "bongo",
        "djembe",
        "conga",
        "tabla",
        "organic bass",
        "plucked guitar",
        "flute",
        "breathy pad",
        "vinyl crackle",
    ),
    sub_domain_tags=(
        "genre_analysis",
        "arrangement",
        "mixing",
        "sound_design",
    ),
)
