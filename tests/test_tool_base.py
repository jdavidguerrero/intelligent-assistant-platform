"""
Tests for tool base classes and validation.
"""

from tools.base import MusicalTool, ToolParameter, ToolResult


class TestToolParameter:
    """Test ToolParameter validation."""

    def test_required_parameter_missing(self):
        """Required parameter with None should fail validation."""
        param = ToolParameter(name="file_path", type=str, description="Path to file", required=True)

        is_valid, error = param.validate(None)
        assert not is_valid
        assert "Required parameter 'file_path' is missing" in error

    def test_required_parameter_present(self):
        """Required parameter with value should pass validation."""
        param = ToolParameter(name="file_path", type=str, description="Path to file", required=True)

        is_valid, error = param.validate("/path/to/file.mp3")
        assert is_valid
        assert error is None

    def test_optional_parameter_missing(self):
        """Optional parameter with None should pass validation."""
        param = ToolParameter(
            name="limit", type=int, description="Result limit", required=False, default=10
        )

        is_valid, error = param.validate(None)
        assert is_valid
        assert error is None

    def test_type_mismatch(self):
        """Parameter with wrong type should fail validation."""
        param = ToolParameter(name="limit", type=int, description="Result limit", required=True)

        is_valid, error = param.validate("not_an_int")
        assert not is_valid
        assert "must be int, got str" in error

    def test_correct_type(self):
        """Parameter with correct type should pass validation."""
        param = ToolParameter(name="limit", type=int, description="Result limit", required=True)

        is_valid, error = param.validate(10)
        assert is_valid
        assert error is None


class TestToolResult:
    """Test ToolResult data structure."""

    def test_success_result(self):
        """Successful result with data."""
        result = ToolResult(success=True, data={"bpm": 128}, metadata={"source": "test"})

        assert result.success is True
        assert result.data == {"bpm": 128}
        assert result.error is None
        assert result.metadata == {"source": "test"}

    def test_failure_result(self):
        """Failed result with error message."""
        result = ToolResult(success=False, error="File not found")

        assert result.success is False
        assert result.data is None
        assert result.error == "File not found"


class DummyTool(MusicalTool):
    """Dummy tool for testing base class."""

    @property
    def name(self) -> str:
        return "dummy_tool"

    @property
    def description(self) -> str:
        return "A dummy tool for testing"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="text", type=str, description="Some text", required=True),
            ToolParameter(
                name="count", type=int, description="A number", required=False, default=1
            ),
        ]

    def execute(self, **kwargs) -> ToolResult:
        """Echo back the inputs."""
        return ToolResult(success=True, data=kwargs)


class TestMusicalTool:
    """Test MusicalTool base class."""

    def test_tool_properties(self):
        """Tool should expose name, description, parameters."""
        tool = DummyTool()

        assert tool.name == "dummy_tool"
        assert "dummy tool" in tool.description.lower()
        assert len(tool.parameters) == 2

    def test_validate_inputs_success(self):
        """Valid inputs should pass validation."""
        tool = DummyTool()

        is_valid, error = tool.validate_inputs(text="hello", count=5)
        assert is_valid
        assert error is None

    def test_validate_inputs_missing_required(self):
        """Missing required parameter should fail validation."""
        tool = DummyTool()

        is_valid, error = tool.validate_inputs(count=5)  # Missing 'text'
        assert not is_valid
        assert "Required parameter 'text' is missing" in error

    def test_validate_inputs_wrong_type(self):
        """Wrong parameter type should fail validation."""
        tool = DummyTool()

        is_valid, error = tool.validate_inputs(text="hello", count="not_an_int")
        assert not is_valid
        assert "must be int" in error

    def test_call_with_valid_inputs(self):
        """Calling tool with valid inputs should succeed."""
        tool = DummyTool()

        result = tool(text="hello", count=3)
        assert result.success is True
        assert result.data == {"text": "hello", "count": 3}

    def test_call_with_invalid_inputs(self):
        """Calling tool with invalid inputs should return error."""
        tool = DummyTool()

        result = tool(count=5)  # Missing 'text'
        assert result.success is False
        assert "Required parameter" in result.error

    def test_to_dict(self):
        """Tool should serialize to dict for API."""
        tool = DummyTool()

        data = tool.to_dict()
        assert data["name"] == "dummy_tool"
        assert "dummy tool" in data["description"].lower()
        assert len(data["parameters"]) == 2
        assert data["parameters"][0]["name"] == "text"
        assert data["parameters"][0]["required"] is True


class FailingTool(MusicalTool):
    """Tool that raises exception during execution."""

    @property
    def name(self) -> str:
        return "failing_tool"

    @property
    def description(self) -> str:
        return "A tool that always fails"

    @property
    def parameters(self) -> list[ToolParameter]:
        return []

    def execute(self, **kwargs) -> ToolResult:
        """Raise exception."""
        raise RuntimeError("Intentional failure")


class TestMusicalToolErrorHandling:
    """Test error handling in tool execution."""

    def test_exception_in_execute(self):
        """Exception during execute should be caught and returned as error."""
        tool = FailingTool()

        result = tool()
        assert result.success is False
        assert "Tool execution failed" in result.error
        assert "Intentional failure" in result.error
