"""
Tool registry with automatic discovery.

The registry discovers all MusicalTool subclasses and provides
lookup by name. No hardcoding — tools register themselves.
"""

import importlib
import inspect
import pkgutil
from pathlib import Path

from tools.base import MusicalTool


class ToolRegistry:
    """
    Registry for all musical tools with automatic discovery.

    Tools are discovered by scanning the tools/ directory for
    MusicalTool subclasses. No manual registration required.

    Usage:
        registry = ToolRegistry()
        registry.discover()  # Auto-discover all tools

        tool = registry.get("analyze_track")
        result = tool(file_path="/path/to/track.mp3")
    """

    def __init__(self):
        self._tools: dict[str, MusicalTool] = {}

    def register(self, tool: MusicalTool) -> None:
        """
        Register a tool instance.

        Args:
            tool: MusicalTool instance to register

        Raises:
            ValueError: If tool with same name already registered
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")

        self._tools[tool.name] = tool

    def get(self, name: str) -> MusicalTool | None:
        """
        Get tool by name.

        Args:
            name: Tool name

        Returns:
            MusicalTool instance or None if not found
        """
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        """
        List all registered tools.

        Returns:
            List of tool dicts (name, description, parameters)
        """
        return [tool.to_dict() for tool in self._tools.values()]

    def discover(self, package_name: str = "tools") -> int:
        """
        Auto-discover all MusicalTool subclasses in package.

        Scans all modules in the package and registers MusicalTool
        subclasses automatically. No manual imports needed.

        Args:
            package_name: Package to scan (default: "tools")

        Returns:
            Number of tools discovered
        """
        count = 0

        # Import the root package
        try:
            package = importlib.import_module(package_name)
        except ImportError:
            return 0

        # Get package path
        if not hasattr(package, "__path__"):
            return 0

        package_path = Path(package.__path__[0])

        # Recursively walk all modules
        for _finder, module_name, _is_pkg in pkgutil.walk_packages(
            [str(package_path)], prefix=f"{package_name}."
        ):
            try:
                # Import module
                module = importlib.import_module(module_name)

                # Find all MusicalTool subclasses
                for _name, obj in inspect.getmembers(module, inspect.isclass):
                    # Skip base class itself
                    if obj is MusicalTool:
                        continue

                    # Check if it's a MusicalTool subclass
                    if issubclass(obj, MusicalTool) and not inspect.isabstract(obj):
                        # Instantiate and register
                        tool_instance = obj()
                        self.register(tool_instance)
                        count += 1

            except (ImportError, AttributeError):
                # Skip modules that fail to import
                continue

        return count

    def __len__(self) -> int:
        """Return number of registered tools."""
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        """Check if tool is registered."""
        return name in self._tools


# Global registry instance
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """
    Get global tool registry singleton.

    Auto-discovers tools on first call.

    Returns:
        Initialized ToolRegistry
    """
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _registry.discover()
    return _registry
