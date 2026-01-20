# scripts/run_planner_agent.py
from planner.crew import build_crew

def main():
    q = input("Enter query: ").strip()
    if not q:
        print("Empty query.")
        return

    crew = build_crew()
    result = crew.kickoff(inputs={"query": q})

    print("\n=== PLAN ===\n")
    print(result)

if __name__ == "__main__":
    main()
