import importlib.util
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Chart" / "jain" / "jain.py"
SPEC = importlib.util.spec_from_file_location("chart_jain", SCRIPT)
chart_jain = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(chart_jain)


def test_load_jain_runs_preserves_current_headered_run_columns(tmp_path):
    source = tmp_path / "jain_index.csv"
    source.write_text(
        "run_a,run_b\n0.90,0.80\n0.95,0.85\n",
        encoding="utf-8",
    )

    runs = chart_jain.load_jain_runs(source)

    assert list(runs.columns) == ["run_a", "run_b"]
    assert runs.iloc[0].tolist() == [0.90, 0.80]


def test_render_jain_plot_writes_current_run_summary(tmp_path):
    output = tmp_path / "jain.png"
    runs = pd.DataFrame(
        {
            "run_a": [0.90, 0.95, 0.98],
            "run_b": [0.85, 0.92, 0.96],
        }
    )

    result = chart_jain.render_jain_plot(
        runs,
        output,
        baselines={
            "milp": {"kind": "constant", "value": 0.97},
            "drl": {"kind": "series", "values": [0.80, 0.85, 0.90]},
            "greedy": {"kind": "series", "values": [0.75, 0.82, 0.88]},
        },
    )

    assert result == output
    assert output.exists()
    assert output.stat().st_size > 0


def test_render_jain_plot_uses_the_requested_jain_y_axis(tmp_path, monkeypatch):
    output = tmp_path / "jain.png"
    captured = {}
    original_subplots = chart_jain.plt.subplots

    def capture_subplots(*args, **kwargs):
        figure, axis = original_subplots(*args, **kwargs)
        captured["figure"] = figure
        captured["axis"] = axis
        return figure, axis

    monkeypatch.setattr(chart_jain.plt, "subplots", capture_subplots)
    chart_jain.render_jain_plot(pd.DataFrame({"run_a": [0.95, 0.96]}), output)

    assert captured["axis"].get_ylim() == (0.8, 1.0)
    assert captured["axis"].lines[0].get_color() == "orange"
    assert captured["axis"].get_legend()._loc == 4  # lower right
    assert captured["axis"].get_xgridlines()[0].get_alpha() == 0.5
    assert captured["figure"].get_size_inches().tolist() == [12.0, 6.0]


def test_optional_legacy_baselines_are_loaded_only_when_present(tmp_path):
    source = tmp_path / "jain_index.csv"
    source.write_text("run_a\n0.90\n", encoding="utf-8")
    milp = tmp_path / "jain_index_milp.csv"
    drl = tmp_path / "jain_index_drl.csv"
    greedy = tmp_path / "jain_index_greedy.csv"
    milp.write_text("0.92,0.94\n", encoding="utf-8")
    drl.write_text("0.80,0.82,0.84\n", encoding="utf-8")
    greedy.write_text("0,0.70,0.80\n1,0.75,0.85\n", encoding="utf-8")

    baselines = chart_jain.load_optional_baselines(
        source,
        milp=milp,
        drl=drl,
        greedy=greedy,
    )

    assert baselines["milp"]["kind"] == "constant"
    assert baselines["milp"]["value"] == pytest.approx(0.93)
    assert baselines["drl"]["kind"] == "series"
    assert baselines["drl"]["values"].tolist() == [0.80, 0.82, 0.84]
    assert baselines["greedy"]["values"].tolist() == [0.75, 0.8]


def test_optional_baselines_are_discovered_beside_the_script_only(tmp_path, monkeypatch):
    source = tmp_path / "external" / "jain_index.csv"
    source.parent.mkdir()
    source.write_text("run_a\n0.90\n", encoding="utf-8")
    source.parent.joinpath("jain_index_milp.csv").write_text(
        "0.80\n", encoding="utf-8"
    )
    chart_folder = tmp_path / "jain"
    chart_folder.mkdir()
    chart_folder.joinpath("jain_index_milp.csv").write_text(
        "0.95\n", encoding="utf-8"
    )
    monkeypatch.setattr(chart_jain, "SCRIPT_DIR", chart_folder)

    baselines = chart_jain.load_optional_baselines(source)

    assert baselines["milp"]["value"] == pytest.approx(0.95)


def test_primary_input_discovers_one_ibg_named_csv_beside_the_script(
    tmp_path, monkeypatch
):
    chart_folder = tmp_path / "jain"
    chart_folder.mkdir()
    primary = chart_folder / "fairness_IBG.csv"
    primary.write_text("run_a\n0.90\n", encoding="utf-8")
    monkeypatch.setattr(chart_jain, "SCRIPT_DIR", chart_folder)

    assert chart_jain.resolve_primary_input() == primary


def test_primary_input_rejects_ambiguous_ibg_named_csvs(tmp_path, monkeypatch):
    chart_folder = tmp_path / "jain"
    chart_folder.mkdir()
    for name in ("one_IBG.csv", "two_IBG.csv"):
        chart_folder.joinpath(name).write_text("run_a\n0.90\n", encoding="utf-8")
    monkeypatch.setattr(chart_jain, "SCRIPT_DIR", chart_folder)

    with pytest.raises(ValueError, match="multiple Jain IBG CSV"):
        chart_jain.resolve_primary_input()


def test_jain_defaults_to_the_requested_ibg_exact_small_scale_title():
    args = chart_jain.parse_args([])

    assert args.title == (
        "Jain's fairness index on small-scale topology: IBG-Exact"
    )
    assert args.input is None
    assert args.output == chart_jain.SCRIPT_DIR / "jain_index.png"


def test_load_jain_runs_rejects_values_outside_jain_bounds(tmp_path):
    source = tmp_path / "jain_index.csv"
    source.write_text("run_a\n1.01\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        chart_jain.load_jain_runs(source)
