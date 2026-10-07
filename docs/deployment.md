# Deployment guide

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
make run
```

## Docker deployment for a lab workstation

```bash
docker compose up --build -d
```

Open `http://127.0.0.1:8765/workspace` on the host. Persistent lab data is stored in the named Docker volume `flexresearch-data`, not inside the container image.

## Separate data vaults

Set `FLEXRESEARCH_DATA_DIR` to place the local SQLite vault, uploads and measurements outside the repository. This is useful for a per-user workstation vault or for testing the public showcase without touching a lab vault:

```bash
FLEXRESEARCH_DATA_DIR="$HOME/flexresearch-demo" make demo-seed
FLEXRESEARCH_DATA_DIR="$HOME/flexresearch-demo" make run
```

The showcase script always reads the tracked public CSV source from the repository, but writes its `DEMO` records only to the selected vault.

## Data and model-provider controls

- The optional `.env` is mounted as environment variables and excluded from the image and Git.
- For a private lab deployment, bind the service only to a trusted local network and put authentication/reverse-proxy controls in front of it before exposing it beyond the lab.
- Back up the `flexresearch-data` volume according to your laboratory data policy.
- Rotate model API keys after suspected exposure; never add them to screenshots, commits, or issue reports.

