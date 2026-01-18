# scripts/run_planner.py
import os
from dotenv import load_dotenv
from openai import OpenAI

from rag.assembler import assemble_prompt

load_dotenv()

MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))

def main():
    q = input("Enter query: ").strip()
    if not q:
        print("Empty query.")
        return

    prompt = assemble_prompt(q, debug=False)

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=TEMPERATURE,
        messages=[
            {"role": "system", "content": "You are a precise workflow planner. Output Markdown only."},
            {"role": "user", "content": prompt},
        ],
    )

    print("\n=== PLANNER OUTPUT ===\n")
    print(resp.choices[0].message.content)

if __name__ == "__main__":
    main()
