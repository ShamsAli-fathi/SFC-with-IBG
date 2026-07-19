import importlib.util
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Chart" / "sla-small" / "2" / "sla-small.py"
SPEC = importlib.util.spec_from_file_location("chart_sla_small_v2", SCRIPT)
chart_sla_small_v2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(chart_sla_small_v2)


def test_load_sla_runs_preserves_current_headered_columns(tmp_path):
    source = tmp_path / "sla_IBG.csv"
    source.write_text("run_a,run_b\n1,3\n2,4\n", encoding="utf-8")

    runs = chart_sla_small_v2.load_sla_runs(source)

    assert list(runs.columns) == ["run_a", "run_b"]
    assert runs.iloc[1].tolist() == [2, 4]


def test_primary_input_discovers_one_ibg_file_beside_script(tmp_path, monkeypatch):
    chart_folder = tmp_path / "sla-small"
    chart_folder.mkdir()
    primary = chart_folder / "sla_IBG.csv"
    primary.write_text("run_a\n1\n", encoding="utf-8")
    monkeypatch.setattr(chart_sla_small_v2, "SCRIPT_DIR", chart_folder)

    assert chart_sla_small_v2.resolve_primary_input() == primary


def test_absent_milp_is_optional(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_sla_small_v2, "SCRIPT_DIR", tmp_path)

    assert chart_sla_small_v2.load_optional_milp() is None


def test_render_preserves_moving_average_and_original_theme(tmp_path, monkeypatch):
    output = tmp_path / "sla.png"
    captured = {}
    original_subplots = chart_sla_small_v2.plt.subplots

    def capture_subplots(*args, **kwargs):
        figure, axis = original_subplots(*args, **kwargs)
        captured["figure"] = figure
        captured["axis"] = axis
        return figure, axis

    monkeypatch.setattr(chart_sla_small_v2.plt, "subplots", capture_subplots)
    chart_sla_small_v2.render_sla_plot(
        pd.DataFrame({"run_a": [1, 3, 5], "run_b": [3, 5, 7]}),
        output,
        milp=pd.DataFrame([[0.0]]),
    )

    axis = captured["axis"]
    assert output.exists()
    assert axis.lines[0].get_ydata().tolist() == pytest.approx([2.0, 3.0, 4.0])
    assert axis.lines[0].get_color() == "orange"
    assert axis.lines[1].get_ydata().tolist() == [0.0, 0.0, 0.0]
    assert axis.get_legend()._loc == 1  # upper right
    assert axis.get_xgridlines()[0].get_alpha() == 0.5
    assert captured["figure"].get_size_inches().tolist() == [12.0, 6.0]
