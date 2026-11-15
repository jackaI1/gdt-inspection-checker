"""Load a part spec and a measurement CSV, then check every feature control frame."""

from __future__ import annotations

import csv
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .geometry import (
    DatumFrame,
    Plane,
    build_datum_frame,
    fit_circle,
    fit_plane,
    flatness_min_zone,
    perpendicularity_deviation,
    profile_band_width,
    true_position_error,
)

FEATURE_TYPES = {"datum", "flatness", "perpendicularity", "position", "profile"}
MATERIAL_CONDITIONS = {"MMC", "RFS"}
SIZE_KINDS = {"hole", "pin"}
DATUM_LABELS = ("A", "B", "C")


class SpecError(ValueError):
    """Raised when the spec file or the measurement file is wrong."""


@dataclass(frozen=True)
class Feature:
    id: str
    type: str
    tolerance: float | None = None
    datums: tuple[str, ...] = ()
    size_kind: str | None = None
    material_condition: str = "RFS"
    mmc_size: float | None = None
    nominal: tuple[float, float] | None = None
    nominal_height: float = 0.0


@dataclass(frozen=True)
class Spec:
    name: str
    units: str
    features: tuple[Feature, ...]


@dataclass(frozen=True)
class Result:
    feature_id: str
    fcf_type: str
    measured: float
    limit: float
    bonus: float
    passed: bool
    note: str

    @property
    def margin(self) -> float:
        return self.limit - self.measured


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SpecError(message)


def load_spec(path: str | Path) -> Spec:
    """Read and validate a TOML part spec."""
    with open(path, "rb") as handle:
        raw = tomllib.load(handle)
    _require(isinstance(raw.get("features"), list), "spec needs a [[features]] list")
    features: list[Feature] = []
    ids: set[str] = set()
    for entry in raw["features"]:
        fid = str(entry.get("id", "")).strip()
        _require(bool(fid), "every feature needs an id")
        _require(fid not in ids, f"feature id '{fid}' is used twice")
        ids.add(fid)
        ftype = entry.get("type")
        _require(ftype in FEATURE_TYPES, f"feature '{fid}' has unknown type '{ftype}'")
        if ftype == "datum":
            _require(fid in DATUM_LABELS, f"datum '{fid}' must be named A, B or C")
            features.append(Feature(id=fid, type=ftype))
            continue
        tolerance = float(entry.get("tolerance", -1))
        _require(tolerance > 0, f"feature '{fid}' needs a positive tolerance")
        datums = tuple(entry.get("datums", []))
        for label in datums:
            _require(label in DATUM_LABELS, f"feature '{fid}' references unknown datum '{label}'")
        if ftype in {"perpendicularity", "profile"}:
            _require("A" in datums, f"feature '{fid}' ({ftype}) must reference datum A")
        if ftype == "position":
            _require(set(datums) == set(DATUM_LABELS), f"position '{fid}' needs datums A, B and C")
            size_kind = entry.get("size_kind", "hole")
            _require(size_kind in SIZE_KINDS, f"position '{fid}' size_kind must be hole or pin")
            condition = entry.get("material_condition", "RFS")
            _require(condition in MATERIAL_CONDITIONS, f"position '{fid}' material_condition must be MMC or RFS")
            nominal = entry.get("nominal")
            _require(
                isinstance(nominal, list) and len(nominal) == 2,
                f"position '{fid}' needs nominal = [x, y] in datum frame coordinates",
            )
            mmc_size = entry.get("mmc_size")
            if condition == "MMC":
                _require(mmc_size is not None, f"position '{fid}' with MMC needs mmc_size")
            features.append(
                Feature(
                    id=fid,
                    type=ftype,
                    tolerance=tolerance,
                    datums=datums,
                    size_kind=size_kind,
                    material_condition=condition,
                    mmc_size=float(mmc_size) if mmc_size is not None else None,
                    nominal=(float(nominal[0]), float(nominal[1])),
                )
            )
        else:
            features.append(
                Feature(
                    id=fid,
                    type=ftype,
                    tolerance=tolerance,
                    datums=datums,
                    nominal_height=float(entry.get("nominal_height", 0.0)),
                )
            )
    for label in DATUM_LABELS:
        _require(label in ids, f"spec must define datum {label}")
        _require(
            next(f for f in features if f.id == label).type == "datum",
            f"{label} must be a datum",
        )
    return Spec(
        name=str(raw.get("name", "unnamed part")),
        units=str(raw.get("units", "mm")),
        features=tuple(features),
    )


