"""Start an isolated, offline showcase without opening the user's lab vault."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def configure(vault):
    vault = Path(vault).expanduser().resolve()
    if vault.is_relative_to(ROOT):
        raise ValueError("choose a showcase vault outside the source repository")
    if vault.exists():
        raise ValueError("choose a new directory; existing vaults are never reused")
    vault.mkdir(parents=True)
    os.environ["FLEXRESEARCH_DATA_DIR"] = str(vault)
    # Empty values override .env loading, including alternate provider keys.
    for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL",
                 "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL", "OPENALEX_API_KEY"):
        os.environ[name] = ""
    return vault


def start(vault, port=8765, seed_only=False):
    vault = configure(vault)
    sys.path.insert(0, str(ROOT))
    import app as application
    from scripts.seed_showcase import main as seed

    def offline(*_args, **_kwargs):
        raise ValueError("Offline showcase: external providers are disabled")

    application.request_json = offline
    application.request_model_json = offline
    application.init_db()
    seed()
    print(f"Isolated showcase vault: {vault}")
    if not seed_only:
        application.app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--seed-only", action="store_true")
    args = parser.parse_args()
    start(args.vault, args.port, args.seed_only)
