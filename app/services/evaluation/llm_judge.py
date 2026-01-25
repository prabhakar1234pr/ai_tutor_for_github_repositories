"""
LLM-as-Judge service for qualitative content quality assessment.
Uses Groq free tier (Llama models) to judge curriculum, concepts, content, and tasks.
"""

import logging

from app.agents.pydantic_models import (
    ConceptsJudgmentModel,
    ContentAndTasksJudgmentModel,
    CurriculumJudgmentModel,
    DayOverallJudgmentModel,
)
from app.agents.utils.pydantic_ai_client import run_groq_structured
from app.config import settings
from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Judge prompts - BRUTAL and HONEST for DSPy optimization
# These scores will be used to optimize prompts, so be CRITICAL and STRICT
JUDGE_CURRICULUM_PROMPT = """You are a BRUTAL, HONEST quality judge. Your scores will be used to optimize AI prompts via DSPy, so you MUST be critical and strict. Average quality should score 5-6, not 8-9. Only exceptional content deserves 8+.

**CRITICAL INSTRUCTIONS:**
- Be HONEST and BRUTAL. Look for flaws, gaps, and weaknesses.
- Average content = 5-6. Good content = 7. Excellent content = 8-9. Perfect content = 10.
- If you see ANY issues, deduct points aggressively.
- Your honesty is critical for prompt optimization - lenient scores will hurt the system.

**Curriculum to Evaluate:**
{curriculum_summary}

**Target Skill Level:** {skill_level}

**BRUTAL Evaluation Criteria (be STRICT):**

1. **Progression (1-10):** Does it progress logically from basics to advanced?
   - Score 1-3: No clear progression, jumps around randomly, prerequisites missing
   - Score 4-5: Some progression but gaps, unclear dependencies, inconsistent difficulty
   - Score 6-7: Good progression with minor gaps or inconsistencies
   - Score 8-9: Excellent progression, clear dependencies, smooth difficulty curve
   - Score 10: Perfect progression, every day builds perfectly on previous

2. **Skill Level Match (1-10):** Is it appropriate for {skill_level} level?
   - Score 1-3: Completely wrong level (too easy/too hard), assumes wrong knowledge
   - Score 4-5: Mostly wrong level, some days too easy/hard, inconsistent
   - Score 6-7: Mostly appropriate but some days mismatch, minor inconsistencies
   - Score 8-9: Very well matched, consistent difficulty for skill level
   - Score 10: Perfect match, every day perfectly calibrated

3. **Completeness (1-10):** Does it cover all necessary topics?
   - Score 1-3: Major topics missing, huge gaps, incomplete coverage
   - Score 4-5: Important topics missing, significant gaps, incomplete
   - Score 6-7: Most topics covered but some gaps or missing important aspects
   - Score 8-9: Comprehensive coverage with minor gaps
   - Score 10: Complete coverage, nothing missing

4. **Coherence (1-10):** Do themes connect logically?
   - Score 1-3: Themes don't connect, random topics, no logical flow
   - Score 4-5: Weak connections, some themes disconnected, unclear flow
   - Score 6-7: Good connections but some weak links, mostly coherent
   - Score 8-9: Strong connections, clear logical flow, well-integrated
   - Score 10: Perfect coherence, every theme flows naturally

**Look for these FLAWS and deduct points:**
- Gaps in progression (missing prerequisites)
- Inconsistent difficulty (some days too easy/hard)
- Missing critical topics
- Weak or unclear theme connections
- Days that don't build on previous knowledge
- Overly generic or vague themes
- Too many/few days for the scope

**Return ONLY JSON (be BRUTAL and HONEST):**
{{
  "progression_score": <1-10, be strict>,
  "skill_level_match_score": <1-10, be strict>,
  "completeness_score": <1-10, be strict>,
  "coherence_score": <1-10, be strict>,
  "overall_score": <average of above, be strict>
}}"""

