"""Musical task routing — pure classification and tier selection.

Exports:
    TaskType, ModelTier, ClassificationResult  (types)
    classify_musical_task                       (classifier)
    TIER_FAST, TIER_STANDARD, TIER_LOCAL        (tier constants)
    select_tier                                 (tier selector)
    calculate_cost                              (cost calculator)
"""

from core.routing.classifier import classify_musical_task
from core.routing.costs import calculate_cost
from core.routing.tiers import TIER_FAST, TIER_LOCAL, TIER_STANDARD, select_tier
from core.routing.types import ClassificationResult, ModelTier, TaskType

__all__ = [
    "TaskType",
    "ModelTier",
    "ClassificationResult",
    "classify_musical_task",
    "TIER_FAST",
    "TIER_STANDARD",
    "TIER_LOCAL",
    "select_tier",
    "calculate_cost",
]
