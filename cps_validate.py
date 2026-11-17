#!/usr/bin/env python3
"""cps_validate.py - Canonical Point Schema (CPS) v1 validator.

Spec: projects/mapping/CANONICAL-POINT-SCHEMA.md

Single file, standard library only, so it can be vendored into any repo that
holds a CPS set - including the public Chicago-Offline repo, which cannot
import from the private workspace.

Usage:
    cps_validate.py SET.geojson [SET.geojson ...]
    cps_validate.py --target public sets/*/pois.geojson
    cps_validate.py --sweep "Eric,Muehlstein,Summerdale" sets/*.geojson

Exit 0 clean, 1 on any error. Warnings never change the exit code.
"""
import argparse
import json
import os
import re
import sys

# --- Maki 215, verified against mapbox/maki 2026-11-16 --------------------
MAKI = set("""aerialway airfield airport alcohol-shop american-football
amusement-park animal-shelter aquarium arrow art-gallery attraction bakery bank
bank-JP bar barrier baseball basketball bbq beach beer bicycle bicycle-share
blood-bank bowling-alley bridge building building-alt1 bus cafe campsite car
car-rental car-repair casino castle castle-JP cemetery cemetery-JP
charging-station cinema circle circle-stroked city clothing-store college
college-JP commercial communications-tower confectionery construction
convenience cricket cross dam danger defibrillator dentist diamond doctor
dog-park drinking-water elevator embassy emergency-phone entrance entrance-alt1
farm fast-food fence ferry ferry-JP fire-station fire-station-JP fitness-centre
florist fuel furniture gaming garden garden-centre gate gift globe golf grocery
hairdresser harbor hardware heart heliport highway-rest-area historic home
horse-riding hospital hospital-JP hot-spring ice-cream industry information
jewelry-store karaoke landmark landmark-JP landuse laundry library lift-gate
lighthouse lighthouse-JP lodging logging marae marker marker-stroked
mobile-phone monument monument-JP mountain museum music natural nightclub
observation-tower optician paint park park-alt1 parking parking-garage
parking-paid pharmacy picnic-site pitch place-of-worship playground police
police-JP post post-JP prison racetrack racetrack-boat racetrack-cycling
racetrack-horse rail rail-light rail-metro ranger-station recycling
religious-buddhist religious-christian religious-jewish religious-muslim
religious-shinto residential-community restaurant restaurant-bbq
restaurant-noodle restaurant-pizza restaurant-seafood restaurant-sushi
road-accident roadblock rocket school school-JP scooter shelter shoe shop
skateboard skiing slaughterhouse slipway snowmobile soccer square
square-stroked stadium star star-stroked suitcase swimming table-tennis taxi
teahouse telephone tennis terminal theatre toilet toll town town-hall triangle
triangle-stroked tunnel veterinary viewpoint village volcano volleyball
warehouse waste-basket watch water waterfall watermill wetland wheelchair
windmill zoo""".split())

VISIBILITIES = {"public", "private"}

# Licence and visibility are ORTHOGONAL axes, not one scale.
#   visibility -> may this data be distributed at all (a gate)
#   licence    -> what obligations attach to the artifact if it is (a duty)
# Ranking 'private' above 'ODbL-1.0' on one scale swallows the ODbL
# attribution duty, which is the exact failure this check exists to catch.
KNOWN_LICENCES = {"CC0-1.0", "public-domain", "permissive", "ODbL-1.0", "private"}

# Licences that impose duties on every artifact built from the data.
SHARE_ALIKE = {"ODbL-1.0"}
ATTRIBUTION_REQUIRED = {"ODbL-1.0"}

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
RFC3339_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def err(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}: {msg}")


def validate_symbol(sym, where, rep):
    if not isinstance(sym, str) or not sym:
        rep.err(where, "marker-symbol missing or not a string")
        return
    if sym.startswith("x-"):
        if sym != sym.lower():
            rep.err(where, f"extension symbol '{sym}' must be lowercase")
        return
    if sym not in MAKI:
        near = [m for m in MAKI if m.startswith(sym[:4].lower())][:3]
        hint = f" did you mean {near}?" if near else ""
        rep.err(where, f"marker-symbol '{sym}' is not a Maki name and lacks "
                       f"the 'x-' extension prefix.{hint}")


