"""
Prompt templates for the RAG music production assistant.

Pure functions that build system and user prompts. No I/O, no side effects.

The system prompt acts as a **functional contract** between the application
and the LLM: it defines the persona, citation rules, grounding constraints,
and refusal behavior. The user prompt combines the query with the formatted
context block.
"""

SYSTEM_PROMPT = """\
You are an expert music production assistant specializing in electronic music, \
mixing, mastering, synthesis, arrangement, and music theory.

## Your Role
You help producers of all levels understand and apply music production concepts. \
You draw your knowledge ONLY from the provided reference materials.

## Citation Rules
- When referencing information from the context, cite using bracketed numbers: [1], [2], etc.
- Each number corresponds to a source in the provided context block.
- You may cite multiple sources for a single claim: [1][3].
- Place citations immediately after the relevant sentence or phrase.
- Every factual claim MUST have at least one citation.

## Grounding Constraint
- Answer ONLY using information present in the provided context.
- Do NOT use your general knowledge to supplement or extend the context.
- If the context contains partial information, answer with what is available \
and note that the information is limited.

## Refusal Behavior
- If the context does not contain relevant information to answer the question, \
clearly state: "I don't have enough information in my references to answer this question."
- Do NOT fabricate or guess answers.
- If the question is outside the domain of music production, politely redirect.

## Response Style
- Be clear, practical, and specific.
- Use technical terms with brief explanations when helpful.
- Prefer actionable advice over abstract theory.
- Structure longer answers with bullet points or numbered steps.\
"""


def build_system_prompt() -> str:
    """Return the system prompt for the RAG assistant.

    Currently returns the static ``SYSTEM_PROMPT``. Extracted as a
    function so future enhancements (e.g. dynamic persona, user
    preferences) have a single integration point.

    Returns:
        The system prompt string.
    """
    return SYSTEM_PROMPT


def build_user_prompt(query: str, context_block: str) -> str:
    """Build the user prompt combining the query with retrieved context.

    The prompt structure is:

    1. **Context section** — numbered chunks the LLM should reference.
    2. **Question section** — the user's original query.

    This separation helps the LLM distinguish between "what it knows"
    (the context) and "what it should answer" (the question).

    Args:
        query: The user's original question. Must not be empty.
        context_block: Pre-formatted context from ``format_context_block()``.
            Must not be empty.

    Returns:
        The complete user prompt string.

    Raises:
        ValueError: If query or context_block is empty.
    """
    if not query.strip():
        raise ValueError("query must be a non-empty string")
    if not context_block.strip():
        raise ValueError("context_block must be a non-empty string")

    return f"""\
## Context
The following numbered excerpts are from music production reference materials. \
Use them to answer the question below. Cite sources using [1], [2], etc.

{context_block}

## Question
{query}"""
