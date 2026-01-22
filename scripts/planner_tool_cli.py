import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from planner_tool import run_planner_full

def main():
    q = input("Enter query: ").strip()
    if not q:
        print("Empty query.")
        return

    result = run_planner_full(q, debug=True)

    print("\n=== ROUTING ===")
    print(result["routing"])

    print("\n=== MANIFEST ===")
    print(result["manifest_path"])

    print("\n=== OUTPUT ===\n")
    print(result["llm_output"])  # or print(result["prompt"]) for assembled prompt


    #uv run python -m scripts.planner_tool_cli