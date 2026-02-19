"""Tests for domains/music/recipes/ genre instances."""

from __future__ import annotations

import pytest

from domains.music.recipes import ArrangementSection, GenreRecipe
from domains.music.recipes.deep_house import DEEP_HOUSE
from domains.music.recipes.melodic_techno import MELODIC_TECHNO
from domains.music.recipes.organic_house import ORGANIC_HOUSE
from domains.music.recipes.progressive_house import PROGRESSIVE_HOUSE
from domains.music.sub_domains import MUSIC_SUB_DOMAINS

ALL_RECIPES: tuple[GenreRecipe, ...] = (
    ORGANIC_HOUSE,
    PROGRESSIVE_HOUSE,
    MELODIC_TECHNO,
    DEEP_HOUSE,
)


class TestArrangementSection:
    """Tests for the ArrangementSection frozen dataclass."""

    def test_valid_construction(self) -> None:
        section = ArrangementSection(name="intro", bars=16)
        assert section.name == "intro"
        assert section.bars == 16

    def test_is_frozen(self) -> None:
        section = ArrangementSection(name="drop", bars=32)
        with pytest.raises((AttributeError, TypeError)):
            section.bars = 64  # type: ignore[misc]

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            ArrangementSection(name="   ", bars=16)

    def test_zero_bars_raises(self) -> None:
        with pytest.raises(ValueError, match="bars must be positive"):
            ArrangementSection(name="intro", bars=0)

    def test_negative_bars_raises(self) -> None:
        with pytest.raises(ValueError, match="bars must be positive"):
            ArrangementSection(name="intro", bars=-4)


class TestGenreRecipeValidation:
    """Tests for GenreRecipe validation logic."""

    def test_bpm_range_inverted_raises(self) -> None:
        with pytest.raises(ValueError, match="bpm_range"):
            GenreRecipe(
                genre_id="test",
                display_name="Test",
                bpm_range=(130, 120),
                typical_bpm=125,
                key_conventions=("A minor",),
                time_signature=(4, 4),
                arrangement=(ArrangementSection("intro", 16),),
                mixing_notes=("note",),
                sound_palette=("kick",),
                sub_domain_tags=("genre_analysis",),
            )

    def test_typical_bpm_outside_range_raises(self) -> None:
        with pytest.raises(ValueError, match="typical_bpm"):
            GenreRecipe(
                genre_id="test",
                display_name="Test",
                bpm_range=(120, 130),
                typical_bpm=135,
                key_conventions=("A minor",),
                time_signature=(4, 4),
                arrangement=(ArrangementSection("intro", 16),),
                mixing_notes=("note",),
                sound_palette=("kick",),
                sub_domain_tags=("genre_analysis",),
            )

    def test_invalid_sub_domain_tag_raises(self) -> None:
        with pytest.raises(ValueError, match="sub_domain_tag"):
            GenreRecipe(
                genre_id="test",
                display_name="Test",
                bpm_range=(120, 130),
                typical_bpm=125,
                key_conventions=("A minor",),
                time_signature=(4, 4),
                arrangement=(ArrangementSection("intro", 16),),
                mixing_notes=("note",),
                sound_palette=("kick",),
                sub_domain_tags=("invalid_domain",),
            )

    def test_genre_recipe_is_frozen(self) -> None:
        with pytest.raises((AttributeError, TypeError)):
            ORGANIC_HOUSE.typical_bpm = 120  # type: ignore[misc]


class TestAllRecipesImportable:
    """Tests that all four recipes are importable and well-formed."""

    def test_organic_house_importable(self) -> None:
        assert ORGANIC_HOUSE.genre_id == "organic_house"

    def test_progressive_house_importable(self) -> None:
        assert PROGRESSIVE_HOUSE.genre_id == "progressive_house"

    def test_melodic_techno_importable(self) -> None:
        assert MELODIC_TECHNO.genre_id == "melodic_techno"

    def test_deep_house_importable(self) -> None:
        assert DEEP_HOUSE.genre_id == "deep_house"

    def test_all_bpm_ranges_valid(self) -> None:
        for recipe in ALL_RECIPES:
            assert (
                recipe.bpm_range[0] < recipe.bpm_range[1]
            ), f"{recipe.genre_id}: bpm_range invalid"

    def test_all_typical_bpm_within_range(self) -> None:
        for recipe in ALL_RECIPES:
            lo, hi = recipe.bpm_range
            assert lo <= recipe.typical_bpm <= hi, f"{recipe.genre_id}: typical_bpm out of range"

    def test_all_arrangements_non_empty(self) -> None:
        for recipe in ALL_RECIPES:
            assert len(recipe.arrangement) > 0, f"{recipe.genre_id}: arrangement is empty"

    def test_all_sub_domain_tags_valid(self) -> None:
        for recipe in ALL_RECIPES:
            for tag in recipe.sub_domain_tags:
                assert (
                    tag in MUSIC_SUB_DOMAINS
                ), f"{recipe.genre_id}: invalid sub_domain_tag {tag!r}"

    def test_all_sound_palettes_non_empty(self) -> None:
        for recipe in ALL_RECIPES:
            assert len(recipe.sound_palette) > 0

    def test_all_mixing_notes_non_empty(self) -> None:
        for recipe in ALL_RECIPES:
            assert len(recipe.mixing_notes) > 0

    def test_all_key_conventions_non_empty(self) -> None:
        for recipe in ALL_RECIPES:
            assert len(recipe.key_conventions) > 0


class TestSpecificRecipeValues:
    """Tests for specific known values in each recipe."""

    def test_organic_house_typical_bpm(self) -> None:
        assert ORGANIC_HOUSE.typical_bpm == 124

    def test_organic_house_bpm_range(self) -> None:
        assert ORGANIC_HOUSE.bpm_range == (120, 128)

    def test_deep_house_bpm_range(self) -> None:
        assert DEEP_HOUSE.bpm_range == (118, 125)

    def test_deep_house_typical_bpm(self) -> None:
        assert DEEP_HOUSE.typical_bpm == 122

    def test_progressive_house_typical_bpm(self) -> None:
        assert PROGRESSIVE_HOUSE.typical_bpm == 128

    def test_melodic_techno_typical_bpm(self) -> None:
        assert MELODIC_TECHNO.typical_bpm == 135

    def test_melodic_techno_bpm_range(self) -> None:
        assert MELODIC_TECHNO.bpm_range == (130, 140)

    def test_organic_house_has_breakdown_section(self) -> None:
        section_names = [s.name for s in ORGANIC_HOUSE.arrangement]
        assert "breakdown" in section_names

    def test_deep_house_has_groove_section(self) -> None:
        section_names = [s.name for s in DEEP_HOUSE.arrangement]
        assert "groove" in section_names

    def test_melodic_techno_has_atmospheric_section(self) -> None:
        section_names = [s.name for s in MELODIC_TECHNO.arrangement]
        assert "atmospheric" in section_names

    def test_progressive_house_display_name(self) -> None:
        assert PROGRESSIVE_HOUSE.display_name == "Progressive House"

    def test_all_time_signatures_are_4_4(self) -> None:
        for recipe in ALL_RECIPES:
            assert recipe.time_signature == (4, 4)
