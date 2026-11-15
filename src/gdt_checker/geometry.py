"""Geometry helpers: plane and circle fits, datum reference frames and zone checks.

All points are numpy arrays with shape (n, 3) in millimetres (or whatever units
the measurement file uses). Nothing here knows about the spec file format.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog, minimize


@dataclass(frozen=True)
class Plane:
    """A plane written as normal . p = offset, with a unit normal."""

    normal: np.ndarray
    offset: float


@dataclass(frozen=True)
class DatumFrame:
    """Right-handed frame built from datums A, B and C.

    `origin` is where the three datum planes meet. `axes` is a 3x3 matrix whose
    rows are the x, y and z unit vectors in measurement coordinates.
    """

    origin: np.ndarray
    axes: np.ndarray

    def to_frame(self, points: np.ndarray) -> np.ndarray:
        """Express measured points in the datum frame."""
        return (np.asarray(points, dtype=float) - self.origin) @ self.axes.T


def fit_plane(points: np.ndarray) -> Plane:
    """Least-squares plane through points (total least squares via SVD)."""
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 3 or len(pts) < 3:
        raise ValueError("a plane needs at least 3 points with x, y, z")
    centroid = pts.mean(axis=0)
    _, singular, vt = np.linalg.svd(pts - centroid)
    if singular[1] < 1e-9 * max(singular[0], 1.0):
        raise ValueError("points are collinear, so no plane can be fitted")
    normal = vt[-1] / np.linalg.norm(vt[-1])
    return Plane(normal=normal, offset=float(normal @ centroid))


def fit_circle(points_xy: np.ndarray) -> tuple[np.ndarray, float]:
    """Least-squares circle (algebraic Kasa fit). Returns (center_xy, radius)."""
    pts = np.asarray(points_xy, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2 or len(pts) < 3:
        raise ValueError("a circle needs at least 3 points with x and y")
    a = np.column_stack([pts[:, 0], pts[:, 1], np.ones(len(pts))])
    b = -(pts[:, 0] ** 2 + pts[:, 1] ** 2)
    (d, e, f), *_ = np.linalg.lstsq(a, b, rcond=None)
    center = np.array([-d / 2.0, -e / 2.0])
    radius_sq = center @ center - f
    if radius_sq <= 0:
        raise ValueError("points do not lie on a circle")
    return center, float(np.sqrt(radius_sq))


def build_datum_frame(
    plane_a: Plane, plane_b: Plane, plane_c: Plane
) -> DatumFrame:
    """Build the 3-2-1 datum reference frame from three datum planes.

    - z axis: the normal of datum A (primary plane, constrains 3 degrees of freedom).
    - x axis: datum B's normal with any part along z removed (secondary plane).
    - y axis: z cross x, so the frame is right-handed.
    - origin: the single point where planes A, B and C all meet (tertiary plane).
    """
    z_axis = plane_a.normal
    x_raw = plane_b.normal - (plane_b.normal @ z_axis) * z_axis
    if np.linalg.norm(x_raw) < 1e-6:
        raise ValueError("datums A and B are parallel, so the frame is undefined")
    x_axis = x_raw / np.linalg.norm(x_raw)
    y_axis = np.cross(z_axis, x_axis)
    system = np.vstack([plane_a.normal, plane_b.normal, plane_c.normal])
    if abs(np.linalg.det(system)) < 1e-6:
        raise ValueError("datums A, B and C do not meet at one point")
    origin = np.linalg.solve(
        system, np.array([plane_a.offset, plane_b.offset, plane_c.offset])
    )
    return DatumFrame(origin=origin, axes=np.vstack([x_axis, y_axis, z_axis]))


def _vertical_width(xy: np.ndarray, z: np.ndarray, a: float, b: float) -> float:
    residual = z - a * xy[:, 0] - b * xy[:, 1]
    return float(residual.max() - residual.min())


def _perpendicular_width(xy: np.ndarray, z: np.ndarray, a: float, b: float) -> float:
    """Thickness of the slab between two planes parallel to z = a x + b y + c."""
    return _vertical_width(xy, z, a, b) / np.sqrt(1.0 + a * a + b * b)


def flatness_min_zone(points: np.ndarray) -> float:
    """Minimum-zone flatness: thickness of the thinnest slab containing all points.

    Step 1 is a linear program that finds the plane with the smallest vertical
    spread (a Chebyshev fit). Step 2 measures the perpendicular thickness of
    that slab and runs a small Nelder-Mead search over the plane tilt to lower
    it further. Returns the perpendicular thickness in the same units as input.
    """
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 3 or len(pts) < 3:
        raise ValueError("flatness needs at least 3 points with x, y, z")
    centred = pts - pts.mean(axis=0)
    xy, z = centred[:, :2], centred[:, 2]
    n = len(pts)
    # Variables: a, b, c, upper, lower. Minimise upper - lower with
    # lower <= z - (a x + b y + c) <= upper for every point.
    a_ub = np.zeros((2 * n, 5))
    b_ub = np.zeros(2 * n)
    a_ub[:n, :2] = -xy
    a_ub[:n, 2] = -1.0
    a_ub[:n, 3] = -1.0
    b_ub[:n] = -z
    a_ub[n:, :2] = xy
    a_ub[n:, 2] = 1.0
    a_ub[n:, 4] = 1.0
    b_ub[n:] = z
    cost = np.array([0.0, 0.0, 0.0, 1.0, -1.0])
    lp = linprog(cost, A_ub=a_ub, b_ub=b_ub, bounds=[(None, None)] * 5, method="highs")
    if not lp.success:
        raise ValueError(f"flatness linear program failed: {lp.message}")
    a0, b0 = lp.x[0], lp.x[1]
    best = _perpendicular_width(xy, z, a0, b0)
    refined = minimize(
        lambda ab: _perpendicular_width(xy, z, ab[0], ab[1]),
        x0=np.array([a0, b0]),
        method="Nelder-Mead",
        options={"xatol": 1e-10, "fatol": 1e-12, "maxiter": 2000},
    )
    return float(min(best, refined.fun))


def perpendicularity_deviation(points_frame: np.ndarray) -> float:
    """Perpendicularity of a planar feature to datum A (z = 0 plane in the frame).

    The feature's fitted normal is projected onto the datum plane. The zone is
    the slab, perpendicular to datum A, that the feature's points fit inside
    when the slab follows that projected normal. Returns the slab thickness.
    A feature parallel to datum A returns infinity.
    """
    plane = fit_plane(points_frame)
    direction = plane.normal[:2]
    length = np.linalg.norm(direction)
    if length < 1e-9:
        return float("inf")
    direction = direction / length
    projected = np.asarray(points_frame, dtype=float)[:, :2] @ direction
    return float(projected.max() - projected.min())


def profile_band_width(points_frame: np.ndarray, nominal_height: float) -> float:
    """Full width of the band needed to hold a planar surface about its nominal.

    Profile of a surface with a bilateral zone is measured as 2 * max |deviation|.
    Compare the result with the full tolerance value.
    """
    z = np.asarray(points_frame, dtype=float)[:, 2]
    return float(2.0 * np.max(np.abs(z - nominal_height)))


def true_position_error(
    center_frame: np.ndarray, nominal_xy: np.ndarray
) -> float:
    """Position error (diameter of the deviation circle), as used by true position."""
    deviation = np.asarray(center_frame, dtype=float) - np.asarray(nominal_xy, dtype=float)
    return float(2.0 * np.hypot(deviation[0], deviation[1]))
