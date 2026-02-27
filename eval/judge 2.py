"""LLM-as-judge scoring for musical answer quality.

Scores each answer on three axes (1–5 scale):

musical_accuracy
    Is the musical information technically correct and precise?
    A score of 5 means a professional producer would fully agree.

relevance
    Does the answer directly address what was asked?
    A score of 5 means the answer is tightly focused with no filler.

actionability
    Can a producer immediately apply this in a live session?
    A score of 5 means concrete, specific, session-ready advice.

The judge also emits a PASS / PARTIAL / FAIL verdict:
    PASS    — all three axes >= 3 AND musical_accuracy >= 3
    PARTIAL — at least one axis >= 3
    FAIL    — all axes < 3 OR the system hallucinated on an adversarial query

For adversarial queries, the expected result is HTTP 422 or an explicit
refusal.  The judge marks these PASS if the system correctly refused and
FAIL if it hallucinated an answer.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_JUDGE_SYSTEM_PROMPT = """\
You are an expert music production evaluator. You assess AI-generated answers
to music production questions on behalf of electronic music producers.

You evaluate answers strictly and objectively on three axes:

1. musical_accuracy (1-5): Is the musical/technical information correct?
   - 5: Perfectly accurate; a seasoned producer would fully endorse this
   - 4: Mostly correct with minor imprecision
   - 3: Generally correct but missing important nuance
   - 2: Partially correct but contains significant errors
   - 1: Incorrect or misleading

2. relevance (1-5): Does the answer directly address the question?
   - 5: Perfectly on-topic, no filler
   - 4: Mostly relevant with minor tangents
   - 3: Relevant but includes unnecessary content
   - 2: Partially answers the question
   - 1: Does not address the question

3. actionability (1-5): Can a producer act on this immediately in a session?
   - 5: Specific, concrete, session-ready advice (e.g., "set attack to 5ms")
   - 4: Mostly concrete with minor vagueness
   - 3: Useful but requires producer to fill in details
   - 2: Too vague to act on directly
   - 1: No actionable content

Respond ONLY with valid JSON in this exact format:
{
  "musical_accuracy": <int 1-5>,
  "relevance": <int 1-5>,
  "actionability": <int 1-5>,
  "reasoning": "<one sentence explaining the scores>"
}
"""

_JUDGE_USER_TEMPLATE = """\
Question: {question}

Answer to evaluate:
{answer}
"""


@dataclass
class JudgeScore:
    """Scores from the LLM judge for a single query/answer pair."""

    musical_accuracy: int  # 1–5
    relevance: int  # 1–5
    actionability: int  # 1–5
    reasoning: str
    verdict: str  # "PASS" | "PARTIAL" | "FAIL"
    raw_response: str = ""

    @property
    def mean_score(self) -> float:
        """Average of the three axes."""
        return (self.musical_accuracy + self.relevance + self.actionability) / 3.0


def _compute_verdict(accuracy: int, relevance: int, actionability: int) -> str:
    if accuracy >= 3 and relevance >= 3 and actionability >= 3:
        return "PASS"
    if accuracy >= 3 or relevance >= 3 or actionability >= 3:
        return "PARTIAL"
    return "FAIL"


class LLMJudge:
    """Score musical answers using an LLM as judge.

    Parameters
    ----------
    api_key:
        OpenAI API key.  Defaults to ``OPENAI_API_KEY`` env var.
    model:
        Model to use for judging.  Defaults to ``gpt-4o-mini`` for speed
        and cost efficiency — adequate for structured scoring tasks.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
    ) -> None:
        try:
            from openai import OpenAI  # noqa: PLC0415

            self._client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
            self._model = model
            self._available = True
        except ImportError:
            logger.warning("openai package not available — LLM judge disabled")
            self._available = False

    @property
    def available(self) -> bool:
        """True if the OpenAI client was initialised successfully."""
        return self._available

    def score(self, question: str, answer: str) -> JudgeScore:
        """Score a single question/answer pair.

        Returns a zeroed-out ``JudgeScore`` with verdict ``"FAIL"`` if the
        judge is unavailable or the API call fails.
        """
        if not self._available or not answer or len(answer.strip()) < 10:
            return JudgeScore(
                musical_accuracy=0,
                relevance=0,
                actionability=0,
                reasoning="Judge unavailable or empty answer.",
                verdict="FAIL",
            )

        user_msg = _JUDGE_USER_TEMPLATE.format(question=question, answer=answer)
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or ""
            data = json.loads(raw)
            accuracy = int(data.get("musical_accuracy", 0))
            relevance = int(data.get("relevance", 0))
            actionability = int(data.get("actionability", 0))
            reasoning = str(data.get("reasoning", ""))
            return JudgeScore(
                musical_accuracy=accuracy,
                relevance=relevance,
                actionability=actionability,
                reasoning=reasoning,
                verdict=_compute_verdict(accuracy, relevance, actionability),
                raw_response=raw,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM judge API call failed: %s", exc)
            return JudgeScore(
                musical_accuracy=0,
                relevance=0,
                actionability=0,
                reasoning=f"Judge call failed: {exc}",
                verdict="FAIL",
                raw_response="",
            )

    def score_adversarial(self, status_code: int, answer: str) -> JudgeScore:
        """Score an adversarial query.

        Adversarial queries should be refused (HTTP 422) or produce an
        explicit "I don't know" answer.  Scoring:
        - PASS: status_code == 422 (correct refusal)
        - PARTIAL: status_code == 200 but answer contains refusal language
        - FAIL: status_code == 200 and answer attempts to answer
        """
        if status_code == 422:
            return JudgeScore(
                musical_accuracy=5,
                relevance=5,
                actionability=5,
                reasoning="Correctly refused out-of-corpus question (422).",
                verdict="PASS",
            )
        refusal_phrases = [
            "don't have",
            "not in",
            "outside",
            "cannot answer",
            "no information",
            "not covered",
            "out of scope",
            "insufficient",
            "unable to",
            "i don't know",
            "not available",
        ]
        answer_lower = answer.lower()
        if any(phrase in answer_lower for phrase in refusal_phrases):
            return JudgeScore(
                musical_accuracy=3,
                relevance=3,
                actionability=1,
                reasoning="Soft refusal in answer text (did not raise 422).",
                verdict="PARTIAL",
            )
        return JudgeScore(
            musical_accuracy=1,
            relevance=1,
            actionability=1,
            reasoning="System attempted to answer an out-of-corpus question (hallucination risk).",
            verdict="FAIL",
        )