def load_points(path: str | Path) -> dict[str, np.ndarray]:
    """Read measured points from a CSV with columns feature,x,y,z."""
    grouped: dict[str, list[list[float]]] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        _require(
            reader.fieldnames is not None and {"feature", "x", "y", "z"} <= set(reader.fieldnames),
            "measurement CSV needs columns: feature,x,y,z",
        )
        for line_no, row in enumerate(reader, start=2):
            try:
                point = [float(row["x"]), float(row["y"]), float(row["z"])]
            except (TypeError, ValueError) as error:
                raise SpecError(f"line {line_no}: x, y and z must be numbers") from error
            grouped.setdefault(row["feature"].strip(), []).append(point)
    return {name: np.array(points, dtype=float) for name, points in grouped.items()}


def _oriented_planes(points: dict[str, np.ndarray]) -> dict[str, tuple[np.ndarray, float]]:
    """Fit datums A, B and C. Normals point out of the part (away from its centroid)."""
    everything = np.vstack([points[label] for label in DATUM_LABELS])
    body_centre = everything.mean(axis=0)
    planes: dict[str, tuple[np.ndarray, float]] = {}
    for label in DATUM_LABELS:
        plane = fit_plane(points[label])
        centre = points[label].mean(axis=0)
        normal = plane.normal
        if normal @ (centre - body_centre) < 0:
            normal = -normal
        planes[label] = (normal, float(normal @ centre))
    return planes


def build_frame(points: dict[str, np.ndarray]) -> DatumFrame:
    planes = _oriented_planes(points)
    return build_datum_frame(
        *(Plane(normal=planes[label][0], offset=planes[label][1]) for label in DATUM_LABELS)
    )


def _position_bonus(feature: Feature, diameter: float) -> float:
    if feature.material_condition != "MMC":
        return 0.0
    if feature.size_kind == "hole":
        return max(0.0, diameter - float(feature.mmc_size))
    return max(0.0, float(feature.mmc_size) - diameter)


def check_feature(feature: Feature, frame_points: np.ndarray) -> Result:
    """Evaluate one feature control frame on points already in the datum frame."""
    assert feature.tolerance is not None
    tolerance = feature.tolerance
    if feature.type == "flatness":
        measured = flatness_min_zone(frame_points)
        return Result(feature.id, "flatness", measured, tolerance, 0.0, measured <= tolerance,
                      "minimum-zone thickness")
    if feature.type == "perpendicularity":
        measured = perpendicularity_deviation(frame_points)
        return Result(feature.id, "perpendicularity", measured, tolerance, 0.0,
                      measured <= tolerance, "zone perpendicular to datum A")
    if feature.type == "profile":
        measured = profile_band_width(frame_points, feature.nominal_height)
        return Result(feature.id, "profile", measured, tolerance, 0.0, measured <= tolerance,
                      f"bilateral band about z = {feature.nominal_height:g}")
    if feature.type == "position":
        center, radius = fit_circle(frame_points[:, :2])
        diameter = 2.0 * radius
        bonus = _position_bonus(feature, diameter)
        measured = true_position_error(center, np.array(feature.nominal))
        limit = tolerance + bonus
        note = f"{feature.material_condition}, {feature.size_kind} dia {diameter:.4f}"
        return Result(feature.id, "position", measured, limit, bonus, measured <= limit, note)
    raise SpecError(f"feature '{feature.id}' has unsupported type '{feature.type}'")


def check_part(spec: Spec, points: dict[str, np.ndarray]) -> list[Result]:
    """Build the datum frame, then evaluate every non-datum feature."""
    for label in DATUM_LABELS:
        _require(label in points, f"measurement file has no points for datum {label}")
    frame = build_frame(points)
    results: list[Result] = []
    for feature in spec.features:
        if feature.type == "datum":
            continue
        _require(feature.id in points, f"measurement file has no points for '{feature.id}'")
        frame_points = frame.to_frame(points[feature.id])
        results.append(check_feature(feature, frame_points))
    return results


def check_files(
    spec_path: str | Path, csv_path: str | Path
) -> tuple[Spec, list[Result], DatumFrame, dict[str, np.ndarray]]:
    """Load both files, check the part, and return what the report and plot need."""
    spec = load_spec(spec_path)
    points = load_points(csv_path)
    frame = build_frame(points)
    results = check_part(spec, points)
    return spec, results, frame, points
