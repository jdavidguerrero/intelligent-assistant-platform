"""
Tests for tool registry and auto-discovery.
"""

import pytest

from tools.base import MusicalTool, ToolParameter, ToolResult
from tools.registry import ToolRegistry


class SimpleTool(MusicalTool):
    """Simple tool for testing registry."""

    @property
    def name(self) -> str:
        return "simple_tool"

    @property
    def description(self) -> str:
        return "A simple test tool"

    @property
    def parameters(self) -> list[ToolParameter]:
        return []

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, data={"result": "simple"})


class AnotherTool(MusicalTool):
    """Another tool for testing registry."""

    @property
    def name(self) -> str:
        return "another_tool"

    @property
    def description(self) -> str:
        return "Another test tool"

    @property
    def parameters(self) -> list[ToolParameter]:
        return []

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, data={"result": "another"})


class TestToolRegistry:
    """Test ToolRegistry registration and lookup."""

    def test_register_tool(self):
        """Should register a tool instance."""
        registry = ToolRegistry()
        tool = SimpleTool()

        registry.register(tool)

        assert len(registry) == 1
        assert "simple_tool" in registry

    def test_register_duplicate_raises(self):
        """Registering duplicate tool name should raise ValueError."""
        registry = ToolRegistry()
        tool1 = SimpleTool()
        tool2 = SimpleTool()

        registry.register(tool1)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(tool2)

    def test_get_tool(self):
        """Should retrieve registered tool by name."""
        registry = ToolRegistry()
        tool = SimpleTool()
        registry.register(tool)

        retrieved = registry.get("simple_tool")

        assert retrieved is not None
        assert retrieved.name == "simple_tool"

    def test_get_nonexistent_tool(self):
        """Getting non-existent tool should return None."""
        registry = ToolRegistry()

        retrieved = registry.get("nonexistent")

        assert retrieved is None

    def test_list_tools(self):
        """Should list all registered tools."""
        registry = ToolRegistry()
        tool1 = SimpleTool()
        tool2 = AnotherTool()
        registry.register(tool1)
        registry.register(tool2)

        tools = registry.list_tools()

        assert len(tools) == 2
        names = [t["name"] for t in tools]
        assert "simple_tool" in names
        assert "another_tool" in names

    def test_len(self):
        """Should return number of registered tools."""
        registry = ToolRegistry()

        assert len(registry) == 0

        registry.register(SimpleTool())
        assert len(registry) == 1

        registry.register(AnotherTool())
        assert len(registry) == 2

    def test_contains(self):
        """Should check if tool is registered."""
        registry = ToolRegistry()
        registry.register(SimpleTool())

        assert "simple_tool" in registry
        assert "nonexistent" not in registry


class TestToolRegistryDiscovery:
    """Test auto-discovery of tools."""

    def test_discover_real_tools(self):
        """Should discover actual tools in tools/ directory."""
        registry = ToolRegistry()

        count = registry.discover("tools")

        # Should find at least analyze_track
        assert count >= 1
        assert "analyze_track" in registry

    def test_discover_nonexistent_package(self):
        """Discovery on non-existent package should return 0."""
        registry = ToolRegistry()

        count = registry.discover("nonexistent_package")

        assert count == 0
        assert len(registry) == 0
