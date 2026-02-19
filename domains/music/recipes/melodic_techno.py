"""Melodic Techno genre recipe."""

from domains.music.recipes import ArrangementSection, GenreRecipe

MELODIC_TECHNO: GenreRecipe = GenreRecipe(
    genre_id="melodic_techno",
    display_name="Melodic Techno",
    bpm_range=(130, 140),
    typical_bpm=135,
    key_conventions=(
        "A minor",
        "D minor",
        "F# minor",
        "E minor",
        "G minor",
    ),
    time_signature=(4, 4),
    arrangement=(
        ArrangementSection(name="intro", bars=16),
        ArrangementSection(name="tension_build", bars=16),
        ArrangementSection(name="drop", bars=32),
        ArrangementSection(name="atmospheric", bars=16),
        ArrangementSection(name="drop_2", bars=32),
        ArrangementSection(name="outro", bars=16),
    ),
    mixing_notes=(
        "heavy compression on drums",
        "pumping sidechain",
        "dark reverb",
        "layered synths with mid cut",
    ),
    sound_palette=(
        "dark synth bass",
        "metallic percussion",
        "atmospheric pad",
        "hypnotic arp",
        "industrial kick",
        "shaker",
    ),
    sub_domain_tags=(
        "genre_analysis",
        "arrangement",
        "mixing",
        "sound_design",
    ),
)
