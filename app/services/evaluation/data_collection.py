"""
Data collection service for DSPy optimization.
Stores evaluation data (inputs, outputs, scores) in evaluation_data table.
Supports all columns: prompt_text, system_prompt, model_used, generation_params, token_usage, generation_latency_ms.
"""

import logging
from typing import Any

from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class EvaluationDataCollector:
    """Collects and stores evaluation data for DSPy optimization."""

    def __init__(self):
        self.supabase = get_supabase_client()

    async def save_concepts_evaluation(
        self,
        project_id: str,
        day_id: str,
        day_number: int,
        input_data: dict[str, Any],
        output_concepts: list[dict],
        evaluation_scores: dict[str, float] | None = None,
        prompt_text: str | None = None,
        system_prompt: str | None = None,
        model_used: str | None = None,
        generation_params: dict[str, Any] | None = None,
        token_usage: dict[str, int] | None = None,
        generation_latency_ms: int | None = None,
    ) -> str | None:
        """
        Save concepts generation evaluation data.

        Args:
            project_id: Project UUID
            day_id: Day UUID
            day_number: Day number
            input_data: Input to prompt (day_number, theme, skill_level, repo_summary, memory_context, etc.)
            output_concepts: Generated concepts
            evaluation_scores: Scores from LLM-as-Judge
            prompt_text: The actual prompt text sent to the LLM
            system_prompt: The system prompt used
            model_used: Model name/ID used for generation
            generation_params: LLM parameters (temperature, max_tokens, etc.)
            token_usage: Token counts (prompt_tokens, completion_tokens, total_tokens)
            generation_latency_ms: Time taken to generate in milliseconds

        Returns:
            Evaluation record ID or None if failed
        """
        try:
            record = {
                "project_id": project_id,
                "day_id": day_id,
                "day_number": day_number,
                "evaluation_type": "concepts",
                "input_data": input_data,
                "output_data": output_concepts,
                "evaluation_scores": evaluation_scores,
                "prompt_text": prompt_text,
                "system_prompt": system_prompt,
                "model_used": model_used,
                "generation_params": generation_params,
                "token_usage": token_usage,
                "generation_latency_ms": generation_latency_ms,
            }

            # Remove None values to let database use defaults
            record = {k: v for k, v in record.items() if v is not None}

            response = self.supabase.table("evaluation_data").insert(record).execute()

            if response.data:
                logger.debug(f"   💾 Saved concepts evaluation for Day {day_number}")
                return response.data[0].get("id")
            return None

        except Exception as e:
            logger.error(f"❌ Failed to save concepts evaluation: {e}", exc_info=True)
            return None

    async def save_content_evaluation(
        self,
        project_id: str,
        concept_id: str,
        day_id: str,
        day_number: int,
        input_data: dict[str, Any],
        output_content: str,
        evaluation_scores: dict[str, float] | None = None,
        prompt_text: str | None = None,
        system_prompt: str | None = None,
        model_used: str | None = None,
        generation_params: dict[str, Any] | None = None,
        token_usage: dict[str, int] | None = None,
        generation_latency_ms: int | None = None,
    ) -> str | None:
        """
        Save content generation evaluation data.

        Args:
            project_id: Project UUID
            concept_id: Concept UUID
            day_id: Day UUID
            day_number: Day number
            input_data: Input to prompt (concept_title, description, skill_level, etc.)
            output_content: Generated content (markdown)
            evaluation_scores: Scores from LLM-as-Judge
            prompt_text: The actual prompt text sent to the LLM
            system_prompt: The system prompt used
            model_used: Model name/ID used for generation
            generation_params: LLM parameters (temperature, max_tokens, etc.)
            token_usage: Token counts (prompt_tokens, completion_tokens, total_tokens)
            generation_latency_ms: Time taken to generate in milliseconds

        Returns:
            Evaluation record ID or None if failed
        """
        try:
            record = {
                "project_id": project_id,
                "concept_id": concept_id,
                "day_id": day_id,
                "day_number": day_number,
                "evaluation_type": "content",
                "input_data": input_data,
                "output_data": {"content": output_content},
                "evaluation_scores": evaluation_scores,
                "prompt_text": prompt_text,
                "system_prompt": system_prompt,
                "model_used": model_used,
                "generation_params": generation_params,
                "token_usage": token_usage,
                "generation_latency_ms": generation_latency_ms,
            }

            # Remove None values to let database use defaults
            record = {k: v for k, v in record.items() if v is not None}

            response = self.supabase.table("evaluation_data").insert(record).execute()

            if response.data:
                logger.debug(f"   💾 Saved content evaluation for concept {concept_id}")
                return response.data[0].get("id")
            return None

        except Exception as e:
            logger.error(f"❌ Failed to save content evaluation: {e}", exc_info=True)
            return None

    async def save_tasks_evaluation(
        self,
        project_id: str,
        concept_id: str,
        day_id: str,
        day_number: int,
        input_data: dict[str, Any],
        output_tasks: list[dict],
        evaluation_scores: dict[str, float] | None = None,
        prompt_text: str | None = None,
        system_prompt: str | None = None,
        model_used: str | None = None,
        generation_params: dict[str, Any] | None = None,
        token_usage: dict[str, int] | None = None,
        generation_latency_ms: int | None = None,
    ) -> str | None:
        """
        Save tasks generation evaluation data.

        Args:
            project_id: Project UUID
            concept_id: Concept UUID
            day_id: Day UUID
            day_number: Day number
            input_data: Input to prompt (concept_title, description, skill_level, etc.)
            output_tasks: Generated tasks
            evaluation_scores: Scores from LLM-as-Judge
            prompt_text: The actual prompt text sent to the LLM
            system_prompt: The system prompt used
            model_used: Model name/ID used for generation
            generation_params: LLM parameters (temperature, max_tokens, etc.)
            token_usage: Token counts (prompt_tokens, completion_tokens, total_tokens)
            generation_latency_ms: Time taken to generate in milliseconds

        Returns:
            Evaluation record ID or None if failed
        """
        try:
            record = {
                "project_id": project_id,
                "concept_id": concept_id,
                "day_id": day_id,
                "day_number": day_number,
                "evaluation_type": "tasks",
                "input_data": input_data,
                "output_data": output_tasks,
                "evaluation_scores": evaluation_scores,
                "prompt_text": prompt_text,
                "system_prompt": system_prompt,
                "model_used": model_used,
                "generation_params": generation_params,
                "token_usage": token_usage,
                "generation_latency_ms": generation_latency_ms,
            }

            # Remove None values to let database use defaults
            record = {k: v for k, v in record.items() if v is not None}

            response = self.supabase.table("evaluation_data").insert(record).execute()

            if response.data:
                logger.debug(f"   💾 Saved tasks evaluation for concept {concept_id}")
                return response.data[0].get("id")
            return None

        except Exception as e:
            logger.error(f"❌ Failed to save tasks evaluation: {e}", exc_info=True)
            return None

    async def update_evaluation_scores(
        self,
        evaluation_id: str,
        evaluation_scores: dict[str, float],
    ) -> bool:
        """
        Update evaluation scores for an existing record.
        Useful when scores are computed after initial save.

        Args:
            evaluation_id: UUID of the evaluation record
            evaluation_scores: New scores to update

        Returns:
            True if update succeeded, False otherwise
        """
        try:
            response = (
                self.supabase.table("evaluation_data")
                .update({"evaluation_scores": evaluation_scores})
                .eq("id", evaluation_id)
                .execute()
            )

            if response.data:
                logger.debug(f"   💾 Updated evaluation scores for {evaluation_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"❌ Failed to update evaluation scores: {e}", exc_info=True)
            return False

    def get_training_examples(
        self,
        evaluation_type: str,
        project_ids: list[str] | None = None,
        min_score: float = 0.0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Retrieve training examples for DSPy optimization.

        Args:
            evaluation_type: "concepts", "content", or "tasks"
            project_ids: Optional list of project IDs to filter by
            min_score: Minimum overall_score to include
            limit: Maximum number of examples to return

        Returns:
            List of training examples with input, output, and evaluation_scores
        """
        try:
            query = (
                self.supabase.table("evaluation_data")
                .select("*")
                .eq("evaluation_type", evaluation_type)
                .order("created_at", desc=False)
                .limit(limit)
            )

            if project_ids:
                query = query.in_("project_id", project_ids)

            response = query.execute()

            if not response.data:
                return []

            examples = []
            for record in response.data:
                eval_scores = record.get("evaluation_scores") or {}

                # Filter by minimum score
                overall_score = eval_scores.get("overall_score", 0.0)
                if overall_score < min_score:
                    continue

                examples.append(
                    {
                        "input": record.get("input_data", {}),
                        "output": record.get("output_data", {}),
                        "evaluation_scores": eval_scores,
                        "prompt_text": record.get("prompt_text"),
                        "system_prompt": record.get("system_prompt"),
                        "model_used": record.get("model_used"),
                        "generation_params": record.get("generation_params"),
                        "token_usage": record.get("token_usage"),
                        "generation_latency_ms": record.get("generation_latency_ms"),
                        "metadata": {
                            "id": record.get("id"),
                            "project_id": record.get("project_id"),
                            "day_number": record.get("day_number"),
                            "created_at": record.get("created_at"),
                        },
                    }
                )

            logger.info(f"   Retrieved {len(examples)} training examples for {evaluation_type}")
            return examples

        except Exception as e:
            logger.error(f"❌ Failed to get training examples: {e}", exc_info=True)
            return []

    def get_evaluations_by_day(
        self,
        day_id: str,
        evaluation_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get all evaluations for a specific day.

        Args:
            day_id: Day UUID
            evaluation_type: Optional filter by type

        Returns:
            List of evaluation records
        """
        try:
            query = (
                self.supabase.table("evaluation_data")
                .select("*")
                .eq("day_id", day_id)
                .order("created_at", desc=False)
            )

            if evaluation_type:
                query = query.eq("evaluation_type", evaluation_type)

            response = query.execute()
            return response.data if response.data else []

        except Exception as e:
            logger.error(f"❌ Failed to get evaluations for day {day_id}: {e}", exc_info=True)
            return []

    def get_evaluations_by_project(
        self,
        project_id: str,
        evaluation_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get all evaluations for a specific project.

        Args:
            project_id: Project UUID
            evaluation_type: Optional filter by type
            limit: Maximum records to return

        Returns:
            List of evaluation records
        """
        try:
            query = (
                self.supabase.table("evaluation_data")
                .select("*")
                .eq("project_id", project_id)
                .order("created_at", desc=True)
                .limit(limit)
            )

            if evaluation_type:
                query = query.eq("evaluation_type", evaluation_type)

            response = query.execute()
            return response.data if response.data else []

        except Exception as e:
            logger.error(
                f"❌ Failed to get evaluations for project {project_id}: {e}", exc_info=True
            )
            return []


def get_evaluation_collector() -> EvaluationDataCollector:
    """Get or create evaluation data collector instance."""
    return EvaluationDataCollector()
