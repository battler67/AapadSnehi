from .balanced_greedy import BalancedGreedyStrategy
from .global_optimal import GlobalOptimalStrategy
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
from .stable_matching import StableMatchingStrategy


register_strategy(BalancedGreedyStrategy())
register_strategy(GlobalOptimalStrategy())
register_strategy(StableMatchingStrategy())

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
