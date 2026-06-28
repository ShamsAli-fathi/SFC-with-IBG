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

The files directly under `IBG/` remain the reference simulation. The budgeted/coupled path is outside the current migration scope.
