"""Progressive House genre recipe."""

from domains.music.recipes import ArrangementSection, GenreRecipe

PROGRESSIVE_HOUSE: GenreRecipe = GenreRecipe(
    genre_id="progressive_house",
    display_name="Progressive House",
    bpm_range=(126, 132),
    typical_bpm=128,
    key_conventions=(
        "A minor",
        "F# minor",
        "B minor",
        "D major",
        "G major",
    ),
    time_signature=(4, 4),
    arrangement=(
        ArrangementSection(name="intro", bars=16),
        ArrangementSection(name="buildup", bars=16),
        ArrangementSection(name="drop", bars=32),
        ArrangementSection(name="breakdown", bars=16),
        ArrangementSection(name="drop_2", bars=32),
        ArrangementSection(name="outro", bars=16),
    ),
    mixing_notes=(
        "wide stereo on leads",
        "punchy kick/bass relationship",
        "heavy sidechain",
        "big reverb on breakdown",
    ),
    sound_palette=(
        "supersaw lead",
        "pluck",
        "driving kick",
        "rolling bassline",
        "riser",
        "ethereal pad",
        "vocal chop",
    ),
    sub_domain_tags=(
        "genre_analysis",
        "arrangement",
        "mixing",
        "sound_design",
    ),
)