def validate_feature(feat, idx, rep, seen_ids):
    where = f"feature[{idx}]"
    if feat.get("type") != "Feature":
        rep.err(where, "type must be 'Feature'")
        return

    fid = feat.get("id")
    if not fid:
        rep.err(where, "missing stable 'id' (RFC 4122 UUID)")
    elif not UUID_RE.match(str(fid)):
        rep.err(where, f"id '{fid}' is not a UUID")
    elif fid in seen_ids:
        rep.err(where, f"duplicate id '{fid}' (also {seen_ids[fid]})")
    else:
        seen_ids[fid] = where

    geom = feat.get("geometry")
    if not isinstance(geom, dict):
        rep.err(where, "missing geometry")
    elif geom.get("type") != "Point":
        rep.err(where, f"geometry.type '{geom.get('type')}' - CPS is points only")
    else:
        c = geom.get("coordinates")
        if not (isinstance(c, list) and len(c) >= 2
                and all(isinstance(v, (int, float)) for v in c[:2])):
            rep.err(where, "coordinates must be [lon, lat] numbers")
        else:
            lon, lat = c[0], c[1]
            if not -180 <= lon <= 180:
                rep.err(where, f"lon {lon} out of range")
            if not -90 <= lat <= 90:
                rep.err(where, f"lat {lat} out of range")
            # RFC 7946 is [lon, lat]. Flag the classic swap.
            if abs(lon) <= 90 and abs(lat) > 90:
                rep.err(where, "coordinates look swapped (RFC 7946 is [lon, lat])")

    props = feat.get("properties")
    if not isinstance(props, dict):
        rep.err(where, "missing properties")
        return

    name = props.get("title")
    if not name:
        rep.err(where, "properties.title is required")
    else:
        where = f"feature[{idx}] '{name}'"

    for legacy in ("name", "notes", "note", "remarks", "icon", "category"):
        if legacy in props:
            rep.warn(where, f"legacy field '{legacy}' survived ingest")

    validate_symbol(props.get("marker-symbol"), where, rep)

    if not props.get("dct:source"):
        rep.err(where, "dct:source is required - every record cites a source")

    col = props.get("marker-color")
    if col is not None and not re.match(r"^#[0-9a-fA-F]{6}$", str(col)):
        rep.err(where, f"marker-color '{col}' must be #RRGGBB")

    for datefield in ("verified", "dct:modified"):
        v = props.get(datefield)
        if v is not None and not RFC3339_DATE.match(str(v)):
            rep.err(where, f"{datefield} '{v}' is not RFC 3339 (YYYY-MM-DD)")

    osm = props.get("osm")
    if osm is not None and not isinstance(osm, dict):
        rep.err(where, "osm must be an object of OpenStreetMap tags")

    return props.get("visibility")


def set_label(path):
    """Every set file is named pois.geojson, so basename alone is useless.
    Label by the containing directory, which is the set name."""
    ap = os.path.abspath(path)
    parent = os.path.basename(os.path.dirname(ap))
    base = os.path.basename(ap)
    return f"{parent}/{base}" if parent else base


def validate_set(path, rep, target):
    where = set_label(path)
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except Exception as exc:
        rep.err(where, f"unreadable: {exc}")
        return None

    if doc.get("type") != "FeatureCollection":
        rep.err(where, "type must be 'FeatureCollection'")

    vis = doc.get("visibility")
    if vis is None:
        rep.err(where, "visibility is required - unset is an error, not a default")
    elif vis not in VISIBILITIES:
        rep.err(where, f"visibility '{vis}' must be one of {sorted(VISIBILITIES)}")

    lic = doc.get("dct:license")
    if not lic:
        rep.err(where, "dct:license is required (SPDX id or 'private')")
    elif lic not in KNOWN_LICENCES:
        rep.warn(where, f"licence '{lic}' not in known set {sorted(KNOWN_LICENCES)}")

    if not doc.get("name"):
        rep.err(where, "set 'name' is required")
    if not doc.get("dct:source"):
        rep.warn(where, "set-level dct:source missing (should mirror ATTRIBUTION.md)")

    feats = doc.get("features")
    if not isinstance(feats, list):
        rep.err(where, "features must be a list")
        return None

    seen_ids = {}
    for i, f in enumerate(feats):
        fvis = validate_feature(f, i, rep, seen_ids)
        # Rule 1: a private feature may never reach a public target.
        if target == "public":
            if fvis == "private":
                rep.err(where, f"feature[{i}] is visibility:private but the "
                               f"target is public")
    if target == "public" and vis == "private":
        rep.err(where, "set is visibility:private but the target is public - "
                       "refusing to build")

    return {"path": path, "visibility": vis, "licence": lic, "count": len(feats)}


