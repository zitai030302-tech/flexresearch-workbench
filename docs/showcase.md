# Offline demo

The shortest useful demo is a measurement and its decision record. It does not need a model key or a literature API.

```bash
python -m pip install -r requirements.txt
python scripts/showcase.py --vault /tmp/flexresearch-showcase
```

Choose a new vault path for each run. This command refuses to reuse an existing directory or write under the repository. It clears provider credentials for the process, disables external source/model calls, seeds only labelled demo records, and starts the local server with debug and reloading disabled.

Open `http://127.0.0.1:8765/provenance`, choose the single DEMO project, then follow the measurement and draft decision. The strain-resistance CSV is generated sample data. The paper record demonstrates provenance links, not a claim extracted from that paper.

A three-minute walkthrough:

1. Show the project, sample, measurement, evidence card, and draft decision in the provenance view.
2. Open the workspace and inspect the CSV metrics and source hash.
3. Open decisions and inspect the frozen snapshot. Explain which parts came from the file and which require a reviewer.

Literature search and remote-model features are deliberately unavailable in this mode. Use the ordinary application entry point for those workflows.

To create the demo database without starting a server:

```bash
python scripts/showcase.py --vault /tmp/flexresearch-seed-check --seed-only
```
