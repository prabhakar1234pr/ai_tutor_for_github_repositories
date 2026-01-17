"""
Evaluation services for content quality assessment.
Used for prompt optimization during development/testing.
"""

from app.services.evaluation.data_collection import (
    EvaluationDataCollector,
    get_evaluation_collector,
)
from app.services.evaluation.llm_judge import LLMJudge, get_llm_judge

try:
    from app.services.evaluation.dspy_optimizer import DSPyOptimizer, get_dspy_optimizer

    __all__ = [
        "LLMJudge",
        "DSPyOptimizer",
        "EvaluationDataCollector",
        "get_llm_judge",
        "get_dspy_optimizer",
        "get_evaluation_collector",
    ]
except ImportError:
    __all__ = [
        "LLMJudge",
        "EvaluationDataCollector",
        "get_llm_judge",
        "get_evaluation_collector",
    ]
