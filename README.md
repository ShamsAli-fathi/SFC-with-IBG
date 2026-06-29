# SFC-with-IBG

Migration of the decoupled Indian Buffet Game simulation into a lightweight Kubernetes testbed. See `ARCHITECTURE.md` for the target design and `ROADMAP.md` for the gated implementation sequence.

## Python environment

From the repository root in WSL:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run the focused characterization suite with:

```bash
python -m pytest -q
```

Run one local HTTP replica with:

```bash
STAGE=1 REPLICA_ID=1 POD_NAME=stage-1-0 \
  STATE=4 CAPACITY=2000 \
  python -m uvicorn testbed.cnf_service:app --host 127.0.0.1 --port 8080
```

The service exposes `GET /health` and `POST /process`.

The files directly under `IBG/` remain the reference simulation. The budgeted/coupled path is outside the current migration scope.
