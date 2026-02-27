"""apply_audit_fix tool — Apply a fix_action from an AuditFinding to Ableton Live.

Takes the fix_action dict from an audit finding (produced by audit_session) and
sends it to Ableton via the ALS Listener bridge.

Use when the user says:
  - "Apply that fix"
  - "Fix the EQ on Pad Main"
  - "Apply the audit recommendations"
  - After audit_session returns findings with fix_action set
"""

from __future__ import annotations

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

try:
    from ingestion.ableton_bridge import AbletonBridge
except ImportError:
    AbletonBridge = None  # type: ignore[assignment,misc]

_WS_HOST: str = "localhost"
_WS_PORT: int = 11005


class ApplyAuditFix(MusicalTool):
    """Apply a fix_action from an audit finding to Ableton Live."""

    @property
    def name(self) -> str:
        return "apply_audit_fix"

    @property
    def description(self) -> str:
        return (
            "Apply a fix_action from an audit finding directly in Ableton Live. "
            "Provide the lom_path, property, and value from a finding's fix_action dict. "
            "Use after audit_session returns findings with fix_action populated. "
            "Requires the ALS Listener M4L device loaded in Ableton."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="lom_path",
                type=str,
                description="LOM path to the target (e.g. 'live_set tracks 2 devices 1 parameters 5').",
            ),
            ToolParameter(
                name="property",
                type=str,
                description="Property to set (e.g. 'value', 'is_active').",
            ),
            ToolParameter(
                name="value",
                type=object,  # Accept any type (str, int, float); auto-converted in execute()
                description="New value to assign. Numbers will be auto-converted.",
            ),
            ToolParameter(
                name="description",
                type=str,
                description="Human-readable description for logging.",
                required=False,
                default="",
            ),
            ToolParameter(
                name="dry_run",
                type=bool,
                description="If True, return the planned command without executing it.",
                required=False,
                default=False,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Apply the fix_action to Ableton."""
        lom_path: str = str(kwargs.get("lom_path", "")).strip()
        prop: str = str(kwargs.get("property", "")).strip()
        raw_value: Any = kwargs.get("value")
        description: str = str(kwargs.get("description", "") or "").strip()
        dry_run: bool = bool(kwargs.get("dry_run", False))

        if not lom_path:
            return ToolResult(success=False, error="lom_path is required")
        if not prop:
            return ToolResult(success=False, error="property is required")
        if raw_value is None:
            return ToolResult(success=False, error="value is required")

        # Auto-convert string numbers to numeric types
        value: float | int | str = raw_value
        if isinstance(raw_value, str):
            try:
                value = int(raw_value)
            except ValueError:
                try:
                    value = float(raw_value)
                except ValueError:
                    value = raw_value  # keep as string

        if dry_run:
            return ToolResult(
                success=True,
                data={
                    "dry_run": True,
                    "planned_command": {
                        "lom_path": lom_path,
                        "property": prop,
                        "value": value,
                        "description": description,
                    },
                },
            )

        if AbletonBridge is None:
            return ToolResult(success=False, error="AbletonBridge not available")

        from core.ableton.types import LOMCommand

        cmd = LOMCommand(
            type="set_property",
            lom_path=lom_path,
            property=prop,
            value=value,
            description=description or f"apply_audit_fix: {lom_path}",
        )

        try:
            bridge = AbletonBridge(host=_WS_HOST, port=_WS_PORT)
            ack = bridge.send_command(cmd)
        except ConnectionError as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, error=f"apply_audit_fix failed: {exc}")

        return ToolResult(
            success=True,
            data={
                "applied": True,
                "lom_path": lom_path,
                "property": prop,
                "value": value,
                "ack": ack,
            },
            metadata={"ws_host": _WS_HOST, "ws_port": _WS_PORT},
        )
