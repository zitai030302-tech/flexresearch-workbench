# Evaluation and acceptance checks

Current engineering acceptance and measured denominators are in [COMPLETION_AUDIT.md](COMPLETION_AUDIT.md) and [EVALUATION_DESIGN.md](EVALUATION_DESIGN.md). The benchmarks below are separate entry points, not proof that their full live suites have just passed.

The test suite checks deterministic behavior rather than only visual output.

| Capability | Check |
| --- | --- |
| Research session persistence | research call creates user/assistant messages and a run trace |
| Stateful workflow trace | Planner, Local Retriever, Researcher, Source Critic, Synthesizer are observable stages, not independent agents |
| Intent routing | product questions never call scholarly APIs; knowledge answers do not append papers; only explicit literature intent starts scholarly retrieval |
| Unified chat default | `/` serves one conversation composer; sources are labelled by provider and collapsed by default |
| Source provenance calibration | every external candidate stores an explainable metadata-completeness score and missing-field flags; it is never presented as a science-quality score |
| DOI paper library | DOI import is normalized through Crossref, persists quality metadata and exports valid BibTeX/RIS records |
| Evidence-card review gate | a card must target exactly one paper/document and moves out of draft only through named review |
| Project provenance graph | graph endpoint emits only explicit project/database/snapshot relationships and is covered for paper → evidence → decision and sample → measurement → decision edges |
| Research-object export | decision packet exports a JSON-LD RO-Crate-style manifest with source DOI links and measurement hashes, without embedding private raw files |
| Benchmark comparability guard | summary groups only exact metric/unit pairs and flags missing conditions, unverified DOI records and insufficient comparison count |
| Live-source adapter boundary | OpenAlex title discovery and Crossref fallback are mockable; live smoke test is run separately |
| Model connection diagnostics | provider API hides credentials, flags random free routing as demo-only, and probe returns actual model + latency |
| Private-document provenance | ingest creates chunks; retrieval emits `local:<doc>#<chunk>` citations |
| Report reproducibility | exported Markdown includes Agent trace and source provenance |
| Streamed orchestration | SSE emits run-started, agent state, and final-result events |
| Approval boundary | only draft protocols can be approved/rejected; every action has an audit record |
| Data analysis | I–V, strain-resistance, cycle, spectral-responsivity classifications and sample links are tested; optoelectronic FWHM is labelled as a discrete-sampling approximation |
| Raw-data integrity | every archived measurement can be re-hashed through a read-only endpoint; a stored fingerprint alone is not treated as sufficient evidence |

Run locally:

```bash
python -m compileall -q app.py tests
python -m pytest -q
```

Then, with the local server already running, run the real HTTP/provider acceptance suite:

```bash
make verify-live
```

## Basic live benchmark

With the local service running, use the repeatable chat benchmark instead of judging one lucky response:

```bash
make benchmark
```

`flexresearch-basic-chat-v1` measures five HTTP-level contracts: identity and model questions do not search, the direct dark-current answer stays condition-aware, the configured model gives a concise mobility answer without literature search, and a recent-literature request returns at least three in-domain OpenAlex records (or Crossref fallback records) with clickable URLs. The report includes the configured and actually routed model, per-case latency, pass rate, and a non-zero exit code on regression.

## Open-source DeepResearch Bench prompts

The repository also includes a live adapter for [DeepResearch Bench](https://github.com/Ayanami0730/deep_research_bench), a public 100-task benchmark for deep-research agents. Run it against a running local service:

```bash
make benchmark-drb
```

The default three-task slice uses public electronics-readout, thin-film-process, and lithium-niobate-photonics prompts. It checks that each live result has at least three query-matched, clickable candidates and retains the title-level evidence boundary. This is deliberately **not** an official RACE/FACT score: the upstream official evaluator needs separate judge-model and Jina scraping credentials. The JSON report labels that limit explicitly instead of presenting a self-score as a leaderboard result.

## Isolated lab-workflow benchmark

```bash
make benchmark-lab
```

This benchmark starts a disposable local server with a temporary data directory, uploads a real I–V CSV and a text-bearing PDF, then verifies CSV analysis, SHA-256 integrity, PDF page-one anchoring, local evidence retrieval, and exported-report provenance. The temporary database and uploaded files are removed after the run.

## Model-provider boundary benchmark

```bash
make benchmark-provider
```

This starts both a temporary FlexResearch service and a local OpenAI-compatible mock. It proves that `/api/providers` never returns the API key, a model switch is used on the very next chat request, the probe reports the routed model, and an HTTP 503 produces the visible local fallback rather than a fabricated model answer.

For a live smoke test, submit “找最近的柔性电子论文” from `/`; the collapsed source block should read `OpenAlex · N` and the returned titles should be in-domain. Submit “谁做的你” and verify there is no source block. Use `API · Online → 测试连接` to record the actual configured model and latency. Network failure is represented as a trace warning or a clear no-answer state, never a fabricated answer.

