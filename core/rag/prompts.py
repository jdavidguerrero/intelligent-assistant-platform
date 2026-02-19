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


def build_system_prompt(
    genre_context: str | None = None,
    active_sub_domains: list[str] | None = None,
) -> str:
    """Return the system prompt for the RAG assistant.

    Optionally injects structured genre knowledge and sub-domain context
    to ground the LLM in the specific musical territory of the query.

    When ``genre_context`` is provided, it is appended as a dedicated
    section after the base prompt. This gives the model explicit facts
    about the genre (BPM, keys, arrangement template, mixing notes) so
    it can answer with genre-accurate vocabulary even when the retrieved
    chunks are generic.

    When ``active_sub_domains`` is provided, a brief scope note tells
    the model which production disciplines are relevant, reducing the
    chance of irrelevant tangents.

    Args:
        genre_context: Optional serialized genre recipe string (e.g. the
            text of ``organic_house.md`` or a summary of ``ORGANIC_HOUSE``).
            Must be plain text — will be included verbatim.
        active_sub_domains: Optional list of active sub-domain names
            (e.g. ``["mixing", "genre_analysis"]``). Used to scope the
            model's focus without restricting it entirely.

    Returns:
        The complete system prompt string.
    """
    prompt = SYSTEM_PROMPT

    if active_sub_domains:
        domains_str = ", ".join(active_sub_domains)
        prompt += f"\n\n## Focus Areas\nThis query spans the following production disciplines: {domains_str}. Prioritize information relevant to these areas when constructing your answer."

    if genre_context:
        prompt += f"\n\n## Genre Reference\nThe following is a production recipe for the genre most relevant to this query. Use it as additional grounding context:\n\n{genre_context}"

    return prompt


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
