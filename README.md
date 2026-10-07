# FlexResearch

A local research workspace for flexible-electronics experiments, literature, and data analysis.

I started this project because my own research workflow was split across papers, CSV files, experiment notes, plotting scripts, and repeated manual checks. The goal is to put those pieces behind one small, inspectable tool instead of treating a general chatbot as the source of truth.

## Current scope

FlexResearch currently supports:

- literature search through OpenAlex, Crossref, and Europe PMC
- local PDF/TXT/Markdown ingestion with source anchors
- CSV analysis for several common experimental data types
- experiment and sample records stored in SQLite
- evidence cards, benchmark tables, and reviewable decision records
- bounded model/tool calls for tasks such as filtering, FFT-based signal inspection, and I-V analysis
- local model-provider configuration with explicit fallbacks

The project is local-first. Imported lab files are not sent to a remote model unless that path is explicitly enabled.

## How it is organized

```text
Question / file
      ↓
intent routing
      ↓
retrieval or typed scientific tool
      ↓
result + source / file provenance
      ↓
reviewable experiment record
```

The model is not allowed to execute arbitrary Python. Numeric operations are handled by typed tools with explicit inputs, unit checks, and stored provenance.

A simplified project data chain is:

```text
Paper → Evidence → Protocol / Benchmark → Sample → Test → Result → Decision
```

## What I have verified

The engineering checkpoint recorded in the audit documents includes:

- 774 automated tests
- 92.66% statement coverage
- 84.45% branch coverage
- 65 golden cases, with 60 executed and passing
- 18 Chromium end-to-end flows
- real-process HTTP tests and SQLite lock-recovery tests

These numbers describe the software test suite, not scientific or clinical accuracy.

For the detailed verification record, see:

- [current system audit](docs/CURRENT_SYSTEM_AUDIT.md)
- [runtime validation](docs/RUNTIME_VALIDATION.md)
- [evaluation design](docs/EVALUATION_DESIGN.md)
- [engineering checklist](docs/COMPLETION_AUDIT.md)

## A few implemented workflows

### Experimental data

The data tools currently cover several bounded workflows, including:

- summary statistics and drift
- filtering with explicit sampling-rate checks
- FFT peak inspection
- gauge-factor and cycle-retention calculations
- I-V zero-bias differential resistance
- simple pulse-rate candidate extraction from an explicitly configured signal workflow

Outputs are tied to the selected source file and persisted with hashes where appropriate.

### Literature and evidence

The literature workspace can search public scholarly sources, save reading status and notes, create page/figure-anchored evidence cards, and export references in BibTeX or RIS format.

### Experiment records

Protocols and decision packets are reviewable objects rather than hidden model state. Generated plans begin as drafts and can be approved or rejected by a named reviewer.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open:

```text
http://127.0.0.1:8765
```

For browser tests:

```bash
python -m playwright install chromium
python -m pytest -q
```

For an isolated offline demo, use a new directory outside the repository:

```bash
python scripts/showcase.py --vault /tmp/flexresearch-showcase
```

Open `/provenance` to inspect the demo project, measurement and draft decision. Provider calls are disabled in this mode. See [the walkthrough](docs/showcase.md).

To seed demo records into the ordinary local workspace:

```bash
make demo-seed
```

For a reproducible local deployment:

```bash
docker compose up --build -d
```

## Repository map

```text
app.py          application entry point
static/         web interface
tests/          unit, integration, golden, and browser tests
docs/           architecture, evaluation, and method notes
scripts/        benchmark and local helper scripts
data/           tracked demo data; local databases/uploads are ignored
```

## Important boundaries

This is research software, not a clinical system or an autonomous laboratory controller.

A few boundaries are intentional:

- experiment suggestions require human review
- missing sampling rates or units should produce clarification rather than guessed values
- image-only PDFs are not silently treated as parsed text
- literature search does not make a paper reliable by itself
- the pulse workflow reports a signal-derived rate candidate, not a validated medical measurement
- private research material should not be uploaded to an unapproved remote provider

More detailed method notes live in `docs/` rather than in this README.

## Why this project exists

The part I care about most is not adding more chat features. It is making a research workflow easier to reproduce: knowing which file was analyzed, which parameters were used, where a claim came from, and what changed between two runs.

## License

MIT

