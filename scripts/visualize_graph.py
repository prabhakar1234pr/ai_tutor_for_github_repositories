#!/usr/bin/env python3
"""
Utility script to visualize the LangGraph workflow.
Saves the graph visualization as a Mermaid diagram file.
"""

import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents.roadmap_agent import get_roadmap_graph


def main():
    """Generate and save Mermaid diagram."""
    print("🔨 Building roadmap graph...")
    graph = get_roadmap_graph()

    output_dir = Path(__file__).parent.parent / "graph_visualizations"
    output_dir.mkdir(exist_ok=True)

    # Generate Mermaid diagram
    print("📊 Generating Mermaid diagram...")
    mermaid_diagram = graph.get_graph().draw_mermaid()
    mermaid_file = output_dir / "roadmap_graph.mmd"
    mermaid_file.write_text(mermaid_diagram, encoding="utf-8")
    print(f"✅ Saved Mermaid diagram to: {mermaid_file}")
    print("   View it at: https://mermaid.live (paste the content)")


if __name__ == "__main__":
    main()
