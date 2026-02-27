"""Genre recipe data structures for the music domain.

Provides ``ArrangementSection`` and ``GenreRecipe`` frozen dataclasses that
describe the structural and production characteristics of a music genre.
"""

from __future__ import annotations

from dataclasses import dataclass

from domains.music.sub_domains import MUSIC_SUB_DOMAINS


@dataclass(frozen=True)
class ArrangementSection:
    """A single named section within a genre arrangement template.

    Attributes
    ----------
    name:
        Human-readable section label (e.g. "intro", "drop", "breakdown").
    bars:
        Typical length of the section in bars.
    """

    name: str
    bars: int

    def __post_init__(self) -> None:
        """Validate name is non-empty and bars is positive."""
        if not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if self.bars <= 0:
            raise ValueError(f"bars must be positive, got {self.bars}")


@dataclass(frozen=True)
class GenreRecipe:
    """Production template for a specific music genre.

    Encodes typical BPM range, key conventions, arrangement structure,
    mixing guidance, and sound palette as immutable configuration.

    Attributes
    ----------
    genre_id:
        Machine-readable slug (e.g. "organic_house").
    display_name:
        Human-readable genre name (e.g. "Organic House").
    bpm_range:
        (min_bpm, max_bpm) inclusive range.
    typical_bpm:
        Most common BPM within the range.
    key_conventions:
        Ordered tuple of commonly used keys/modes for this genre.
    time_signature:
        (numerator, denominator) e.g. (4, 4).
    arrangement:
        Ordered tuple of ``ArrangementSection`` instances describing the
        typical song structure.
    mixing_notes:
        Production/mixing tips specific to this genre.
    sound_palette:
        Characteristic sounds and instruments used in this genre.
    sub_domain_tags:
        Music sub-domains this recipe is relevant to.
    """

    genre_id: str
    display_name: str
    bpm_range: tuple[int, int]
    typical_bpm: int
    key_conventions: tuple[str, ...]
    time_signature: tuple[int, int]
    arrangement: tuple[ArrangementSection, ...]
    mixing_notes: tuple[str, ...]
    sound_palette: tuple[str, ...]
    sub_domain_tags: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate bpm_range, typical_bpm, and sub_domain_tags."""
        if self.bpm_range[0] >= self.bpm_range[1]:
            raise ValueError(f"bpm_range[0] must be less than bpm_range[1], got {self.bpm_range}")
        if not (self.bpm_range[0] <= self.typical_bpm <= self.bpm_range[1]):
            raise ValueError(
                f"typical_bpm {self.typical_bpm} must be within bpm_range {self.bpm_range}"
            )
        for tag in self.sub_domain_tags:
            if tag not in MUSIC_SUB_DOMAINS:
                raise ValueError(f"sub_domain_tag {tag!r} must be one of {MUSIC_SUB_DOMAINS}")
