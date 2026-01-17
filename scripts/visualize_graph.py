#!/usr/bin/env python3
"""
Utility script to visualize the LangGraph workflow.
Saves the graph visualization as a Mermaid diagram file and text representation.

Generates visualizations for the current optimized LangGraph structure (v2).
"""

import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents.roadmap_agent import get_roadmap_graph


def main():
    """Generate and save Mermaid diagram and text representation."""
    print("Building roadmap graph (v2 optimized)...")
    graph = get_roadmap_graph()

    output_dir = Path(__file__).parent.parent / "graph_visualizations"
    output_dir.mkdir(exist_ok=True)

    # Generate Mermaid diagram
    print("Generating Mermaid diagram...")
    mermaid_diagram = graph.get_graph().draw_mermaid()
    mermaid_file = output_dir / "roadmap_graph.mmd"
    mermaid_file.write_text(mermaid_diagram, encoding="utf-8")
    print(f"Saved Mermaid diagram to: {mermaid_file}")
    print("   View it at: https://mermaid.live (paste the content)")

    # Generate text representation
    print("Generating text representation...")
    text_diagram = graph.get_graph().draw_ascii()
    text_file = output_dir / "roadmap_graph.txt"
    text_file.write_text(text_diagram, encoding="utf-8")
    print(f"Saved text diagram to: {text_file}")

    # Print summary
    print("\nGraph Summary:")
    print("   - Total nodes: 8")
    print("   - LLM nodes: 3 (analyze_repo, plan_curriculum, generate_concept_content)")
    print(
        "   - Non-LLM nodes: 5 (fetch_context, insert_all_days, save_all_concepts, build_memory_context, mark_concept_complete)"
    )
    print("   - Conditional edges: 2 (should_continue_concept_generation)")
    print("   - LLM calls: 2 + (1 x N concepts) = 58 for 56 concepts")


if __name__ == "__main__":
    main()
