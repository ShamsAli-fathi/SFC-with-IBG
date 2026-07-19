import importlib.util
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Chart" / "util-small" / "util-small.py"
SPEC = importlib.util.spec_from_file_location("chart_util_small", SCRIPT)
chart_util_small = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(chart_util_small)


def test_load_utility_runs_preserves_current_headered_run_columns(tmp_path):
    source = tmp_path / "realized_end_to_end_utility_IBG.csv"
    source.write_text("run_a,run_b\n10,20\n30,40\n", encoding="utf-8")

    runs = chart_util_small.load_utility_runs(source)

    assert list(runs.columns) == ["run_a", "run_b"]
    assert runs.iloc[1].tolist() == [30, 40]


def test_primary_input_discovers_one_ibg_file_beside_script(tmp_path, monkeypatch):
    chart_folder = tmp_path / "util-small"
    chart_folder.mkdir()
    primary = chart_folder / "realized_end_to_end_utility_IBG.csv"
    primary.write_text("run_a\n10\n", encoding="utf-8")
    monkeypatch.setattr(chart_util_small, "SCRIPT_DIR", chart_folder)

    assert chart_util_small.resolve_primary_input() == primary


def test_absent_milp_is_optional(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_util_small, "SCRIPT_DIR", tmp_path)

    assert chart_util_small.load_optional_milp() is None


def test_render_preserves_original_ibg_theme_and_std_band(tmp_path, monkeypatch):
    output = tmp_path / "utility.png"
    captured = {}
    original_subplots = chart_util_small.plt.subplots

    def capture_subplots(*args, **kwargs):
        figure, axis = original_subplots(*args, **kwargs)
        captured["figure"] = figure
        captured["axis"] = axis
        return figure, axis

    monkeypatch.setattr(chart_util_small.plt, "subplots", capture_subplots)
    chart_util_small.render_utility_plot(
        pd.DataFrame({"run_a": [10.0, 30.0], "run_b": [20.0, 40.0]}),
        output,
        milp=None,
    )

    axis = captured["axis"]
    assert output.exists()
    assert axis.lines[0].get_ydata().tolist() == pytest.approx([15.0, 25.0])
    assert axis.lines[0].get_color() == "orange"
    assert len(axis.collections) == 1
    assert axis.get_legend()._loc == 4  # lower right
    assert axis.get_xgridlines()[0].get_alpha() == 0.5
    assert axis.xaxis.get_major_locator()._integer is True
    assert captured["figure"].get_size_inches().tolist() == [10.0, 5.0]


def test_milp_is_loaded_only_when_its_local_csv_is_present(tmp_path):
    source = tmp_path / "realized_end_to_end_utility_milp.csv"
    source.write_text("10\n20\n", encoding="utf-8")

    assert chart_util_small.load_optional_milp(source).tolist() == [10.0, 20.0]