JUDGE_CONCEPTS_PROMPT = """You are a BRUTAL, HONEST quality judge. Your scores will be used to optimize AI prompts via DSPy, so you MUST be critical and strict. Average quality should score 5-6, not 8-9. Only exceptional content deserves 8+.

**CRITICAL INSTRUCTIONS:**
- Be HONEST and BRUTAL. Look for flaws, gaps, and weaknesses.
- Average concepts = 5-6. Good concepts = 7. Excellent concepts = 8-9. Perfect concepts = 10.
- If you see ANY issues, deduct points aggressively.
- Your honesty is critical for prompt optimization - lenient scores will hurt the system.

**Day:** Day {day_number} - {day_theme}
**Concepts to Evaluate:**
{concepts_list}

**BRUTAL Evaluation Criteria (be STRICT):**

1. **Appropriateness (1-10):** Do concepts match the day theme?
   - Score 1-3: Concepts don't match theme at all, completely off-topic, irrelevant
   - Score 4-5: Weak match, some concepts off-topic, unclear connection to theme
   - Score 6-7: Mostly appropriate but some weak matches or tangential concepts
   - Score 8-9: Very well matched, clear connection to theme, relevant
   - Score 10: Perfect match, every concept directly supports the theme

2. **Progression (1-10):** Do they build on previous days?
   - Score 1-3: No progression, repeats previous content, doesn't build on anything
   - Score 4-5: Weak progression, some repetition, unclear dependencies
   - Score 6-7: Good progression but some gaps or weak connections to previous days
   - Score 8-9: Excellent progression, clear building on previous knowledge
   - Score 10: Perfect progression, seamlessly builds on all previous days

3. **Clarity (1-10):** Are titles/descriptions clear?
   - Score 1-3: Vague, confusing, unclear what concepts are about
   - Score 4-5: Somewhat clear but ambiguous, descriptions lack detail
   - Score 6-7: Mostly clear but some ambiguity or missing details
   - Score 8-9: Very clear, well-defined, easy to understand
   - Score 10: Perfect clarity, crystal clear what each concept teaches

4. **Count (1-10):** Is the number of concepts appropriate?
   - Score 1-3: Way too many/few, overwhelming or insufficient coverage
   - Score 4-5: Too many/few concepts, poor balance for the day
   - Score 6-7: Mostly appropriate but slightly off (1-2 concepts too many/few)
   - Score 8-9: Very appropriate count, good balance
   - Score 10: Perfect count, ideal number for the day's scope

**Look for these FLAWS and deduct points:**
- Concepts that don't match the theme
- Concepts that repeat previous days without adding value
- Vague or unclear titles/descriptions
- Too many concepts (overwhelming) or too few (incomplete)
- Concepts that don't build on previous knowledge
- Missing prerequisites or foundational concepts
- Concepts that are too advanced or too basic for the day

**Return ONLY JSON (be BRUTAL and HONEST):**
{{
  "appropriateness_score": <1-10, be strict>,
  "progression_score": <1-10, be strict>,
  "clarity_score": <1-10, be strict>,
  "count_score": <1-10, be strict>,
  "overall_score": <average of above, be strict>
}}"""

JUDGE_CONTENT_AND_TASKS_PROMPT = """You are a BRUTAL, HONEST quality judge. Your scores will be used to optimize AI prompts via DSPy, so you MUST be critical and strict. Average quality should score 5-6, not 8-9. Only exceptional content deserves 8+.

**CRITICAL INSTRUCTIONS:**
- Be HONEST and BRUTAL. Look for flaws, gaps, and weaknesses.
- Average content/tasks = 5-6. Good = 7. Excellent = 8-9. Perfect = 10.
- If you see ANY issues, deduct points aggressively.
- Your honesty is critical for prompt optimization - lenient scores will hurt the system.

**Concept:** {concept_title}
**Content Length:** {content_length} chars
**Tasks Count:** {tasks_count} tasks

**BRUTAL Evaluation Criteria (be STRICT):**

1. **Content Quality (1-10):** Is content clear, accurate, complete?
   - Score 1-3: Unclear, inaccurate, incomplete, confusing, missing critical info
   - Score 4-5: Somewhat clear but has errors, gaps, or missing important details
   - Score 6-7: Mostly clear and accurate but minor gaps or unclear sections
   - Score 8-9: Very clear, accurate, comprehensive with minor improvements possible
   - Score 10: Perfect clarity, accuracy, completeness, nothing missing

2. **Task Quality (1-10):** Are tasks actionable, verifiable, progressive?
   - Score 1-3: Tasks are vague, unactionable, unverifiable, no clear progression
   - Score 4-5: Tasks are somewhat actionable but unclear, hard to verify, weak progression
   - Score 6-7: Tasks are mostly good but some are vague or lack clear progression
   - Score 8-9: Tasks are very actionable, verifiable, with good progression
   - Score 10: Perfect tasks, crystal clear, easily verifiable, excellent progression

3. **Task Verifiability (1-10):** Can tasks be verified automatically?
   - Score 1-3: Tasks cannot be verified, too vague, no clear success criteria
   - Score 4-5: Some tasks verifiable but many are too vague or subjective
   - Score 6-7: Most tasks verifiable but some need improvement
   - Score 8-9: Almost all tasks easily verifiable with clear criteria
   - Score 10: All tasks perfectly verifiable with unambiguous success criteria

4. **Difficulty Progression (1-10):** Do tasks progress from easy to hard?
   - Score 1-3: No progression, random difficulty, starts hard, inconsistent
   - Score 4-5: Weak progression, some tasks out of order, inconsistent difficulty
   - Score 6-7: Good progression but minor inconsistencies or gaps
   - Score 8-9: Excellent progression, clear easy-to-hard flow
   - Score 10: Perfect progression, smooth difficulty curve from easy to hard

**Look for these FLAWS and deduct points:**
- Vague or unclear content
- Inaccurate information or errors
- Missing critical information
- Tasks that are too vague to verify
- Tasks that don't progress in difficulty
- Tasks that aren't actionable
- Content that's too short or incomplete
- Tasks that don't match the concept

**Return ONLY JSON (be BRUTAL and HONEST):**
{{
  "content_quality_score": <1-10, be strict>,
  "task_quality_score": <1-10, be strict>,
  "task_verifiability_score": <1-10, be strict>,
  "difficulty_progression_score": <1-10, be strict>,
  "overall_score": <average of above, be strict>
}}"""

