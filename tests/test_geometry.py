"""Hand-calculated checks for the geometry helpers."""

import math

import numpy as np
import pytest

from gdt_checker.geometry import (
    Plane,
    build_datum_frame,
    fit_circle,
    fit_plane,
    flatness_min_zone,
    perpendicularity_deviation,
    profile_band_width,
    true_position_error,
)


def test_plane_fit_recovers_z_plane_at_height_five():
    pts = np.array([[0, 0, 5], [10, 0, 5], [0, 10, 5], [7, -3, 5]], float)
    plane = fit_plane(pts)
    assert abs(abs(plane.normal[2]) - 1) < 1e-12
    assert plane.offset == pytest.approx(5.0)


def test_plane_fit_rejects_collinear_points():
    with pytest.raises(ValueError):
        fit_plane(np.array([[0, 0, 0], [1, 1, 1], [2, 2, 2]], float))


def test_circle_fit_recovers_centre_and_radius():
    # Circle of radius 5 centred at (10.1, 20.1): diameter 10.0 by hand.
    angles = np.radians([0, 90, 180, 270])
    pts = np.column_stack([10.1 + 5 * np.cos(angles), 20.1 + 5 * np.sin(angles)])
    centre, radius = fit_circle(pts)
    assert centre == pytest.approx([10.1, 20.1])
    assert radius == pytest.approx(5.0)


def test_datum_frame_identity_for_axis_aligned_datums():
    # A: z = 0, B: x = 0, C: y = 0 -> origin (0,0,0) and identity axes.
    frame = build_datum_frame(
        Plane(np.array([0, 0, 1.0]), 0.0),
        Plane(np.array([1.0, 0, 0]), 0.0),
        Plane(np.array([0, 1.0, 0]), 0.0),
    )
    assert frame.origin == pytest.approx([0, 0, 0])
    assert frame.axes == pytest.approx(np.eye(3))


def test_datum_frame_origin_moves_with_datum_planes():
    # Planes z = 5, x = 10, y = 20 meet at (10, 20, 5); a point at (11, 20, 5) is (1, 0, 0).
    frame = build_datum_frame(
        Plane(np.array([0, 0, 1.0]), 5.0),
        Plane(np.array([1.0, 0, 0]), 10.0),
        Plane(np.array([0, 1.0, 0]), 20.0),
    )
    assert frame.origin == pytest.approx([10, 20, 5])
    np.testing.assert_allclose(frame.to_frame(np.array([[11.0, 20.0, 5.0]])), [[1, 0, 0]], atol=1e-12)


def test_flatness_square_with_one_corner_raised():
    # Square of side 30 with one corner raised by h = 0.02. Hand result: the
    # best slab is tilted so the raised corner sits at the middle of the other
    # three, giving a vertical spread of h/2 = 0.01 (side length cancels out).
    pts = np.array([[-30, 0, 0], [0, 0, 0], [-30, 30, 0], [0, 30, 0.02]], float)
    assert flatness_min_zone(pts) == pytest.approx(0.01, abs=1e-4)


def test_flatness_of_a_true_plane_is_zero():
    pts = np.array([[0, 0, 1], [4, 0, 1], [0, 3, 1], [4, 3, 1], [2, 1, 1]], float)
    assert flatness_min_zone(pts) == pytest.approx(0.0, abs=1e-9)


def test_perpendicularity_of_face_leaning_0p1_per_mm():
    # Face x = 0.1 z over z in [0, 10]: x spans 0 to 1.0, so the zone is 1.0 wide.
    pts = np.array([[0, 0, 0], [0, 10, 0], [0.5, 0, 5], [0.5, 10, 5], [1, 0, 10], [1, 10, 10]], float)
    assert perpendicularity_deviation(pts) == pytest.approx(1.0)


def test_perpendicularity_of_square_face_is_zero():
    pts = np.array([[3, 0, 0], [3, 10, 0], [3, 0, 10], [3, 10, 10]], float)
    assert perpendicularity_deviation(pts) == pytest.approx(0.0, abs=1e-12)


def test_profile_band_is_twice_the_largest_deviation():
    # Heights 0.03, -0.02, 0.04 about nominal 0: largest |dev| is 0.04, band = 0.08.
    pts = np.array([[0, 0, 0.03], [1, 0, -0.02], [0, 1, 0.04]], float)
    assert profile_band_width(pts, 0.0) == pytest.approx(0.08)


def test_true_position_error_is_twice_the_radial_offset():
    # Offset (0.1, 0.1): radius 0.1414, so error = 2 * sqrt(0.02) = 0.28284.
    assert true_position_error(np.array([10.1, 20.1]), np.array([10.0, 20.0])) == pytest.approx(
        2 * math.sqrt(0.02)
    )
