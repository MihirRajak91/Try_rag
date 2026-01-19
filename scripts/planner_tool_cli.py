import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from planner_tool import run_planner_full


def main():
    q = input("Enter query: ").strip()
    if not q:
        print("Empty query.")
        return

    result = run_planner_full(q, debug_prompt=False, save_manifest=True)

    print("\n=== ROUTING ===")
    print(result.routing)

    print("\n=== MANIFEST ===")
    print(result.manifest_path)

    print("\n=== OUTPUT ===\n")
    print(result.plan_markdown)

if __name__ == "__main__":
    q = input("Enter query: ").strip()
    if not q:
        print("Empty query.")
        raise SystemExit(1)

    result = run_planner_full(q, debug=True)

    print("\n=== ROUTING RESULT ===")
    print(result["routing"])

    print("\n=== AUDIT ===")
    print(result["audit"])

    print("\n=== MANIFEST SAVED ===")
    print(result["manifest_path"])

    print("\n=== ASSEMBLED PROMPT ===\n")
    print(result["prompt"])

    print("\n=== LLM OUTPUT ===\n")
    print(result["llm_output"])

    #uv run python -m scripts.planner_tool_cli