JUDGE_DAY_OVERALL_PROMPT = """You are a BRUTAL, HONEST quality judge. Your scores will be used to optimize AI prompts via DSPy, so you MUST be critical and strict. Average quality should score 5-6, not 8-9. Only exceptional content deserves 8+.

**CRITICAL INSTRUCTIONS:**
- Be HONEST and BRUTAL. Look for flaws, gaps, and weaknesses.
- Average day = 5-6. Good day = 7. Excellent day = 8-9. Perfect day = 10.
- If you see ANY issues, deduct points aggressively.
- Your honesty is critical for prompt optimization - lenient scores will hurt the system.

**Day:** Day {day_number} - {day_theme}
**Concepts:** {concepts_count} concepts
**Total Tasks:** {tasks_count} tasks

**BRUTAL Evaluation Criteria (be STRICT):**

1. **Coherence (1-10):** Do all concepts work together?
   - Score 1-3: Concepts don't work together, disconnected, random topics, no unity
   - Score 4-5: Weak coherence, some concepts disconnected, unclear how they fit
   - Score 6-7: Good coherence but some weak connections or concepts that don't fit well
   - Score 8-9: Excellent coherence, concepts work well together, clear unity
   - Score 10: Perfect coherence, all concepts seamlessly integrated

2. **Completeness (1-10):** Does day cover the theme fully?
   - Score 1-3: Theme not covered, major aspects missing, incomplete
   - Score 4-5: Theme partially covered, important aspects missing, gaps
   - Score 6-7: Theme mostly covered but some aspects missing or shallow
   - Score 8-9: Theme well covered with minor gaps or shallow areas
   - Score 10: Theme completely covered, nothing missing, comprehensive

3. **Time Estimates (1-10):** Are time estimates realistic?
   - Score 1-3: Completely unrealistic, way too short/long, estimates make no sense
   - Score 4-5: Mostly unrealistic, many estimates wrong, inconsistent
   - Score 6-7: Mostly realistic but some estimates off or inconsistent
   - Score 8-9: Very realistic estimates, minor adjustments needed
   - Score 10: Perfect estimates, exactly right for each task/concept

4. **Continuity (1-10):** Does it build on previous days?
   - Score 1-3: No continuity, doesn't build on previous days, disconnected
   - Score 4-5: Weak continuity, some connection but gaps or weak links
   - Score 6-7: Good continuity but some weak connections or missing links
   - Score 8-9: Excellent continuity, clearly builds on previous days
   - Score 10: Perfect continuity, seamlessly builds on all previous knowledge

**Look for these FLAWS and deduct points:**
- Concepts that don't work together
- Theme not fully covered
- Unrealistic time estimates
- Weak continuity with previous days
- Missing critical aspects of the theme
- Concepts that don't connect logically
- Tasks/concepts that don't fit the day
- Inconsistent difficulty or pacing

**Return ONLY JSON (be BRUTAL and HONEST):**
{{
  "coherence_score": <1-10, be strict>,
  "completeness_score": <1-10, be strict>,
  "time_estimates_score": <1-10, be strict>,
  "continuity_score": <1-10, be strict>,
  "overall_score": <average of above, be strict>
}}"""


