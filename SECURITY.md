# Security and data-boundary notes

FlexResearch is a local-first research workflow prototype. It is not an ELN, LIMS, clinical system, identity provider, or autonomous instrument controller.

## Data classification before deployment

| Data class | Default handling | External transfer |
| --- | --- | --- |
| Public DOI metadata and user-entered search query | Crossref / Europe PMC lookup | allowed by the relevant source connector |
| Imported PDFs, SOPs, CSVs and local evidence chunks | local `data/` database and uploads directory | never sent by the included model adapter |
| Question + selected public metadata | optional OpenAI-compatible synthesis adapter | sent only if a user explicitly enables the model toggle and configures a provider |
| Human-review names and notes | local SQLite audit records | local only by default |

Do not upload unpublished manuscripts, collaboration-restricted data, identifiers, clinical data, raw participant data, instrument credentials or confidential SOPs to an external provider unless your laboratory has approved that exact transfer.

## Deployment boundary

The current application intentionally has **no built-in multi-user authentication or role-based access control**. Treat it as a single-user workstation application, or put it behind your laboratory's authenticated reverse proxy/VPN before exposing it beyond a trusted private network.

For a group deployment, the minimum operational baseline is:

1. Place the service behind institutional SSO or a reverse proxy with TLS and access logging.
2. Store `.env`, SQLite backups and uploaded files on an approved encrypted volume.
3. Restrict filesystem ownership to the service account; do not mount a shared writeable folder into a public container.
4. Configure backups and restore drills before collecting valuable records.
5. Use named reviewers for protocols, evidence cards and decision packets; do not treat a model output as approval.

## Secrets

- `.env` is ignored by Git. Start from `.env.example`; never place a real key in documentation, screenshots, commits, issue reports or chat logs.
- Keys supplied in a chat should be treated as exposed and rotated in the provider console.
- Use a dedicated, quota-limited key for development instead of a personal or shared production key.

## Reporting a concern

Do not post suspected secrets or private lab data in a public issue. Contact the repository maintainer through a private institutional channel, include only the minimum reproduction detail, and rotate any exposed credential first.

