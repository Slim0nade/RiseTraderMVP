"""
Unit tests for deterministic grid search utilities.

These tests verify:
- T024: generate_grid_combinations() produces all combinations
- T025: Deterministic ordering - same input always produces same output
- T026: Grid size validation (max 10,000 combinations)
"""

import pytest
from src.utils.grid_search import (
    calculate_grid_size,
    validate_grid_size,
    generate_grid_combinations,
    get_combination_at_index,
    chunk_grid,
    GridSizeExceededError,
    MAX_COMBINATIONS,
)


class TestCalculateGridSize:
    """Tests for calculate_grid_size function."""

    def test_single_param_grid(self):
        """Test grid size calculation with single parameter."""
        grid = {"fast_period": [5, 10, 15, 20, 25]}
        assert calculate_grid_size(grid) == 5

    def test_multiple_param_grid(self):
        """Test grid size calculation with multiple parameters."""
        grid = {
            "fast_period": [5, 10, 15],
            "slow_period": [20, 30, 40, 50],
        }
        assert calculate_grid_size(grid) == 12  # 3 x 4

    def test_large_grid(self):
        """Test grid size calculation for larger grids."""
        grid = {
            "param1": list(range(10)),
            "param2": list(range(10)),
            "param3": list(range(10)),
        }
        assert calculate_grid_size(grid) == 1000  # 10 x 10 x 10

    def test_empty_grid(self):
        """Test grid size calculation for empty grid raises ValueError."""
        grid = {}
        with pytest.raises(ValueError) as exc_info:
            calculate_grid_size(grid)
        assert "empty" in str(exc_info.value).lower()

    def test_single_value_params(self):
        """Test grid with parameters having single values."""
        grid = {
            "fast_period": [10],
            "slow_period": [30],
        }
        assert calculate_grid_size(grid) == 1


class TestValidateGridSize:
    """Tests for validate_grid_size function (T026)."""

    def test_valid_grid_under_limit(self):
        """Test that valid grids under limit pass validation."""
        grid = {"fast_period": [5, 10], "slow_period": [20, 30]}
        result = validate_grid_size(grid)
        assert result == 4

    def test_grid_at_limit(self):
        """Test that grid exactly at MAX_COMBINATIONS passes."""
        # Create grid with exactly MAX_COMBINATIONS
        grid = {"param": list(range(MAX_COMBINATIONS))}
        result = validate_grid_size(grid)
        assert result == MAX_COMBINATIONS

    def test_grid_exceeds_limit(self):
        """Test that grid exceeding MAX_COMBINATIONS raises error."""
        # Create grid exceeding MAX_COMBINATIONS (10,000)
        grid = {
            "param1": list(range(101)),
            "param2": list(range(100)),
        }  # 101 * 100 = 10,100 > 10,000

        with pytest.raises(GridSizeExceededError) as exc_info:
            validate_grid_size(grid)

        assert "exceeds maximum" in str(exc_info.value)
        # Error message uses comma formatting: "10,000"
        assert "10,000" in str(exc_info.value) or str(MAX_COMBINATIONS) in str(exc_info.value)


class TestGenerateGridCombinations:
    """Tests for generate_grid_combinations function (T024)."""

    def test_generates_all_combinations(self):
        """Test that all combinations are generated."""
        grid = {
            "fast_period": [5, 10],
            "slow_period": [20, 30],
        }
        combinations = list(generate_grid_combinations(grid))

        assert len(combinations) == 4
        expected = [
            {"fast_period": 5, "slow_period": 20},
            {"fast_period": 5, "slow_period": 30},
            {"fast_period": 10, "slow_period": 20},
            {"fast_period": 10, "slow_period": 30},
        ]
        assert combinations == expected

    def test_single_param(self):
        """Test generation with single parameter."""
        grid = {"fast_period": [5, 10, 15]}
        combinations = list(generate_grid_combinations(grid))

        assert len(combinations) == 3
        assert combinations == [
            {"fast_period": 5},
            {"fast_period": 10},
            {"fast_period": 15},
        ]

    def test_three_params(self):
        """Test generation with three parameters."""
        grid = {
            "a": [1, 2],
            "b": [10, 20],
            "c": [100, 200],
        }
        combinations = list(generate_grid_combinations(grid))

        assert len(combinations) == 8  # 2 x 2 x 2
        # Verify first and last combinations
        assert combinations[0] == {"a": 1, "b": 10, "c": 100}
        assert combinations[-1] == {"a": 2, "b": 20, "c": 200}

    def test_empty_grid(self):
        """Test generation with empty grid raises ValueError."""
        grid = {}
        with pytest.raises(ValueError) as exc_info:
            list(generate_grid_combinations(grid))
        assert "empty" in str(exc_info.value).lower()

    def test_validation_flag(self):
        """Test that validate flag works correctly."""
        # Create large grid that exceeds limit
        grid = {
            "param1": list(range(101)),
            "param2": list(range(101)),
        }

        # With validation disabled, should work (but we don't iterate)
        gen = generate_grid_combinations(grid, validate=False)
        assert gen is not None

        # With validation enabled (default), should raise
        with pytest.raises(GridSizeExceededError):
            list(generate_grid_combinations(grid, validate=True))


