"""
Grid search utilities for deterministic parameter optimization.

This module provides functions to generate all parameter combinations
from a parameter grid using itertools.product, ensuring reproducible
and deterministic optimization results.
"""

from itertools import product
from typing import Any, Dict, List

import structlog

logger = structlog.get_logger(__name__)

# Maximum allowed combinations to prevent OOM/timeout
MAX_COMBINATIONS = 10_000


class GridSizeExceededError(ValueError):
    """Raised when the parameter grid exceeds maximum allowed combinations."""

    def __init__(self, size: int, max_size: int):
        self.size = size
        self.max_size = max_size
        super().__init__(
            f"Grid size {size:,} exceeds maximum allowed {max_size:,} combinations"
        )


def calculate_grid_size(param_grid: Dict[str, List[Any]]) -> int:
    """
    Calculate total number of combinations in a parameter grid.

    Args:
        param_grid: Dictionary mapping parameter names to lists of values.
                   Example: {"fast_period": [5, 10, 15], "slow_period": [20, 30]}

    Returns:
        Total number of combinations (product of all list lengths).

    Raises:
        ValueError: If param_grid is empty or contains empty lists.
    """
    if not param_grid:
        raise ValueError("Parameter grid cannot be empty")

    size = 1
    for param_name, values in param_grid.items():
        if not isinstance(values, (list, tuple)):
            raise ValueError(f"Parameter '{param_name}' must be a list or tuple of values")
        if len(values) == 0:
            raise ValueError(f"Parameter '{param_name}' cannot have empty value list")
        size *= len(values)

    return size


def validate_grid_size(param_grid: Dict[str, List[Any]], max_combinations: int = MAX_COMBINATIONS) -> int:
    """
    Validate that a parameter grid does not exceed maximum combinations.

    Args:
        param_grid: Dictionary mapping parameter names to lists of values.
        max_combinations: Maximum allowed combinations (default 10,000).

    Returns:
        The grid size if valid.

    Raises:
        GridSizeExceededError: If grid size exceeds max_combinations.
    """
    size = calculate_grid_size(param_grid)

    if size > max_combinations:
        raise GridSizeExceededError(size, max_combinations)

    logger.debug("grid_size_validated", size=size, max_allowed=max_combinations)
    return size


def generate_grid_combinations(param_grid: Dict[str, List[Any]], validate: bool = True) -> List[Dict[str, Any]]:
    """
    Generate all parameter combinations from a grid deterministically.

    Uses itertools.product to create the Cartesian product of all parameter
    values, ensuring a consistent, reproducible order every time.

    Args:
        param_grid: Dictionary mapping parameter names to lists of values.
                   Example: {
                       "fast_period": [5, 10, 15],
                       "slow_period": [20, 30, 40],
                       "threshold": [0.5, 0.7]
                   }
                   This would generate 3 × 3 × 2 = 18 combinations.
        validate: Whether to validate grid size (default True).

    Returns:
        List of dictionaries, each containing one parameter combination.
        Order is deterministic: iterates through the last parameter fastest.

        Example output for above input:
        [
            {"fast_period": 5, "slow_period": 20, "threshold": 0.5},
            {"fast_period": 5, "slow_period": 20, "threshold": 0.7},
            {"fast_period": 5, "slow_period": 30, "threshold": 0.5},
            ...
        ]

    Raises:
        GridSizeExceededError: If grid exceeds MAX_COMBINATIONS (when validate=True).
        ValueError: If param_grid is invalid.
    """
    if not param_grid:
        raise ValueError("Parameter grid cannot be empty")

    # Validate grid size before generating
    if validate:
        validate_grid_size(param_grid)

    # Sort keys for consistent ordering across Python versions
    keys = sorted(param_grid.keys())
    values = [param_grid[k] for k in keys]

    # Generate all combinations using itertools.product
    combinations = []
    for combo in product(*values):
        combinations.append(dict(zip(keys, combo)))

    logger.info(
        "grid_combinations_generated",
        total_combinations=len(combinations),
        parameters=list(keys),
    )

    return combinations


def get_combination_at_index(param_grid: Dict[str, List[Any]], index: int) -> Dict[str, Any]:
    """
    Get a specific combination by index without generating all combinations.

    Useful for resuming optimization from a specific point.

    Args:
        param_grid: Dictionary mapping parameter names to lists of values.
        index: Zero-based index of the combination to retrieve.

    Returns:
        Dictionary containing the parameter combination at the given index.

    Raises:
        IndexError: If index is out of range.
        ValueError: If param_grid is invalid.
    """
    if not param_grid:
        raise ValueError("Parameter grid cannot be empty")

    total = calculate_grid_size(param_grid)
    if index < 0 or index >= total:
        raise IndexError(f"Index {index} out of range for grid size {total}")

    # Sort keys for consistent ordering
    keys = sorted(param_grid.keys())
    values = [param_grid[k] for k in keys]

    # Calculate the combination at index using modular arithmetic
    combination = {}
    remaining_index = index

    for i in range(len(keys) - 1, -1, -1):
        param_values = values[i]
        value_index = remaining_index % len(param_values)
        combination[keys[i]] = param_values[value_index]
        remaining_index //= len(param_values)

    return combination


def chunk_grid(param_grid: Dict[str, List[Any]], chunk_size: int = 100) -> List[List[Dict[str, Any]]]:
    """
    Split a parameter grid into chunks for batched processing.

    Args:
        param_grid: Dictionary mapping parameter names to lists of values.
        chunk_size: Maximum combinations per chunk.

    Returns:
        List of chunks, where each chunk is a list of parameter combinations.
    """
    all_combinations = generate_grid_combinations(param_grid, validate=True)

    chunks = []
    for i in range(0, len(all_combinations), chunk_size):
        chunks.append(all_combinations[i:i + chunk_size])

    logger.debug(
        "grid_chunked",
        total_combinations=len(all_combinations),
        chunk_size=chunk_size,
        num_chunks=len(chunks),
    )

    return chunks
