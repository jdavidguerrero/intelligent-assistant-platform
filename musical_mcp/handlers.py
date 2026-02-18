"""
MCP Musical Intelligence — tool, resource, and prompt handlers.

Each handler function is registered with the FastMCP instance in server.py.
Handlers are thin: validate input → call Week 3 tool → format response.
All timing and structured logging flows through the @timed_call decorator.

Handler categories:
    Tools     — actions that execute something (log session, analyze track, etc.)
    Resources — data reads (practice history, session notes, KB metadata)
    Prompts   — pre-built prompt templates (prepare_for_set, review_practice_week)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from musical_mcp.resources import (
    read_kb_metadata,
    read_practice_logs,
    read_session_notes,
    read_setlist,
)
from musical_mcp.schemas import (
    URI_KB_METADATA,
    URI_PRACTICE_LOGS,
    URI_SESSION_NOTES,
    URI_SETLIST,
    make_call_log,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timed call decorator — structured log on every MCP call
# ---------------------------------------------------------------------------


def _log_call(
    tool_name: str,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    latency_ms: float,
    success: bool = True,
    error: str | None = None,
) -> None:
    """Emit a structured McpCallLog to the logger."""
    record = make_call_log(
        tool_name=tool_name,
        inputs=inputs,
        outputs=outputs,
        latency_ms=latency_ms,
        success=success,
        error=error,
    )
    if success:
        logger.info("%s", record)
    else:
        logger.error("%s", record)


# ---------------------------------------------------------------------------
# Handler registration — called from server.py with the FastMCP instance
# ---------------------------------------------------------------------------


def register_all(mcp: FastMCP) -> None:
    """
    Register all tools, resources, and prompts onto the FastMCP instance.

    Called once at server startup. Each sub-function registers one category.

    Args:
        mcp: FastMCP server instance to attach handlers to
    """
    _register_tools(mcp)
    _register_resources(mcp)
    _register_prompts(mcp)
    logger.info("All MCP handlers registered (tools + resources + prompts)")


# ---------------------------------------------------------------------------
# TOOLS
# ---------------------------------------------------------------------------


def _register_tools(mcp: FastMCP) -> None:
    """Register all musical action tools."""

    # ------------------------------------------------------------------
    # log_practice_session
    # ------------------------------------------------------------------

    @mcp.tool()
    async def log_practice_session(
        topic: str,
        duration_minutes: int,
        notes: str = "",
        bpm_practiced: int = 0,
        key_practiced: str = "",
    ) -> str:
        """
        Log a completed music production or practice session.

        Use this when the user says they finished a session, practiced something,
        or worked on a specific topic. Creates a persistent record used for
        gap detection and personalized suggestions.

        Args:
            topic: What was practiced (e.g., "bass design", "chord progressions")
            duration_minutes: How long the session lasted (must be > 0)
            notes: Optional free-text session notes
            bpm_practiced: Optional BPM of tracks worked on
            key_practiced: Optional musical key practiced (e.g., "A minor")

        Returns:
            Confirmation string with session ID and summary
        """
        t_start = time.perf_counter()
        inputs = {
            "topic": topic,
            "duration_minutes": duration_minutes,
            "notes": notes,
            "bpm_practiced": bpm_practiced,
            "key_practiced": key_practiced,
        }

        try:
            from tools.music.log_practice_session import LogPracticeSession

            tool = LogPracticeSession()
            result = tool(
                topic=topic,
                duration_minutes=duration_minutes,
                notes=notes or None,
                bpm_practiced=bpm_practiced or None,
                key_practiced=key_practiced or None,
            )

            latency_ms = (time.perf_counter() - t_start) * 1000

            if result.success:
                data = result.data or {}
                session_id = data.get("session_id", "?")
                outputs = {"session_id": session_id, "topic": topic}
                _log_call("log_practice_session", inputs, outputs, latency_ms)
                return (
                    f"✓ Session logged (ID: {session_id})\n"
                    f"  Topic: {topic}\n"
                    f"  Duration: {duration_minutes} min\n"
                    f"{_format_gaps(data)}"
                )
            else:
                _log_call(
                    "log_practice_session",
                    inputs,
                    {},
                    latency_ms,
                    success=False,
                    error=result.error,
                )
                return f"✗ Failed to log session: {result.error}"

        except Exception as exc:
            latency_ms = (time.perf_counter() - t_start) * 1000
            _log_call("log_practice_session", inputs, {}, latency_ms, success=False, error=str(exc))
            return f"✗ Unexpected error: {exc}"

    # ------------------------------------------------------------------
    # create_session_note
    # ------------------------------------------------------------------

    @mcp.tool()
    async def create_session_note(
        category: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> str:
        """
        Save a musical discovery, idea, or next step to the session knowledge journal.

        Use this when the user says they discovered something, had an idea,
        wants to remember a technique, or needs to note next steps.

        Args:
            category: One of: discovery, problem, idea, reference, next_steps
            title: Short title for the note (max 120 chars)
            content: Full note content (max 2000 chars)
            tags: Optional list of keyword tags (e.g., ["sidechain", "attack"])

        Returns:
            Confirmation string with note ID and category
        """
        t_start = time.perf_counter()
        inputs = {"category": category, "title": title, "content": content[:50], "tags": tags}

        try:
            from tools.music.create_session_note import CreateSessionNote

            tool = CreateSessionNote()
            kwargs: dict[str, Any] = {
                "category": category,
                "title": title,
                "content": content,
            }
            if tags is not None:
                kwargs["tags"] = tags

            result = tool(**kwargs)
            latency_ms = (time.perf_counter() - t_start) * 1000

            if result.success:
                data = result.data or {}
                note_id = data.get("note_id", "?")
                total = data.get("total_notes", "?")
                tag_list = data.get("tags", [])
                outputs = {"note_id": note_id, "category": category}
                _log_call("create_session_note", inputs, outputs, latency_ms)
                tag_str = f"\n  Tags: {', '.join(tag_list)}" if tag_list else ""
                return (
                    f"✓ Note saved (ID: {note_id})\n"
                    f"  Category: {category}\n"
                    f"  Title: {title}{tag_str}\n"
                    f"  Total notes: {total}"
                )
            else:
                _log_call(
                    "create_session_note",
                    inputs,
                    {},
                    latency_ms,
                    success=False,
                    error=result.error,
                )
                return f"✗ Failed to save note: {result.error}"

        except Exception as exc:
            latency_ms = (time.perf_counter() - t_start) * 1000
            _log_call("create_session_note", inputs, {}, latency_ms, success=False, error=str(exc))
            return f"✗ Unexpected error: {exc}"

    # ------------------------------------------------------------------
    # analyze_track
    # ------------------------------------------------------------------

    @mcp.tool()
    async def analyze_track(
        file_path: str,
        analyze_audio: bool = True,
    ) -> str:
        """
        Extract BPM, musical key, and energy level from an audio file on disk.

        IMPORTANT: file_path must be the REAL absolute path on the local filesystem
        (e.g. /Users/juan/Music/track.mp3). Do NOT upload the file — ask the user
        for the full path if you don't have it. Uploaded file paths (/mnt/...) will
        not work because the server runs locally and cannot access upload sandboxes.

        Uses audio signal analysis (librosa) when the file exists, falls back
        to filename pattern matching otherwise. Useful for track preparation,
        DJ set planning, and harmonic mixing decisions.

        Args:
            file_path: Absolute local path to audio file (mp3, wav, flac, etc.)
                       e.g. /Users/juan/Music/track.mp3
            analyze_audio: Set False to skip librosa and use filename only (instant)

        Returns:
            Formatted string with BPM, key, energy, and confidence
        """
        t_start = time.perf_counter()
        inputs = {"file_path": file_path, "analyze_audio": analyze_audio}

        try:
            from tools.music.analyze_track import AnalyzeTrack

            tool = AnalyzeTrack()

            # librosa audio analysis is CPU-bound and can take 60-120s on large files.
            # Run it in a thread pool so the async event loop stays responsive,
            # and cap it at 45s — if it exceeds that, fall back to filename parsing.
            _AUDIO_TIMEOUT = 45.0

            def _run_sync(use_audio: bool) -> object:
                return tool(file_path=file_path, analyze_audio=use_audio)

            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(_run_sync, analyze_audio),
                    timeout=_AUDIO_TIMEOUT,
                )
            except TimeoutError:
                logger.warning(
                    "analyze_track: audio analysis timed out after %.0fs, "
                    "falling back to filename parsing",
                    _AUDIO_TIMEOUT,
                )
                result = await asyncio.to_thread(_run_sync, False)

            latency_ms = (time.perf_counter() - t_start) * 1000

            if result.success:
                data = result.data or {}
                bpm = data.get("bpm", "unknown")
                key = data.get("key", "unknown")
                energy = data.get("energy", "unknown")
                confidence = data.get("confidence", "?")
                method = (result.metadata or {}).get("method", "?")
                outputs = {"bpm": bpm, "key": key, "energy": energy}
                _log_call("analyze_track", inputs, outputs, latency_ms)
                return (
                    f"Track Analysis ({method})\n"
                    f"  BPM:        {bpm}\n"
                    f"  Key:        {key}\n"
                    f"  Energy:     {energy}/10\n"
                    f"  Confidence: {confidence}"
                )
            else:
                _log_call(
                    "analyze_track", inputs, {}, latency_ms, success=False, error=result.error
                )
                return f"✗ Analysis failed: {result.error}"

        except Exception as exc:
            latency_ms = (time.perf_counter() - t_start) * 1000
            _log_call("analyze_track", inputs, {}, latency_ms, success=False, error=str(exc))
            return f"✗ Unexpected error: {exc}"

    # ------------------------------------------------------------------
    # search_production_knowledge
    # ------------------------------------------------------------------

    @mcp.tool()
    async def search_production_knowledge(
        query: str,
        top_k: int = 5,
        confidence_threshold: float = 0.58,
    ) -> str:
        """
        Search the music production knowledge base for techniques and tips.

        Queries the RAG vector store with the user's question and returns
        grounded answers with citations. Use this for 'how to' questions,
        technique explanations, and production advice.

        Args:
            query: Natural language question about music production
            top_k: Number of knowledge chunks to retrieve (default: 5)
            confidence_threshold: Minimum relevance score 0-1 (default: 0.58)

        Returns:
            Answer with citations from the knowledge base, or explanation
            of why no answer is available
        """
        t_start = time.perf_counter()
        inputs = {"query": query[:80], "top_k": top_k}

        try:
            import os

            import httpx

            api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
            payload = {
                "query": query,
                "top_k": top_k,
                "confidence_threshold": confidence_threshold,
                "use_tools": False,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(f"{api_base}/ask", json=payload)

            latency_ms = (time.perf_counter() - t_start) * 1000

            if response.status_code == 200:
                data = response.json()
                answer = data.get("answer", "No answer returned.")
                sources = data.get("sources", [])
                source_names = [s.get("source_name", "?") for s in sources[:3]]
                outputs = {"sources": source_names, "answer_len": len(answer)}
                _log_call("search_production_knowledge", inputs, outputs, latency_ms)
                return answer
            elif response.status_code == 422:
                detail = response.json().get("detail", {})
                reason = detail.get("reason", "unknown")
                _log_call(
                    "search_production_knowledge",
                    inputs,
                    {},
                    latency_ms,
                    success=False,
                    error=reason,
                )
                return (
                    f"No answer found in knowledge base (reason: {reason}).\n"
                    "Try rephrasing the question or check if the topic is covered."
                )
            else:
                _log_call(
                    "search_production_knowledge",
                    inputs,
                    {},
                    latency_ms,
                    success=False,
                    error=f"HTTP {response.status_code}",
                )
                return f"✗ Knowledge base unavailable (HTTP {response.status_code})"

        except Exception as exc:
            latency_ms = (time.perf_counter() - t_start) * 1000
            _log_call(
                "search_production_knowledge",
                inputs,
                {},
                latency_ms,
                success=False,
                error=str(exc),
            )
            return f"✗ Could not reach knowledge base: {exc}"

    # ------------------------------------------------------------------
    # suggest_chord_progression
    # ------------------------------------------------------------------

    @mcp.tool()
    async def suggest_chord_progression(
        key: str,
        genre: str = "organic house",
        mood: str = "melancholic",
        bars: int = 8,
    ) -> str:
        """
        Generate a chord progression for a given key, genre, and mood.

        Produces a musically coherent chord sequence with Roman numeral
        analysis, voicing suggestions, and MIDI note names. Use this when
        the user asks for chord ideas, harmonic content, or music composition.

        Args:
            key: Musical key, e.g. "A minor", "C# major", "D dorian"
            genre: Music genre for stylistic context (default: "organic house")
            mood: Emotional quality — melancholic, uplifting, dark, euphoric, etc.
            bars: Number of bars in the progression (4, 8, or 16)

        Returns:
            Chord progression with voicings, Roman analysis, and production tips
        """
        t_start = time.perf_counter()
        inputs = {"key": key, "genre": genre, "mood": mood, "bars": bars}

        try:
            from tools.music.suggest_chord_progression import SuggestChordProgression

            tool = SuggestChordProgression()
            result = tool(key=key, genre=genre, mood=mood, bars=bars)
            latency_ms = (time.perf_counter() - t_start) * 1000

            if result.success:
                data = result.data or {}
                chords = data.get("chords", [])
                roman = data.get("roman_analysis", "")
                tips = data.get("production_tips", [])
                outputs = {"chords": chords, "bars": bars}
                _log_call("suggest_chord_progression", inputs, outputs, latency_ms)

                lines = [
                    f"Chord Progression — {key} / {genre} / {mood}",
                    f"  Chords:  {' → '.join(chords)}",
                    f"  Roman:   {roman}",
                ]
                if tips:
                    lines.append("  Tips:")
                    for tip in tips[:3]:
                        lines.append(f"    • {tip}")
                return "\n".join(lines)
            else:
                _log_call(
                    "suggest_chord_progression",
                    inputs,
                    {},
                    latency_ms,
                    success=False,
                    error=result.error,
                )
                return f"✗ Could not generate progression: {result.error}"

        except Exception as exc:
            latency_ms = (time.perf_counter() - t_start) * 1000
            _log_call(
                "suggest_chord_progression",
                inputs,
                {},
                latency_ms,
                success=False,
                error=str(exc),
            )
            return f"✗ Unexpected error: {exc}"

    # ------------------------------------------------------------------
    # suggest_compatible_tracks
    # ------------------------------------------------------------------

    @mcp.tool()
    async def suggest_compatible_tracks(
        key: str,
        bpm: float = 0.0,
        max_results: int = 10,
    ) -> str:
        """
        Find tracks harmonically compatible for DJ mixing using the Camelot Wheel.

        Returns keys that mix well with the given key: same position,
        adjacent positions, and relative major/minor. Optionally filters
        by BPM tolerance.

        Args:
            key: Musical key to find compatible tracks for (e.g., "A minor")
            bpm: Optional BPM for tempo-compatible suggestions (0 = any tempo)
            max_results: Maximum number of results to return (default: 10)

        Returns:
            List of compatible keys with Camelot positions and mixing notes
        """
        t_start = time.perf_counter()
        inputs = {"key": key, "bpm": bpm, "max_results": max_results}

        try:
            from tools.music.suggest_compatible_tracks import SuggestCompatibleTracks

            tool = SuggestCompatibleTracks()
            kwargs: dict[str, Any] = {"key": key, "max_results": max_results}
            if bpm and bpm > 0:
                kwargs["bpm"] = bpm

            result = tool(**kwargs)
            latency_ms = (time.perf_counter() - t_start) * 1000

            if result.success:
                data = result.data or {}
                compatible = data.get("compatible_keys", [])
                camelot = data.get("camelot_position", "?")
                total = data.get("total_found", len(compatible))
                outputs = {"total_found": total, "camelot": camelot}
                _log_call("suggest_compatible_tracks", inputs, outputs, latency_ms)

                lines = [
                    f"Compatible Tracks for {key}",
                    f"  Camelot position: {camelot}",
                    f"  Found {total} compatible keys:",
                ]
                for item in compatible[:max_results]:
                    k = item.get("key", "?")
                    pos = item.get("camelot", "?")
                    rel = item.get("relationship", "")
                    lines.append(f"    {pos}  {k}  ({rel})")
                return "\n".join(lines)
            else:
                _log_call(
                    "suggest_compatible_tracks",
                    inputs,
                    {},
                    latency_ms,
                    success=False,
                    error=result.error,
                )
                return f"✗ Could not find compatible tracks: {result.error}"

        except Exception as exc:
            latency_ms = (time.perf_counter() - t_start) * 1000
            _log_call(
                "suggest_compatible_tracks",
                inputs,
                {},
                latency_ms,
                success=False,
                error=str(exc),
            )
            return f"✗ Unexpected error: {exc}"

    # ------------------------------------------------------------------
    # ableton_insert_chords
    # ------------------------------------------------------------------

    @mcp.tool()
    async def ableton_insert_chords(
        chords: str,
        beats_per_chord: float = 4.0,
        velocity: int = 90,
        octave: int = 4,
        bpm: float = 120.0,
    ) -> str:
        """
        Insert a chord progression directly into the selected Ableton clip via OSC.

        REQUIRES: The 'Claude Chords' Max for Live device (.amxd) must be loaded
        on a MIDI track in Ableton Live and a clip slot must be selected.
        The device listens on localhost:11001.

        How to set up in Ableton:
          1. Create a MIDI track
          2. Drag 'Claude Chords' M4L device onto the track
          3. Select an empty clip slot (click on it)
          4. Call this tool — chords appear in the piano roll instantly

        Args:
            chords: Space or comma-separated chord names, e.g. "Am F C G" or "Am7,Fmaj7,C,G7"
                    Supports: maj, m, maj7, m7, 7, dim, sus2, sus4, add9
            beats_per_chord: beats each chord lasts (4 = 1 bar at 4/4, default 4)
            velocity: MIDI velocity 1-127 (default 90)
            octave: root octave for voicings, 3-5 (default 4 = middle)
            bpm: session BPM — informational only, does not change Ableton tempo

        Returns:
            Confirmation with chord count, note count, and clip length
        """
        t_start = time.perf_counter()

        # Parse chord string: "Am F C G" or "Am,F,C,G" or "Am, F, C, G"
        import re

        raw_chords = re.split(r"[,\s]+", chords.strip())
        chord_names = [c.strip() for c in raw_chords if c.strip()]

        if not chord_names:
            return "✗ No chords provided. Example: 'Am F C G' or 'Am7, Fmaj7, C, G7'"

        inputs = {
            "chords": chord_names,
            "beats_per_chord": beats_per_chord,
            "velocity": velocity,
            "octave": octave,
        }

        try:
            from musical_mcp.ableton import AbletonOscSender

            sender = AbletonOscSender()
            result = await asyncio.to_thread(
                sender.send_chords,
                chord_names,
                beats_per_chord,
                velocity,
                octave,
                bpm,
            )

            latency_ms = (time.perf_counter() - t_start) * 1000
            _log_call("ableton_insert_chords", inputs, result, latency_ms)

            bars = result["clip_beats"] / 4
            return (
                f"✓ Chords sent to Ableton\n"
                f"  Progression:  {' → '.join(chord_names)}\n"
                f"  Clip length:  {bars:.0f} bars ({result['clip_beats']:.0f} beats)\n"
                f"  Notes sent:   {result['note_count']} MIDI notes\n"
                f"  Latency:      {result['latency_ms']}ms\n"
                f"\n"
                f"  → Check your Ableton piano roll now!"
            )

        except OSError as exc:
            latency_ms = (time.perf_counter() - t_start) * 1000
            _log_call(
                "ableton_insert_chords", inputs, {}, latency_ms, success=False, error=str(exc)
            )
            return (
                f"✗ Could not reach Ableton (OSError: {exc})\n"
                f"  Make sure the 'Claude Chords' M4L device is loaded on a MIDI track."
            )

        except ValueError as exc:
            latency_ms = (time.perf_counter() - t_start) * 1000
            _log_call(
                "ableton_insert_chords", inputs, {}, latency_ms, success=False, error=str(exc)
            )
            return f"✗ Invalid chord: {exc}"

        except Exception as exc:
            latency_ms = (time.perf_counter() - t_start) * 1000
            _log_call(
                "ableton_insert_chords", inputs, {}, latency_ms, success=False, error=str(exc)
            )
            return f"✗ Unexpected error: {exc}"


# ---------------------------------------------------------------------------
# RESOURCES
# ---------------------------------------------------------------------------


def _register_resources(mcp: FastMCP) -> None:
    """
    Register all musical state resources.

    Each resource delegates immediately to resources.py — no logic here.
    Docstrings are MCP-visible: they tell the LLM when to read each resource.
    """

    @mcp.resource(URI_PRACTICE_LOGS)
    def get_practice_logs() -> str:
        """
        Read logged practice sessions with stats and gap detection.

        Returns paginated JSON with sessions array, totals, and stats:
        total_minutes, topics breakdown, most/least practiced areas.
        Use this to understand what the user has been working on recently
        and to identify practice gaps before making suggestions.
        """
        return read_practice_logs()

    @mcp.resource(URI_SESSION_NOTES)
    def get_session_notes() -> str:
        """
        Read session notes (discoveries, ideas, problems, next steps).

        Returns paginated JSON with notes array, totals, and category counts.
        Each note has: category, title, content, tags, created_at.
        Use this to review what the user has learned, what needs solving,
        and what action items are pending.
        """
        return read_session_notes()

    @mcp.resource(URI_KB_METADATA)
    def get_kb_metadata() -> str:
        """
        Read metadata about the music production knowledge base.

        Returns: status, total_chunks, per-source breakdown with percentages,
        and source type classification (pdf/youtube/markdown).
        Use this to understand what's in the knowledge base before searching,
        and to diagnose why a query might return insufficient_knowledge.
        """
        return read_kb_metadata()

    @mcp.resource(URI_SETLIST)
    def get_setlist() -> str:
        """
        Read the current setlist draft.

        Returns session notes tagged 'setlist' with last_updated timestamp.
        Setlists are stored as next_steps notes with the 'setlist' tag.
        Use this before a DJ set to review the planned track sequence and keys.
        """
        return read_setlist()


# ---------------------------------------------------------------------------
# PROMPTS
# ---------------------------------------------------------------------------


def _register_prompts(mcp: FastMCP) -> None:
    """Register musical prompt templates."""

    @mcp.prompt()
    def prepare_for_set(
        hours_until_set: int = 2,
        set_duration_minutes: int = 60,
        venue_vibe: str = "underground club",
    ) -> str:
        """
        Generate a personalized set preparation plan.

        Combines recent practice history, session notes, and knowledge base
        to create a warm-up and set preparation checklist. Best used when
        the user has logged practice sessions and saved session notes.

        Args:
            hours_until_set: How many hours until the set starts (affects urgency)
            set_duration_minutes: Expected set length in minutes
            venue_vibe: Description of the venue/event vibe

        Returns:
            System prompt that guides the LLM to create a set prep plan
        """
        return (
            f"You are a music production assistant helping prepare for a live DJ set.\n\n"
            f"Context:\n"
            f"  - Set starts in {hours_until_set} hours\n"
            f"  - Set duration: {set_duration_minutes} minutes\n"
            f"  - Venue vibe: {venue_vibe}\n\n"
            f"Your task:\n"
            f"1. Read the practice logs resource ({URI_PRACTICE_LOGS}) to understand "
            f"what topics the user has worked on recently.\n"
            f"2. Read the session notes resource ({URI_SESSION_NOTES}) for ideas, "
            f"next steps, and discoveries the user has recorded.\n"
            f"3. Read the setlist resource ({URI_SETLIST}) for any planned track sequences.\n"
            f"4. Use search_production_knowledge to find warm-up exercises or "
            f"preparation tips relevant to the user's recent focus areas.\n"
            f"5. Produce a concrete preparation plan:\n"
            f"   - Warm-up exercises (musical and physical)\n"
            f"   - Key/BPM range recommendations based on practice history\n"
            f"   - 3-5 opening track characteristics to look for\n"
            f"   - Any technique reminders from recent discoveries\n\n"
            f"Be specific. Reference actual topics from the practice logs."
        )

    @mcp.prompt()
    def review_practice_week(
        target_areas: str = "general music production",
    ) -> str:
        """
        Generate a weekly practice review and improvement plan.

        Analyzes the week's practice sessions and notes to identify:
        patterns, gaps, achievements, and next week's priorities.
        Use this every Sunday or at the end of a practice cycle.

        Args:
            target_areas: Comma-separated focus areas (e.g., "mixing, chord theory")

        Returns:
            System prompt that guides the LLM to produce a weekly review
        """
        return (
            f"You are a music production coach performing a weekly review.\n\n"
            f"Target skill areas: {target_areas}\n\n"
            f"Your task:\n"
            f"1. Read the practice logs resource ({URI_PRACTICE_LOGS}) and identify:\n"
            f"   - Total time practiced this week\n"
            f"   - Topics covered and time per topic\n"
            f"   - Topics NOT practiced (gaps vs. core areas)\n"
            f"   - Longest and shortest sessions\n"
            f"2. Read the session notes resource ({URI_SESSION_NOTES}) and identify:\n"
            f"   - New discoveries made this week\n"
            f"   - Problems still unresolved\n"
            f"   - Ideas generated but not yet explored\n"
            f"   - Pending next steps\n"
            f"3. Use search_production_knowledge to find resources for the identified gaps.\n"
            f"4. Produce a structured weekly review:\n"
            f"   - 🏆 Wins this week (what went well)\n"
            f"   - 📉 Gaps identified (what needs attention)\n"
            f"   - 🎯 Next week's top 3 priorities\n"
            f"   - 📚 Suggested resources from the knowledge base\n\n"
            f"Be honest about gaps. The goal is improvement, not validation."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_gaps(data: dict[str, Any]) -> str:
    """Format gap detection output from log_practice_session tool."""
    gaps = data.get("practice_gaps", [])
    if not gaps:
        return ""
    gap_list = ", ".join(gaps[:3])
    return f"  Practice gaps: {gap_list}"
