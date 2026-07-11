# SFC-with-IBG

SFC-with-IBG testbed development. The current implemented path migrates the active decoupled Indian Buffet Game simulation into a lightweight Kubernetes testbed. See [Tutorial.md](Tutorial.md) for the beginner-friendly usage guide, `ARCHITECTURE.md` for the target design, and `ROADMAP.md` for the gated implementation sequence.

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

## Local three-hop testbed

Build and start one flow generator and one replica for each stage on a private container network:

```bash
docker compose -f deploy/local/compose.yaml up --build --detach --wait
.venv/bin/python scripts/phase4_smoke.py
docker compose -f deploy/local/compose.yaml down --remove-orphans
```

The smoke test sends three logical flows concurrently. Each flow visits its selected stage 1, 2, and 3 replicas sequentially and returns correlated per-hop telemetry.

The files directly under `IBG/` remain the reference simulation. The budgeted/coupled path is outside the current migration scope unless a future task explicitly brings it in.
