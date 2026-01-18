from rag.assembler import assemble_prompt

def main():
    q = "if status is approved send email else send notification"
    p = assemble_prompt(q)
    print("Prompt length:", len(p))
    print(p[:800], "\n...\n")

if __name__ == "__main__":
    main()
