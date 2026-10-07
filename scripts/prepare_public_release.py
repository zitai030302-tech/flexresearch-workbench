"""Build a clean source snapshot with only code, fixtures, and selected docs."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ("app.py", "README.md", "LICENSE", "CONTRIBUTING.md", "SECURITY.md",
              "requirements.txt", "Dockerfile", "compose.yaml", "Makefile",
              ".gitignore", ".dockerignore", ".env.example", ".github/workflows/verify.yml")
DOCS = ("architecture.md", "agent-architecture.md", "deployment.md", "evaluation.md",
        "EVALUATION_DESIGN.md", "CURRENT_SYSTEM_AUDIT.md", "RUNTIME_VALIDATION.md",
        "COMPLETION_AUDIT.md", "showcase.md", "public-release.md")


def export(output):
    output = Path(output).resolve()
    if output.exists() or output.is_relative_to(ROOT):
        raise ValueError("choose a new directory outside the source repository")
    names = set(ROOT_FILES) | {"docs/" + name for name in DOCS}
    for directory, extensions in (("flexresearch", {".py"}), ("static", {".js", ".css", ".html"}),
                                  ("tests", {".py"}), ("eval", {".json", ".jsonl", ".csv"}),
                                  ("scripts", {".py"})):
        names.update(str(p.relative_to(ROOT)) for p in (ROOT / directory).rglob("*")
                     if p.suffix in extensions and p.is_file())
    names.update({"data/demo_strain_sensor.csv", "data/demo_spectral_responsivity.csv"})
    sources = {name: (ROOT / name).read_bytes() for name in sorted(names)}
    output.mkdir(parents=True)
    for name, raw in sources.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    manifest = {"scope": "code, generated fixtures, selected docs; no git history or lab vault",
                "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in sources.items()}}
    (output / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = export(args.output)
    print(f"Exported {len(manifest['files'])} files to {args.output}")
