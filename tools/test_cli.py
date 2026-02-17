"""
Simple CLI to test tool registry and execution.

Usage:
    python -m tools.test_cli
"""

from tools.registry import get_registry


def main():
    """Test tool registry and analyze_track tool."""
    print("=" * 70)
    print("TOOL REGISTRY TEST")
    print("=" * 70)

    # Get global registry (auto-discovers tools)
    registry = get_registry()

    print(f"\n✅ Discovered {len(registry)} tool(s)\n")

    # List all tools
    print("Available tools:")
    for tool_dict in registry.list_tools():
        print(f"\n  • {tool_dict['name']}")
        print(f"    {tool_dict['description']}")
        params = ", ".join([p["name"] for p in tool_dict["parameters"]])
        print(f"    Parameters: {params}")

    # Test analyze_track
    print("\n" + "=" * 70)
    print("ANALYZE_TRACK TEST")
    print("=" * 70)

    tool = registry.get("analyze_track")
    if not tool:
        print("❌ analyze_track not found")
        return

    test_files = [
        "progressive_house_128bpm_Aminor_energy8.mp3",
        "techno_140bpm_Cmajor.wav",
        "track_125bpm.mp3",
        "ambient.flac",
        "Lane 8 - Brightest Lights (128 bpm, A minor).mp3",
    ]

    for filename in test_files:
        result = tool(file_path=filename)

        if result.success:
            data = result.data
            print(f"\n📁 {filename}")
            print(f"   BPM: {data['bpm']}")
            print(f"   Key: {data['key']}")
            print(f"   Energy: {data['energy']}")
            print(f"   Confidence: {data['confidence']}")
        else:
            print(f"\n❌ {filename}: {result.error}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
