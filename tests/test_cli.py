"""The command line returns 0 when everything passes, 1 on a fail, 2 on bad input."""

from pathlib import Path

from gdt_checker.cli import main

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_example_part_exits_1_because_rear_face_fails(tmp_path, capsys):
    report = tmp_path / "report.md"
    plot = tmp_path / "plot.png"
    code = main([str(EXAMPLES / "bracket_spec.toml"), str(EXAMPLES / "bracket_measurements.csv"),
                 "--report", str(report), "--plot", str(plot)])
    assert code == 1
    assert "4 of 5 features pass; failed: rear_face" in capsys.readouterr().out
    assert "| rear_face | perpendicularity |" in report.read_text()
    assert plot.stat().st_size > 1000


def test_bad_input_exits_2(tmp_path, capsys):
    missing = tmp_path / "nope.toml"
    assert main([str(missing), str(EXAMPLES / "bracket_measurements.csv")]) == 2
    assert "error:" in capsys.readouterr().err


def test_outputs_go_into_folders_that_do_not_exist_yet(tmp_path):
    report = tmp_path / "new" / "nested" / "report.md"
    plot = tmp_path / "new" / "plot.png"
    code = main([str(EXAMPLES / "bracket_spec.toml"), str(EXAMPLES / "bracket_measurements.csv"),
                 "--report", str(report), "--plot", str(plot)])
    assert code == 1
    assert report.exists() and plot.exists()
