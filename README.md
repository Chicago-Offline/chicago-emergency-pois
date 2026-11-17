# Chicago Emergency POIs

723 emergency-infrastructure points for Chicago, built entirely from published
open data. Public-access AEDs and Stop-the-Bleed kits, fire and police stations,
library branches usable as daytime warming/cooling refuge, DFSS community service
centers and senior centers used as warming sites, and hospitals with an emergency
department.

Snapshot date: **2026-11-16**

| `class` | Count |
|---|---|
| bleed-kit | 381 |
| fire-station | 92 |
| library | 82 |
| aed | 63 |
| hospital-er | 55 |
| warming-center | 27 |
| police-station | 23 |
| **total** | **723** |

## Read this before relying on it

This is a **dated snapshot of published open data, not a curated or verified list.**

- **Most AED and bleed-kit markers are inside buildings.** They are only reachable
  when the building is open. An AED pin is not a promise of 3am access.
- **Hours drift.** Library and senior-center hours come from the datasets and are
  not re-verified here.
- **Known upstream defect:** the DFSS dataset reports M-F 9am-5pm for all six
  community service centers. Those are the city's *primary* extreme-cold warming
  centers and run extended or 24-hour hours during an activation. Those six notes
  are hand-corrected in the build; the underlying dataset is still wrong.
- **Call 311 to confirm** before depending on any of this in an emergency.

Every POI carries its originating dataset and fetch date in its `dct:source`
property - per feature, not just once for the file, because a set-level citation
cannot tell you which of the eight datasets a given point came from, and ODbL
attribution is owed per source.

## Provenance

| Source | POIs | Dataset |
|---|---|---|
| Chicago Data Portal | 444 | `mrzc-49gi` - AEDs & Stop-the-Bleed kits |
| Chicago Data Portal | 92 | `28km-gtjn` - Fire stations |
| Chicago Data Portal | 82 | `x8fc-8rcq` - Library branches |
| OpenStreetMap (Overpass) | 55 | hospitals with `emergency=yes` |
| Chicago Data Portal | 23 | `z8bn-74gv` - Police stations |
| Chicago Data Portal | 21 | `qhfc-4cw2` - Senior centers |
| Chicago Data Portal | 6 | `bspy-6mw8` - DFSS community service centers |

All 723 records cite a source. See [ATTRIBUTION.md](ATTRIBUTION.md) and
[LICENSE](LICENSE) - the OSM-derived records carry ODbL obligations.

## Schema

`pois.geojson` is plain GeoJSON - any GIS tool will open it - constrained to a
profile called **Canonical Point Schema v1 (CPS)**. Validate with the bundled
`cps_validate.py` (standard library only, no install):

```bash
python3 cps_validate.py --target public pois.geojson
```

```json
{
  "type": "FeatureCollection",
  "name": "Chicago Emergency 2026",
  "description": "...",
  "visibility": "public",
  "dct:license": "ODbL-1.0",
  "dct:source": "Chicago Data Portal ... and OpenStreetMap contributors ...",
  "dct:modified": "2026-11-16",
  "features": [
    {
      "type": "Feature",
      "id": "f1d2...",
      "geometry": {"type": "Point", "coordinates": [-87.677794, 41.870282]},
      "properties": {
        "title": "Jesse Brown VA Medical Center",
        "description": "Emergency department. ...",
        "marker-symbol": "hospital",
        "class": "hospital-er",
        "osm": {"amenity": "hospital", "emergency": "yes"},
        "addr:full": "820 South Damen Avenue Chicago",
        "tags": ["chicago", "24-7", "hospital", "er"],
        "dct:source": "OpenStreetMap contributors via Overpass ..., fetched 2026-11-16",
        "dct:modified": "2026-11-16"
      }
    }
  ]
}
```

Notes on the profile:

- **`id` is `uuid5(CPS_NS, "<set>|<title>|<lon>,<lat>")`** - reproducible across
  runs and machines, so rebuilding produces no diff noise, and it doubles as a
  stable dedupe key downstream (re-importing a rebuilt set will not stack
  duplicate markers).
- **`class` vs `osm` vs `marker-symbol`** - `class` is our category, `osm` is the
  authority on what the thing actually is, `marker-symbol` is only a rendering
  hint ([Maki](https://labs.mapbox.com/maki-icons/) names). An `x-` prefix marks
  a deliberate extension where Maki has no equivalent (`x-bleed-kit`), which is
  what lets a validator tell an extension from a typo.
- **`visibility` and `dct:license` are declared, never defaulted.** The validator
  errors if either is missing rather than assuming one.

Useful `tags` for filtering: `24-7`, `staffed`, `indoor`, `daytime-only`,
`warming`, `cooling`, `wifi`, `restroom`, `hours-unverified`, `hours-corrected`.

## Rebuilding

```bash
python3 build_set.py                             # rewrites pois.geojson from raw/
POI_OUT=/tmp/pois.geojson python3 build_set.py   # build elsewhere
python3 cps_validate.py --target public pois.geojson
```

`raw/` holds the eight source snapshots so the set is reproducible from this
clone alone, with no network access. Refresh a file in `raw/` and re-run.

### Two corrections already baked into the build

1. **Hospitals are queried node+way+relation.** The original node-only Overpass
   query missed every hospital mapped as a building footprint - Northwestern
   Memorial, Rush, Stroger, UIC, Illinois Masonic, Humboldt Park. 44 -> 55 ERs.
   `raw/er.json` is that superseded node-only query, kept as a record; the build
   reads `raw/hospitals-all.json`.
2. **Device markers are disambiguated by in-building location.** The city encodes
   distinct placements inside one building as sequential fake street numbers (the
   Field Museum occupies 1400-1425 S Lake Shore Dr), so collapsing on
   (building, address, type) produced 26 markers all named "Field Museum - Bleed
   Kit" - unusable in search, and it collided marker UIDs downstream.
