"""Deep House genre recipe."""

from domains.music.recipes import ArrangementSection, GenreRecipe

DEEP_HOUSE: GenreRecipe = GenreRecipe(
    genre_id="deep_house",
    display_name="Deep House",
    bpm_range=(118, 125),
    typical_bpm=122,
    key_conventions=(
        "F minor",
        "Bb minor",
        "Eb major",
        "Ab major",
        "C minor",
    ),
    time_signature=(4, 4),
    arrangement=(
        ArrangementSection(name="intro", bars=16),
        ArrangementSection(name="groove", bars=16),
        ArrangementSection(name="break", bars=8),
        ArrangementSection(name="groove_2", bars=32),
        ArrangementSection(name="break_2", bars=8),
        ArrangementSection(name="outro", bars=16),
    ),
    mixing_notes=(
        "warm low-end",
        "subtle sidechain",
        "lush reverb",
        "intimate stereo field",
        "vintage saturation",
    ),
    sound_palette=(
        "warm sub bass",
        "house piano",
        "soulful vocal sample",
        "Rhodes",
        "shaker",
        "soft kick",
        "rimshot",
    ),
    sub_domain_tags=(
        "genre_analysis",
        "arrangement",
        "mixing",
        "sound_design",
    ),
)
