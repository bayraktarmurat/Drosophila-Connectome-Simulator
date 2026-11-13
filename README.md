# Connectome Circuit Explorer

Interactive LIF simulator, signal-path finder and virtual lesions on sub-circuits of the MaleCNS *Drosophila* connectome (`male-cns:v1.0`). The first circuit is the Giant Fiber escape circuit. Work in progress: the full README arrives in Phase 6.

## Setup

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -e ".[dev,fetch]"
```

### neuPrint token
Get your token from neuprint.janelia.org → Account. Store it **only** as an environment variable; never put it in code or notebooks:

```bash
read -s 'T?Paste your neuPrint token: ' && echo "export NEUPRINT_APPLICATION_CREDENTIALS=\"$T\"" >> ~/.zshrc && unset T && source ~/.zshrc
```

## Fetch data (one-time, needs the token)

```bash
.venv/bin/python scripts/fetch_circuit.py --config giant_fiber
```

This writes `data/giant_fiber/{neurons,edges}.parquet` plus `manifest.json`. After that, the app runs offline and never calls neuPrint.

## Tests

```bash
.venv/bin/python -m pytest
```

## Docs
- `docs/ASSUMPTIONS.md`: every modelling assumption
- `docs/NOTES.md`: learning notes (Turkish)
