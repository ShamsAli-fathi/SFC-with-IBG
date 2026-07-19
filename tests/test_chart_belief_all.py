import importlib.util
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Chart" / "belief" / "all.py"
SPEC = importlib.util.spec_from_file_location("chart_belief_all", SCRIPT)
chart_belief_all = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(chart_belief_all)


def test_primary_input_discovers_one_ibg_file_beside_script(tmp_path, monkeypatch):
    chart_folder = tmp_path / "belief"
    chart_folder.mkdir()
    primary = chart_folder / "replica_results_IBG.csv"
    primary.write_text('"(1, 1)"\n"[0.25, 0.25, 0.25, 0.25]"\n', encoding="utf-8")
    monkeypatch.setattr(chart_belief_all, "SCRIPT_DIR", chart_folder)

    assert chart_belief_all.resolve_primary_input() == primary


def test_select_replicas_uses_the_configured_manual_replicas():
    runs = pd.DataFrame(
        {
            "(1, 1)": ["[0.25, 0.25, 0.25, 0.25]"],
            "(1, 4)": ["[0.25, 0.25, 0.25, 0.25]"],
        }
    )

    assert chart_belief_all.select_replicas(runs) == ["(1, 1)", "(1, 4)"]


def test_select_replicas_rejects_missing_requested_column():
    runs = pd.DataFrame({"(1, 1)": ["[0.25, 0.25, 0.25, 0.25]"]})

    with pytest.raises(ValueError, match="not found"):
        chart_belief_all.select_replicas(runs, ["(1, 1)", "(2, 18)"])


def test_render_preserves_all_state_colors_markers_and_raw_posteriors(
    tmp_path, monkeypatch
):
    output = tmp_path / "belief.png"
    runs = pd.DataFrame(
        {
            "(1, 1)": [
                "[1.0, 0.0, 0.0, 0.0]",
                "[0.0, 1.0, 0.0, 0.0]",
                "[0.0, 0.0, 1.0, 0.0]",
            ],
            "(2, 1)": [
                "[0.0, 0.0, 0.0, 1.0]",
                "[0.0, 0.0, 1.0, 0.0]",
                "[0.0, 1.0, 0.0, 0.0]",
            ],
        }
    )
    captured = {}
    original_subplots = chart_belief_all.plt.subplots

    def capture_subplots(*args, **kwargs):
        figure, axis = original_subplots(*args, **kwargs)
        captured["axis"] = axis
        return figure, axis

    monkeypatch.setattr(chart_belief_all.plt, "subplots", capture_subplots)
    chart_belief_all.render_all_beliefs(
        runs, output, replicas=["(1, 1)", "(2, 1)"]
    )

    axis = captured["axis"]
    assert output.exists()
    assert len(axis.lines) == 8
    assert [line.get_color() for line in axis.lines[:4]] == chart_belief_all.STATE_COLORS
    assert axis.lines[0].get_marker() == "o"
    assert axis.lines[4].get_marker() == "*"
    assert axis.lines[0].get_ydata().tolist() == pytest.approx([1.0, 0.0, 0.0])
    assert axis.xaxis.get_major_locator()._integer is True
    assert axis.get_xgridlines()[0].get_alpha() == 0.4
    assert axis.figure.get_size_inches().tolist() == [12.0, 6.0]
