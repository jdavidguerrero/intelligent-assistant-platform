"""
Tool base class and common types.

All musical tools inherit from MusicalTool and implement execute().
This ensures consistent interface for tool registry and router.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolParameter:
    """
    Tool parameter specification.

    Attributes:
        name: Parameter name
        type: Python type (str, int, float, etc.)
        description: Human-readable description for LLM
        required: Whether parameter is required
        default: Default value if not required
    """

    name: str
    type: type
    description: str
    required: bool = True
    default: Any = None

    def validate(self, value: Any) -> tuple[bool, str | None]:
        """
        Validate parameter value.

        Args:
            value: Value to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if value is None:
            if self.required:
                return False, f"Required parameter '{self.name}' is missing"
            return True, None

        # Type check
        if not isinstance(value, self.type):
            return (
                False,
                f"Parameter '{self.name}' must be {self.type.__name__}, got {type(value).__name__}",
            )

        return True, None


@dataclass(frozen=True)
class ToolResult:
    """
    Result from tool execution.

    Attributes:
        success: Whether execution succeeded
        data: Result data (dict, list, str, etc.)
        error: Error message if success=False
        metadata: Optional metadata (execution time, sources, etc.)
    """

    success: bool
    data: Any = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


class MusicalTool(ABC):
    """
    Abstract base class for all musical tools.

    Musical tools are deterministic functions that analyze audio,
    log sessions, search knowledge, or manipulate musical data.

    Subclasses must implement:
        - name: Unique tool identifier
        - description: Clear description for LLM tool selection
        - parameters: List of ToolParameter specs
        - execute(): Core tool logic

    Example:
        class AnalyzeTrack(MusicalTool):
            @property
            def name(self) -> str:
                return "analyze_track"

            def execute(self, **kwargs) -> ToolResult:
                # Extract BPM, key, energy
                return ToolResult(success=True, data={...})
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier (lowercase, underscores)."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        Human-readable description for LLM tool selection.

        This is critical — the LLM uses this to decide when to call the tool.
        Be specific about musical context and use cases.

        Good: "Extract BPM, musical key, and energy level from audio file metadata"
        Bad: "Analyze track"
        """
        pass

    @property
    @abstractmethod
    def parameters(self) -> list[ToolParameter]:
        """
        List of parameters this tool accepts.

        Order matters — positional parameters come first.
        """
        pass

    def validate_inputs(self, **kwargs) -> tuple[bool, str | None]:
        """
        Validate all input parameters.

        Args:
            **kwargs: Parameter values to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        for param in self.parameters:
            value = kwargs.get(param.name)
            is_valid, error = param.validate(value)
            if not is_valid:
                return False, error

        return True, None

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """
        Execute tool with validated parameters.

        Args:
            **kwargs: Tool parameters (already validated)

        Returns:
            ToolResult with success status and data
        """
        pass

    def __call__(self, **kwargs) -> ToolResult:
        """
        Execute tool with automatic validation.

        This is the main entry point — validates inputs then calls execute().

        Args:
            **kwargs: Tool parameters

        Returns:
            ToolResult (error if validation fails)
        """
        # Validate inputs
        is_valid, error = self.validate_inputs(**kwargs)
        if not is_valid:
            return ToolResult(success=False, error=error)

        # Execute
        try:
            return self.execute(**kwargs)
        except Exception as e:
            return ToolResult(success=False, error=f"Tool execution failed: {str(e)}")

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize tool for API/LLM consumption.

        Returns dict with name, description, parameters for tool_use API.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type.__name__,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                }
                for p in self.parameters
            ],
        }
