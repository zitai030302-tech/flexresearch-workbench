# Public snapshot

Use `python scripts/prepare_public_release.py --output /tmp/flexresearch-public` to build a new directory containing application code, static files, tests, generated fixtures, scripts, and selected method/verification docs. `RELEASE_MANIFEST.json` records every file hash.

The export excludes Git history, `.env`, databases, provider settings, uploads, measurements, logs, and personal learning/interview notes. Only the two tracked `data/demo_*.csv` fixtures are included from the data directory. Existing output directories are rejected.

The tracked source snapshot was checked for common key/private-key patterns, internal IP addresses, local user paths, and unexpected data files. The detected local-path/key strings in conversation-context tests are deliberately synthetic rejection fixtures. This content check does not certify the entire private Git history; the release uses a fresh history instead.

Validate the exported directory, not only the original workspace:

```bash
cd /tmp/flexresearch-public
python -m pytest -q
python scripts/run_agent_eval.py
python scripts/showcase.py --vault /tmp/flexresearch-public-demo --seed-only
```

Keep the MIT license and all software/scientific limitations. Verification documents describe historical checkpoints; current counts and pass/fail status must come from the run being cited.
