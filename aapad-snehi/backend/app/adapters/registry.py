from __future__ import annotations

from collections.abc import Callable

from .base import BaseAdapter


AdapterClass = type[BaseAdapter]
_ADAPTERS: dict[str, AdapterClass] = {}


def register_adapter(adapter_type: str) -> Callable[[AdapterClass], AdapterClass]:
    """Register an adapter class under the Source.adapter_type value."""

    normalized = adapter_type.strip().lower()
    if not normalized:
        raise ValueError("Adapter type cannot be empty")

    def decorator(adapter_class: AdapterClass) -> AdapterClass:
        existing = _ADAPTERS.get(normalized)
        if existing and existing is not adapter_class:
            raise ValueError(f"Adapter type '{normalized}' is already registered")
        _ADAPTERS[normalized] = adapter_class
        return adapter_class

    return decorator


def get_adapter(adapter_type: str) -> AdapterClass | None:
    return _ADAPTERS.get(adapter_type.strip().lower())


def registered_adapter_types() -> tuple[str, ...]:
    return tuple(sorted(_ADAPTERS))