def sweep(paths, needles, rep):
    """Surface candidate personal data for human review. Never auto-passes."""
    pats = [n.strip() for n in needles.split(",") if n.strip()]
    if not pats:
        return
    rx = re.compile("|".join(re.escape(p) for p in pats), re.I)
    hits = 0
    for p in paths:
        try:
            doc = json.load(open(p))
        except Exception:
            continue
        for i, f in enumerate(doc.get("features", [])):
            blob = json.dumps(f)
            if rx.search(blob):
                hits += 1
                title = (f.get("properties") or {}).get("title", "?")
                print(f"  SWEEP {os.path.basename(p)} feature[{i}] {title!r}")
    print(f"  sweep: {hits} record(s) matched - inspect every hit by hand; "
          f"a count alone either blocks a clean set or passes a dirty one.")


def main():
    ap = argparse.ArgumentParser(description="Validate CPS v1 point sets.")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--target", choices=["public", "private"],
                    help="build target; 'public' refuses private data")
    ap.add_argument("--combine", action="store_true",
                    help="these sets will be MERGED into one database. "
                         "Validating many files is not combining them, so "
                         "licence-mixing rules only apply with this flag or "
                         "--target.")
    ap.add_argument("--sweep", metavar="NAMES",
                    help="comma-separated names/streets to flag for review")
    args = ap.parse_args()

    rep = Report()
    sets = [s for s in (validate_set(p, rep, args.target) for p in args.paths) if s]

    # Rule 2: report BOTH axes when sets combine. Never collapse them.
    # Only a real build combines. Plain multi-file validation must not be
    # treated as a merge, or the tool cries wolf on every routine check.
    if len(sets) > 1 and (args.combine or args.target):
        licences = {s["licence"] for s in sets}
        duties = licences & SHARE_ALIKE
        private_sets = [s for s in sets if s["visibility"] == "private"]

        print(f"combining {len(sets)} set(s): licences {sorted(licences)}")

        if duties:
            # Share-alike reaches the artifact, not just the repo.
            print(f"  OBLIGATION {sorted(duties)} is share-alike: the produced "
                  f"package must carry the licence and its attribution")
            for s in sets:
                if s["licence"] in ATTRIBUTION_REQUIRED:
                    print(f"    attribution owed via {set_label(s['path'])}")
            if private_sets:
                # Merging share-alike data into a private set creates a
                # Derivative Database. Separate files stay a Collective
                # Database, which ODbL does not infect.
                rep.err("combine",
                        f"share-alike input {sorted(duties)} is being combined "
                        f"with private set(s) "
                        f"{[set_label(s['path']) for s in private_sets]} - "
                        f"merging creates a Derivative Database and attaches "
                        f"share-alike to private outputs. Keep the sets as "
                        f"separate files (Collective Database) instead.")

        if args.target == "public" and private_sets:
            rep.err("combine",
                    f"private set(s) "
                    f"{[set_label(s['path']) for s in private_sets]} "
                    f"among the inputs to a public build - refusing to build")

    if args.sweep:
        sweep(args.paths, args.sweep, rep)

    total = sum(s["count"] for s in sets)
    print(f"{len(sets)} set(s), {total} feature(s)")
    for w in rep.warnings:
        print(f"WARN  {w}")
    for e in rep.errors:
        print(f"ERROR {e}")
    print(f"{len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
