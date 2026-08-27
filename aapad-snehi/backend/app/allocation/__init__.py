from .balanced_greedy import BalancedGreedyStrategy
from .base import (
    AllocationDecision,
    AllocationPlan,
    AllocationProblem,
    AllocationStrategy,
    IncidentAllocationInput,
    UnassignedVolunteer,
    VolunteerAllocationInput,
)
from .registry import get_strategy, register_strategy, strategy_metadata


register_strategy(BalancedGreedyStrategy())

__all__ = [
    "AllocationDecision",
    "AllocationPlan",
    "AllocationProblem",
    "AllocationStrategy",
    "IncidentAllocationInput",
    "UnassignedVolunteer",
    "VolunteerAllocationInput",
    "get_strategy",
    "register_strategy",
    "strategy_metadata",
]
