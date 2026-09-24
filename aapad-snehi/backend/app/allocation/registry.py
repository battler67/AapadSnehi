from __future__ import annotations

from .base import AllocationStrategy


_STRATEGIES: dict[str, AllocationStrategy] = {}


def register_strategy(strategy: AllocationStrategy) -> AllocationStrategy:
    if not strategy.key or strategy.key in _STRATEGIES:
        raise ValueError(f"Allocation strategy key must be unique: {strategy.key!r}")
    _STRATEGIES[strategy.key] = strategy
    return strategy


def get_strategy(key: str) -> AllocationStrategy:
    try:
        return _STRATEGIES[key]
    except KeyError as exc:
        raise KeyError(f"Unknown allocation strategy: {key}") from exc


def strategy_metadata() -> list[dict[str, str]]:
    return [
        {
            "key": strategy.key,
            "name": strategy.name,
            "version": strategy.version,
            "summary": getattr(strategy, "summary", "Deterministic allocation strategy."),
            "bestFor": getattr(strategy, "best_for", "Administrator-reviewed planning."),
        }
        for strategy in sorted(_STRATEGIES.values(), key=lambda item: item.key)
    ]
