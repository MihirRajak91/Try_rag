# rag/manifest.py
import json
import os
import time
from typing import Any, Dict, Optional


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_manifest(out_dir: str, manifest: Dict[str, Any], filename: Optional[str] = None) -> str:
    ensure_dir(out_dir)

    if not filename:
        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = f"prompt_manifest_{ts}.json"

    path = os.path.join(out_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return path