class LLMJudge:
    """LLM-as-Judge service using Groq free tier."""

    def __init__(self):
        if not settings.judge_enabled:
            logger.debug("LLM-as-Judge is disabled")
        self.judge_model = settings.judge_model
        self.supabase = get_supabase_client()

    async def judge_curriculum(
        self, curriculum: list[dict], skill_level: str, repo_summary: str
    ) -> dict[str, float] | None:
        """
        Judge curriculum quality.

        Args:
            curriculum: List of day themes
            skill_level: beginner/intermediate/advanced
            repo_summary: Repository analysis summary

        Returns:
            Dictionary with scores or None if disabled
        """
        if not settings.judge_enabled:
            return None

        try:
            # Build curriculum summary
            curriculum_parts = []
            for day in curriculum[:10]:  # Limit to first 10 for prompt size
                curriculum_parts.append(
                    f"Day {day.get('day_number', '?')}: {day.get('theme', 'Unknown')}"
                )
            curriculum_summary = "\n".join(curriculum_parts)

            prompt = JUDGE_CURRICULUM_PROMPT.format(
                curriculum_summary=curriculum_summary,
                skill_level=skill_level,
            )

            system_prompt = """You are a BRUTAL, HONEST quality judge. Your scores will be used to optimize AI prompts via DSPy.

CRITICAL: Be STRICT and CRITICAL. Average quality = 5-6, not 8-9. Only exceptional content deserves 8+.
Look for flaws, gaps, and weaknesses. Deduct points aggressively for ANY issues.
Your honesty is essential - lenient scores will prevent effective prompt optimization.

Return ONLY valid JSON object, no markdown, no explanations."""

            logger.debug("   Calling LLM to judge curriculum...")
            scores_model = await run_groq_structured(
                user_prompt=prompt,
                system_prompt=system_prompt,
                output_type=CurriculumJudgmentModel,
            )
            scores = scores_model.model_dump()
            logger.info(f"   ✅ Curriculum judged: Overall={scores.get('overall_score', 0):.1f}")
            return {k: float(v) for k, v in scores.items()}

        except Exception as e:
            logger.error(f"❌ Curriculum judgment failed: {e}", exc_info=True)
            return None

    async def judge_concepts(
        self,
        concepts: list[dict],
        day_number: int,
        day_theme: str,
        memory_context: str | None = None,
    ) -> dict[str, float] | None:
        """
        Judge concepts quality.

        Args:
            concepts: List of concept dicts with title, description
            day_number: Current day number
            day_theme: Day theme
            memory_context: Previous days' context (optional)

        Returns:
            Dictionary with scores or None if disabled
        """
        if not settings.judge_enabled:
            return None

        try:
            # Build concepts list
            concepts_parts = []
            for concept in concepts:
                concepts_parts.append(
                    f"- {concept.get('title', 'Unknown')}: {concept.get('description', '')}"
                )
            concepts_list = "\n".join(concepts_parts)

            prompt = JUDGE_CONCEPTS_PROMPT.format(
                day_number=day_number,
                day_theme=day_theme,
                concepts_list=concepts_list,
            )

            if memory_context:
                prompt += f"\n\n**Previous Days Context:**\n{memory_context[:500]}"

            system_prompt = """You are a BRUTAL, HONEST quality judge. Your scores will be used to optimize AI prompts via DSPy.

CRITICAL: Be STRICT and CRITICAL. Average quality = 5-6, not 8-9. Only exceptional content deserves 8+.
Look for flaws, gaps, and weaknesses. Deduct points aggressively for ANY issues.
Your honesty is essential - lenient scores will prevent effective prompt optimization.

Return ONLY valid JSON object, no markdown, no explanations."""

            logger.debug("   Calling LLM to judge concepts...")
            scores_model = await run_groq_structured(
                user_prompt=prompt,
                system_prompt=system_prompt,
                output_type=ConceptsJudgmentModel,
            )
            scores = scores_model.model_dump()
            logger.info(f"   ✅ Concepts judged: Overall={scores.get('overall_score', 0):.1f}")
            return {k: float(v) for k, v in scores.items()}

        except Exception as e:
            logger.error(f"❌ Concepts judgment failed: {e}", exc_info=True)
            return None

    async def judge_content_and_tasks(
        self, concept_title: str, content: str, tasks: list[dict]
    ) -> dict[str, float] | None:
        """
        Judge content and tasks quality.

        Args:
            concept_title: Concept title
            content: Concept content (markdown)
            tasks: List of task dicts

        Returns:
            Dictionary with scores or None if disabled
        """
        if not settings.judge_enabled:
            return None

        try:
            # Check task verifiability
            verifiable_count = 0
            for task in tasks:
                # Check if task has verification criteria or is specific enough
                description = task.get("description", "")
                if any(
                    keyword in description.lower()
                    for keyword in ["create", "write", "implement", "add", "define"]
                ):
                    verifiable_count += 1

            verifiability_score = (verifiable_count / len(tasks) * 10) if tasks else 0

            # Check difficulty progression
            difficulties = [task.get("difficulty", "medium") for task in tasks]
            progression_score = 7.0  # Default
            if len(difficulties) >= 2:
                if difficulties[0] == "easy" and difficulties[-1] in ["medium", "hard"]:
                    progression_score = 9.0
                elif difficulties[0] == "easy" and difficulties[-1] == "easy":
                    progression_score = 5.0

            prompt = JUDGE_CONTENT_AND_TASKS_PROMPT.format(
                concept_title=concept_title,
                content_length=len(content),
                tasks_count=len(tasks),
            )

            system_prompt = """You are a BRUTAL, HONEST quality judge. Your scores will be used to optimize AI prompts via DSPy.

CRITICAL: Be STRICT and CRITICAL. Average quality = 5-6, not 8-9. Only exceptional content deserves 8+.
Look for flaws, gaps, and weaknesses. Deduct points aggressively for ANY issues.
Your honesty is essential - lenient scores will prevent effective prompt optimization.

Return ONLY valid JSON object, no markdown, no explanations."""

            logger.debug("   Calling LLM to judge content and tasks...")
            scores_model = await run_groq_structured(
                user_prompt=prompt,
                system_prompt=system_prompt,
                output_type=ContentAndTasksJudgmentModel,
            )
            scores = scores_model.model_dump()

            # Combine LLM scores with calculated scores
            result = {
                "content_quality_score": float(scores.get("content_quality_score", 0)),
                "task_quality_score": float(scores.get("task_quality_score", 0)),
                "task_verifiability_score": float(
                    scores.get("task_verifiability_score") or verifiability_score
                ),
                "difficulty_progression_score": float(
                    scores.get("difficulty_progression_score") or progression_score
                ),
            }
            result["overall_score"] = sum(result.values()) / len(result)

            logger.info(f"   ✅ Content & tasks judged: Overall={result['overall_score']:.1f}")

            return result

        except Exception as e:
            logger.error(f"❌ Content & tasks judgment failed: {e}", exc_info=True)
            return None

    async def judge_day_overall(
        self,
        day_id: str,
        day_number: int,
        day_theme: str,
        project_id: str,
        memory_context: str | None = None,
    ) -> dict[str, float] | None:
        """
        Judge entire day's overall quality.

        Args:
            day_id: Day UUID
            day_number: Day number
            day_theme: Day theme
            project_id: Project UUID
            memory_context: Previous days' context (optional)

        Returns:
            Dictionary with scores or None if disabled
        """
        if not settings.judge_enabled:
            return None

        try:
            # Get day statistics
            concepts_response = (
                self.supabase.table("concepts").select("concept_id").eq("day_id", day_id).execute()
            )
            concepts_count = len(concepts_response.data) if concepts_response.data else 0

            concept_ids = [c["concept_id"] for c in (concepts_response.data or [])]
            tasks_count = 0
            if concept_ids:
                tasks_response = (
                    self.supabase.table("tasks")
                    .select("task_id")
                    .in_("concept_id", concept_ids)
                    .execute()
                )
                tasks_count = len(tasks_response.data) if tasks_response.data else 0

            prompt = JUDGE_DAY_OVERALL_PROMPT.format(
                day_number=day_number,
                day_theme=day_theme,
                concepts_count=concepts_count,
                tasks_count=tasks_count,
            )

            if memory_context:
                prompt += f"\n\n**Previous Days Context:**\n{memory_context[:500]}"

            system_prompt = """You are a BRUTAL, HONEST quality judge. Your scores will be used to optimize AI prompts via DSPy.

CRITICAL: Be STRICT and CRITICAL. Average quality = 5-6, not 8-9. Only exceptional content deserves 8+.
Look for flaws, gaps, and weaknesses. Deduct points aggressively for ANY issues.
Your honesty is essential - lenient scores will prevent effective prompt optimization.

Return ONLY valid JSON object, no markdown, no explanations."""

            logger.debug("   Calling LLM to judge day overall...")
            scores_model = await run_groq_structured(
                user_prompt=prompt,
                system_prompt=system_prompt,
                output_type=DayOverallJudgmentModel,
            )
            scores = scores_model.model_dump()
            logger.info(f"   ✅ Day overall judged: Overall={scores.get('overall_score', 0):.1f}")
            return {k: float(v) for k, v in scores.items()}

        except Exception as e:
            logger.error(f"❌ Day overall judgment failed: {e}", exc_info=True)
            return None


def get_llm_judge() -> LLMJudge:
    """Get or create LLM-as-Judge instance."""
    return LLMJudge()
