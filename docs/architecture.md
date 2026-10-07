# Architecture decision record

## Why this first version is local and deterministic

The first deliverable needs to be demonstrable in a laboratory and credible on GitHub. It therefore starts with a small Flask application, public citations and transparent calculations—not a black-box autonomous agent.

```text
Browser UI
  ├─ POST /api/assistant  → local question routing + public/private evidence separation
  ├─ GET /api/literature  → curated public evidence + source URL
  ├─ POST /api/plan       → direction-specific review checklist
  └─ POST /api/analyze    → I–V / strain / cycle / spectral-response CSV parsing + transparent metrics + local raw-file fingerprint
  ├─ POST /api/projects   → local project registry (SQLite)
  ├─ POST /api/samples    → project-linked sample IDs and process metadata
  ├─ POST /api/documents  → local text/PDF ingestion + SHA-256 fingerprint
  └─ GET /api/private-search → transparent local keyword search
```

## Production boundary

```text
Approved lab documents ─┐
Measurements / samples ─┼─> access-controlled data store ─> retrieval service
Public literature ──────┘                                  └> cited response draft
                                                             ↓
                                                        researcher approval
```

The model, if added, must only draft responses with per-claim citations. Experimental execution, chemical safety decisions, medical interpretations and publication claims remain human responsibilities.

## Data model to implement next

| Object | Minimum fields |
| --- | --- |
| `Paper` | DOI, source URL, claim excerpt, permission status |
| `Material` | composition, batch, supplier, safety note |
| `Device` | architecture, area, substrate, sample ID |
| `Process` | SOP version, parameters, operator, timestamp |
| `Test` | instrument, calibration, protocol, environment |
| `Result` | raw-file hash, calculation version, reviewer |

