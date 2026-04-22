"""Unit tests for homekit_climate_plus.util."""
from __future__ import annotations

import pytest

from custom_components.homekit_climate_plus.util import (
    auto_fan_mode_mapping,
    fan_mode_for_percent,
)


class TestAutoFanModeMapping:
    def test_empty_input(self) -> None:
        assert auto_fan_mode_mapping([]) == {}

    def test_single_mode_maps_to_max(self) -> None:
        assert auto_fan_mode_mapping(["Auto"]) == {"Auto": 100}

    def test_two_modes_split_50_100(self) -> None:
        assert auto_fan_mode_mapping(["Low", "High"]) == {"Low": 50, "High": 100}

    def test_three_modes_evenly_spaced(self) -> None:
        # 33, 67, 100
        assert auto_fan_mode_mapping(["a", "b", "c"]) == {"a": 33, "b": 67, "c": 100}

    def test_daikin_seven_mode_example(self) -> None:
        # Reference Daikin BRP069 fan_modes from PRD §13.
        mapping = auto_fan_mode_mapping(
            ["Auto", "Silence", "1", "2", "3", "4", "5"]
        )
        assert mapping == {
            "Auto": 14,
            "Silence": 29,
            "1": 43,
            "2": 57,
            "3": 71,
            "4": 86,
            "5": 100,
        }

    def test_last_mode_always_hits_100(self) -> None:
        for n in range(1, 20):
            modes = [f"m{i}" for i in range(n)]
            assert auto_fan_mode_mapping(modes)[f"m{n - 1}"] == 100

    def test_mapping_preserves_order_and_uniqueness(self) -> None:
        modes = ["Auto", "Silence", "1", "2", "3", "4", "5"]
        mapping = auto_fan_mode_mapping(modes)
        # Keys in insertion order.
        assert list(mapping.keys()) == modes
        # All percents distinct and strictly ascending.
        values = list(mapping.values())
        assert values == sorted(values)
        assert len(set(values)) == len(values)


class TestFanModeForPercent:
    @pytest.fixture
    def daikin_mapping(self) -> dict[str, int]:
        return {
            "Auto": 14,
            "Silence": 29,
            "1": 43,
            "2": 57,
            "3": 71,
            "4": 86,
            "5": 100,
        }

    def test_empty_mapping_returns_none(self) -> None:
        assert fan_mode_for_percent(50, {}) == None  # noqa: E711

    def test_exact_percent_returns_its_mode(
        self, daikin_mapping: dict[str, int]
    ) -> None:
        assert fan_mode_for_percent(14, daikin_mapping) == "Auto"
        assert fan_mode_for_percent(71, daikin_mapping) == "3"
        assert fan_mode_for_percent(100, daikin_mapping) == "5"

    def test_below_min_clamps_to_lowest_mode(
        self, daikin_mapping: dict[str, int]
    ) -> None:
        assert fan_mode_for_percent(0, daikin_mapping) == "Auto"
        assert fan_mode_for_percent(7, daikin_mapping) == "Auto"

    def test_above_max_clamps_to_highest_mode(
        self, daikin_mapping: dict[str, int]
    ) -> None:
        assert fan_mode_for_percent(101, daikin_mapping) == "5"

    def test_midway_rounds_to_closest(
        self, daikin_mapping: dict[str, int]
    ) -> None:
        # 22 is 8 away from Auto(14) and 7 away from Silence(29).
        assert fan_mode_for_percent(22, daikin_mapping) == "Silence"
        # 50 is equidistant from "1"(43) and "2"(57): ties resolve to first.
        assert fan_mode_for_percent(50, daikin_mapping) == "1"

    def test_single_entry_mapping_always_returns_that_mode(self) -> None:
        mapping = {"Only": 100}
        assert fan_mode_for_percent(0, mapping) == "Only"
        assert fan_mode_for_percent(100, mapping) == "Only"