class TestDeterministicOrdering:
    """Tests for deterministic result ordering (T025)."""

    def test_same_input_same_output(self):
        """Test that same input always produces same output order."""
        grid = {
            "fast_period": [5, 10, 15],
            "slow_period": [20, 30, 40],
            "rsi_period": [7, 14],
        }

        # Generate combinations multiple times
        run1 = list(generate_grid_combinations(grid))
        run2 = list(generate_grid_combinations(grid))
        run3 = list(generate_grid_combinations(grid))

        # All runs should produce identical results
        assert run1 == run2
        assert run2 == run3

    def test_consistent_ordering_across_sizes(self):
        """Test that ordering is consistent regardless of grid size."""
        small_grid = {"a": [1, 2], "b": [10, 20]}
        large_grid = {"a": [1, 2, 3], "b": [10, 20, 30]}

        small_combos = list(generate_grid_combinations(small_grid))
        large_combos = list(generate_grid_combinations(large_grid))

        # The first combinations of large grid should match small grid pattern
        assert small_combos[0]["a"] == large_combos[0]["a"]
        assert small_combos[0]["b"] == large_combos[0]["b"]


class TestGetCombinationAtIndex:
    """Tests for get_combination_at_index function."""

    def test_get_specific_index(self):
        """Test retrieving combination at specific index."""
        grid = {
            "fast_period": [5, 10],
            "slow_period": [20, 30, 40],
        }

        # Index 0 should be first combination
        combo_0 = get_combination_at_index(grid, 0)
        assert combo_0 == {"fast_period": 5, "slow_period": 20}

        # Index 1
        combo_1 = get_combination_at_index(grid, 1)
        assert combo_1 == {"fast_period": 5, "slow_period": 30}

        # Last index
        combo_5 = get_combination_at_index(grid, 5)
        assert combo_5 == {"fast_period": 10, "slow_period": 40}

    def test_out_of_range_index(self):
        """Test that out of range index raises error."""
        grid = {"a": [1, 2]}

        with pytest.raises(IndexError):
            get_combination_at_index(grid, 10)

    def test_negative_index(self):
        """Test that negative index raises error."""
        grid = {"a": [1, 2]}

        with pytest.raises(IndexError):
            get_combination_at_index(grid, -1)


class TestChunkGrid:
    """Tests for chunk_grid function."""

    def test_chunk_into_parts(self):
        """Test chunking grid into specified chunk size."""
        grid = {
            "fast_period": [5, 10],
            "slow_period": [20, 30, 40],
        }  # 6 combinations

        # Use chunk_size=3 to get 2 chunks of 3 combinations each
        chunks = chunk_grid(grid, chunk_size=3)

        assert len(chunks) == 2
        # Each chunk should have combinations, total should be 6
        total_combos = sum(len(chunk) for chunk in chunks)
        assert total_combos == 6

    def test_single_chunk(self):
        """Test chunking with large chunk_size returns single chunk."""
        grid = {"a": [1, 2, 3]}
        # chunk_size larger than grid means single chunk
        chunks = chunk_grid(grid, chunk_size=100)

        assert len(chunks) == 1
        assert chunks[0] == list(generate_grid_combinations(grid))

    def test_more_chunks_than_combinations(self):
        """Test with chunk_size=1 creates many small chunks."""
        grid = {"a": [1, 2]}  # 2 combinations
        chunks = chunk_grid(grid, chunk_size=1)

        # Should return 2 chunks, each with 1 combination
        assert len(chunks) == 2
        assert all(len(chunk) == 1 for chunk in chunks)


class TestGridSizeExceededError:
    """Tests for GridSizeExceededError exception."""

    def test_error_message_includes_size(self):
        """Test that error message includes the grid size and limit."""
        error = GridSizeExceededError(15000, 10000)
        message = str(error)

        assert "15000" in message or "15,000" in message
        assert "10000" in message or "10,000" in message

    def test_error_attributes(self):
        """Test that error has correct attributes."""
        error = GridSizeExceededError(15000, 10000)

        assert error.size == 15000
        assert error.max_size == 10000
