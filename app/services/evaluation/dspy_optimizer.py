"""
DSPy optimizer for prompt optimization.
Uses evaluation data from LLM-as-Judge to optimize prompts.
"""

import logging
from typing import Any

from app.config import settings
from app.services.evaluation.data_collection import get_evaluation_collector

logger = logging.getLogger(__name__)

# Lazy import DSPy to avoid import errors if not installed
try:
    import dspy
    from dspy.teleprompt import MIPROv2

    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False
    logger.warning("DSPy not installed. Install with: pip install dspy-ai")


class DSPyOptimizer:
    """DSPy optimizer for prompt optimization using evaluation data."""

    def __init__(self):
        if not DSPY_AVAILABLE:
            raise ImportError("DSPy is not installed. Install with: pip install dspy-ai")

        # Configure DSPy with Groq (free tier)
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is required for DSPy optimization")

        # Set up DSPy with Groq
        lm = dspy.LM(model=f"groq/{settings.groq_model}", api_key=settings.groq_api_key)
        dspy.configure(lm=lm)

        logger.info("✅ DSPy optimizer initialized with Groq")

    def get_training_examples_from_db(
        self,
        evaluation_type: str,
        project_ids: list[str] | None = None,
        min_score: float = 0.0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get training examples from database.

        Args:
            evaluation_type: "concepts", "content", or "tasks"
            project_ids: Optional list of project IDs to filter by
            min_score: Minimum overall_score to include
            limit: Maximum number of examples

        Returns:
            List of training examples
        """
        collector = get_evaluation_collector()
        return collector.get_training_examples(
            evaluation_type=evaluation_type,
            project_ids=project_ids,
            min_score=min_score,
            limit=limit,
        )

    def optimize_concepts_prompt(
        self,
        training_examples: list[dict] | None = None,
        evaluation_metrics: dict[str, Any] | None = None,
        project_ids: list[str] | None = None,
        min_score: float = 0.0,
        limit: int = 100,
    ) -> str:
        """
        Optimize concepts generation prompt using DSPy.

        Args:
            training_examples: Optional list of examples. If None, fetches from database.
            evaluation_metrics: Metrics to optimize for (e.g., {"overall_score": "maximize"})
            project_ids: Optional list of project IDs to filter by (if fetching from DB)
            min_score: Minimum overall_score to include (if fetching from DB)
            limit: Maximum number of examples (if fetching from DB)

        Returns:
            Optimized prompt string
        """
        if not DSPY_AVAILABLE:
            raise ImportError("DSPy is not installed")

        # If no training examples provided, fetch from database
        if training_examples is None:
            logger.info("   Fetching training examples from database...")
            training_examples = self.get_training_examples_from_db(
                evaluation_type="concepts",
                project_ids=project_ids,
                min_score=min_score,
                limit=limit,
            )

        if not training_examples:
            raise ValueError("No training examples available for optimization")

        logger.info(f"🔧 Optimizing concepts prompt with {len(training_examples)} examples...")

        # Define DSPy signature for concepts generation
        class ConceptsGeneration(dspy.Signature):
            """Generate learning concepts for a day."""

            day_number: int = dspy.InputField(desc="Day number")
            day_theme: str = dspy.InputField(desc="Day theme")
            skill_level: str = dspy.InputField(desc="beginner/intermediate/advanced")
            repo_summary: str = dspy.InputField(desc="Repository analysis summary")
            memory_context: str = dspy.InputField(desc="Previous days' context")
            concepts: list[dict] = dspy.OutputField(
                desc="List of concepts with order_index, title, description"
            )

        # Create DSPy module
        class ConceptsModule(dspy.Module):
            def __init__(self):
                super().__init__()
                self.generate = dspy.ChainOfThought(ConceptsGeneration)

            def forward(self, day_number, day_theme, skill_level, repo_summary, memory_context):
                return self.generate(
                    day_number=day_number,
                    day_theme=day_theme,
                    skill_level=skill_level,
                    repo_summary=repo_summary,
                    memory_context=memory_context,
                )

        # Prepare training examples for DSPy
        trainset = []
        for example in training_examples:
            trainset.append(
                dspy.Example(
                    day_number=example["input"]["day_number"],
                    day_theme=example["input"]["day_theme"],
                    skill_level=example["input"]["skill_level"],
                    repo_summary=example["input"]["repo_summary"],
                    memory_context=example["input"].get("memory_context", ""),
                    concepts=example["output"]["concepts"],
                ).with_inputs(
                    "day_number", "day_theme", "skill_level", "repo_summary", "memory_context"
                )
            )

        # Define metric function (based on evaluation scores)
        def concept_quality_metric(example, pred, trace=None):
            """Metric based on evaluation scores."""
            # Use evaluation scores from training examples
            scores = example.get("evaluation_scores", {})
            overall_score = scores.get("overall_score", 0.0)
            return overall_score / 10.0  # Normalize to 0-1

        # Run MIPROv2 optimization
        optimizer = MIPROv2(
            metric=concept_quality_metric,
            num_candidates=10,
            init_temperature=1.0,
        )

        # Optimize the module
        _optimized_module = optimizer.compile(
            student=ConceptsModule(),
            trainset=trainset[:50],  # Limit to 50 for speed
        )

        # Extract optimized prompt
        # Note: DSPy optimizes the internal prompt, we need to extract it
        # For now, return a placeholder - full implementation would extract the optimized prompt
        logger.info("✅ Concepts prompt optimization complete")

        # TODO: Extract optimized prompt from _optimized_module
        # This requires accessing DSPy's internal prompt structure
        optimized_prompt = "Optimized prompt (extract from DSPy module)"

        return optimized_prompt

    def optimize_content_prompt(
        self, training_examples: list[dict], evaluation_metrics: dict[str, Any]
    ) -> str:
        """
        Optimize content generation prompt using DSPy.

        Args:
            training_examples: List of examples with input/output and evaluation scores
            evaluation_metrics: Metrics to optimize for

        Returns:
            Optimized prompt string
        """
        if not DSPY_AVAILABLE:
            raise ImportError("DSPy is not installed")

        logger.info(f"🔧 Optimizing content prompt with {len(training_examples)} examples...")

        # Similar implementation to optimize_concepts_prompt
        # Define signature, module, optimize, extract prompt

        return "Optimized content prompt"

    def optimize_tasks_prompt(
        self, training_examples: list[dict], evaluation_metrics: dict[str, Any]
    ) -> str:
        """
        Optimize tasks generation prompt using DSPy.

        Args:
            training_examples: List of examples with input/output and evaluation scores
            evaluation_metrics: Metrics to optimize for

        Returns:
            Optimized prompt string
        """
        if not DSPY_AVAILABLE:
            raise ImportError("DSPy is not installed")

        logger.info(f"🔧 Optimizing tasks prompt with {len(training_examples)} examples...")

        # Similar implementation to optimize_concepts_prompt
        # Define signature, module, optimize, extract prompt

        return "Optimized tasks prompt"


def get_dspy_optimizer() -> DSPyOptimizer:
    """Get or create DSPy optimizer instance."""
    if not DSPY_AVAILABLE:
        raise ImportError("DSPy is not installed. Install with: pip install dspy-ai")
    return DSPyOptimizer()
