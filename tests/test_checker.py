"""Hand-calculated feature checks, spec validation, and the example part."""

import math
from pathlib import Path

import numpy as np
import pytest

from gdt_checker import SpecError, check_files, load_points, load_spec
from gdt_checker.checker import Feature, check_feature

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _hole_points(cx, cy, radius, z=-5.0):
    return np.array(
        [[cx + radius * math.cos(math.radians(a)), cy + radius * math.sin(math.radians(a)), z]
         for a in range(0, 360, 45)]
    )


def test_mmc_hole_gets_bonus_for_extra_diameter():
    # Hole dia 10.0, MMC (smallest) 9.9 -> bonus 0.1 -> limit 0.25 + 0.1 = 0.35.
    # Offset (-0.1, 0.1) from nominal -> error 2*sqrt(0.02) = 0.28284 -> PASS.
    feature = Feature("H1", "position", tolerance=0.25, datums=("A", "B", "C"),
                      size_kind="hole", material_condition="MMC", mmc_size=9.9, nominal=(-20.0, 15.0))
    result = check_feature(feature, _hole_points(-20.1, 15.1, 5.0))
    assert result.bonus == pytest.approx(0.1)
    assert result.limit == pytest.approx(0.35)
    assert result.measured == pytest.approx(2 * math.sqrt(0.02), abs=1e-9)
    assert result.passed


def test_same_hole_fails_when_regardless_of_feature_size():
    # RFS gives no bonus: limit stays 0.25 and 0.28284 fails.
    feature = Feature("H1", "position", tolerance=0.25, datums=("A", "B", "C"),
                      size_kind="hole", material_condition="RFS", nominal=(-20.0, 15.0))
    result = check_feature(feature, _hole_points(-20.1, 15.1, 5.0))
    assert result.bonus == 0.0
    assert not result.passed


def test_pin_mmc_bonus_grows_as_pin_shrinks():
    # Pin MMC (largest) 10.0, actual dia 9.8 -> bonus 0.2 -> limit 0.1 + 0.2 = 0.3.
    feature = Feature("P1", "position", tolerance=0.1, datums=("A", "B", "C"),
                      size_kind="pin", material_condition="MMC", mmc_size=10.0, nominal=(0.0, 0.0))
    result = check_feature(feature, _hole_points(0.0, 0.0, 4.9))
    assert result.bonus == pytest.approx(0.2)
    assert result.limit == pytest.approx(0.3)


def test_example_part_matches_hand_calculated_values():
    spec, results, _, _ = check_files(EXAMPLES / "bracket_spec.toml", EXAMPLES / "bracket_measurements.csv")
    by_id = {r.feature_id: r for r in results}
    assert by_id["top_face"].measured == pytest.approx(0.01, abs=1e-4)
    assert by_id["top_face"].passed
    assert by_id["rear_face"].measured == pytest.approx(0.2, abs=1e-9)
    assert not by_id["rear_face"].passed
    assert by_id["H1"].measured == pytest.approx(0.282843, abs=1e-5)
    assert by_id["H1"].limit == pytest.approx(0.35, abs=1e-4)
    assert by_id["H1"].passed
    # H2 offset (-0.02, 0.03): error 2*sqrt(0.0013) = 0.072111 against 0.10.
    assert by_id["H2"].measured == pytest.approx(0.072111, abs=1e-5)
    assert by_id["H2"].passed
    assert by_id["pad_profile"].measured == pytest.approx(0.06)
    assert by_id["pad_profile"].passed
    assert len(results) == 5


def test_spec_rejects_unknown_type(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text('[[features]]\nid="A"\ntype="datum"\n[[features]]\nid="B"\ntype="datum"\n'
                    '[[features]]\nid="C"\ntype="datum"\n[[features]]\nid="X"\ntype="bogus"\ntolerance=0.1\n')
    with pytest.raises(SpecError, match="unknown type"):
        load_spec(path)


def test_position_without_all_datums_is_rejected(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text('[[features]]\nid="A"\ntype="datum"\n[[features]]\nid="B"\ntype="datum"\n'
                    '[[features]]\nid="C"\ntype="datum"\n[[features]]\nid="H"\ntype="position"\n'
                    'tolerance=0.1\ndatums=["A"]\nnominal=[0,0]\n')
    with pytest.raises(SpecError, match="needs datums A, B and C"):
        load_spec(path)


def test_missing_csv_columns_are_rejected(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("feature,x,y\nA,0,0\n")
    with pytest.raises(SpecError, match="feature,x,y,z"):
        load_points(path)
