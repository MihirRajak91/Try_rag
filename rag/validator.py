# rag/validator.py
REQUIRED_KEYS = {
    "doc_type",
    "topic",
    "priority",
    "role",
    "data",
    "text",
}


def validate_chunks(chunks):
    errors = []

    for i, ch in enumerate(chunks):
        missing = REQUIRED_KEYS - ch.keys()
        if missing:
            errors.append(f"Chunk[{i}] missing keys: {missing}")

        if not isinstance(ch.get("data"), str) or not ch["data"].strip():
            errors.append(f"Chunk[{i}] has empty data")

        if not isinstance(ch.get("text"), str) or not ch["text"].strip():
            errors.append(f"Chunk[{i}] has empty text")

        if not isinstance(ch.get("priority"), int):
            errors.append(f"Chunk[{i}] priority must be int")

        if ch.get("role") not in {"router", "support", "static"}:
            errors.append(f"Chunk[{i}] invalid role: {ch.get('role')}")

    if errors:
        raise ValueError(
            "❌ Chunk validation failed:\n" + "\n".join(errors)
        )

    return True
