# GD&T concepts in this checker (ASME Y14.5)

This page explains which parts of ASME Y14.5 the checker implements, how each
one is calculated, and what it leaves out. It is written for someone who knows
what a drawing callout looks like but has not read the standard.

## Datums and the datum reference frame

A datum is a feature on the part that the drawing uses as a reference, labelled
with a letter. The checker reads three datums, A, B and C, each as a set of
measured points.

The **3-2-1 alignment** is how the frame is built:

| Datum | Real contact points | Checker |
| --- | --- | --- |
| A (primary) | 3 points, removes 3 degrees of freedom | least-squares plane; sets the z axis |
| B (secondary) | 2 points, removes 2 | least-squares plane; its normal, with z removed, sets the x axis |
| C (tertiary) | 1 point, removes 1 | least-squares plane; the three planes A, B and C meet at the origin |

The y axis is z cross x, so the frame is right-handed. Normals point out of the
part (away from the centroid of all measured points), which is the usual
convention for datum faces.

**Left out:** the checker uses whole planes for all three datums, not the
2-point and 1-point contacts of a real 3-2-1 set-up. It also does not apply
datum feature simulators (a surface plate or a gauge pin) that real inspection
uses to hold a part, so it does not model how a part sits on a fixture.

## Flatness (minimum zone)

Flatness is the thickness of the thinnest pair of parallel planes that enclose
every point of the surface. The checker does this in two steps:

1. A linear program (`scipy.optimize.linprog`) finds the plane with the smallest
   vertical spread of the points (a Chebyshev fit).
2. The perpendicular thickness of that slab is then reduced further by a
   Nelder-Mead search over the plane's tilt.

The result is the perpendicular thickness. For a square with one corner raised by
0.02 mm, the hand result is 0.01 mm, which the tests check.

**Left out:** the second step is a local search, so for an unusual point set it
may stop at a local minimum rather than the global one.

## Perpendicularity (to datum A)

A feature is perpendicular to datum A when it stands straight up from A. The
checker fits a plane to the feature's points, projects its normal onto the
datum A plane, and measures how far the points spread along that projected
direction. For a face that leans 0.1 mm per mm of height over 10 mm, the spread
is 1.0 mm.

**Left out:** this uses a least-squares feature normal, not a search over every
zone orientation, so it can slightly overstate the deviation for a face that is
both twisted and leaning. A feature parallel to datum A is reported as infinitely
out of tolerance.

## True position

Position is how far a hole or pin centre sits from its theoretical (basic)
location, measured in the datum frame. The zone is a circle, so the deviation is
given as a diameter:

    position error = 2 * sqrt(dx^2 + dy^2)

The checker fits a circle to the hole's points (algebraic least squares) to find
the centre and diameter.

### Maximum material condition (MMC) bonus

MMC gives extra tolerance when a feature is not at its most-material size:

- **Hole:** the most-material size is the smallest diameter. A larger hole gets
  bonus tolerance equal to (measured diameter) - (MMC diameter).
- **Pin:** the most-material size is the largest diameter. A smaller pin gets
  bonus tolerance equal to (MMC diameter) - (measured diameter).

The allowed position is the base tolerance plus the bonus. Features marked RFS
(regardless of feature size) get no bonus.

Worked example from the tests: a hole of diameter 10.0 mm, MMC 9.9 mm, base
tolerance 0.25 mm. The bonus is 0.10 mm, so the limit is 0.35 mm. An offset of
(-0.1, 0.1) gives a position error of 0.2828 mm, which passes. Without the bonus
the same hole would fail.

**Left out:** the checker takes hole axes as perpendicular to datum A and uses
only the points' XY positions. Tilted holes, and the datum-shift and bonus rules
for datum features at MMC, are not implemented.

## Profile of a surface

A profile tolerance is a band that the surface must stay inside, centred on a
theoretical shape. The checker supports only planar nominal shapes at a given
height above datum A. The band is bilateral (it extends equally on both sides),
so the full width needed is 2 times the largest deviation from the nominal.

**Left out:** curved profiles, unilateral and unequal bands, and profile
combined with datum references beyond A.

## Not implemented

- Straightness, circularity, cylindricity, runout, angularity, symmetry and
  concentricity.
- Composite feature control frames (for example two-row position).
- Free-state, projected and statistical tolerance zones.
- Feature of size checks (the measured diameter is reported but not checked
  against its own size tolerance).
- Uncertainty of measurement and any machine calibration.

These are not drawing checks a student tool should imply it covers. This tool
checks a fixed set of callouts against measured points, and it says so in its
report.
