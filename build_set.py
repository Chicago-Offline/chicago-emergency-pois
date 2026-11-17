#!/usr/bin/env python3
"""Build pois.geojson (Canonical Point Schema v1) from raw open-data snapshots.

Reproducible replacement for the ad-hoc one-off that first generated this set.
Re-run after refreshing anything in raw/.

Two things this gets right that the first pass did not:

1. Hospitals come from hospitals-all.json, which was queried node+way+relation.
   The original er.json was a node-only Overpass query and therefore missed
   every hospital mapped as a building footprint -- Northwestern Memorial,
   Rush, Stroger, UIC, Illinois Masonic, Humboldt Park. 44 -> 55 ERs.

2. Device markers are disambiguated by their in-building location. The city
   encodes distinct device placements inside one building as sequential fake
   street numbers (the Field Museum occupies 1400-1425 S Lake Shore Dr), so
   collapsing on (building, address, type) leaves 26 markers all named
   "Field Museum - Bleed Kit". Unusable in ATAK search, and it collided the
   uuid5 marker uids until build_personal.py started keying on lat/lon too.
"""
import json, collections, os, re, uuid

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'raw')
HERE = os.path.dirname(os.path.abspath(__file__))
# Self-contained: the built set lands next to the raw data it came from.
# POI_OUT overrides it for consumers that vendor this set elsewhere.
OUT = os.environ.get('POI_OUT') or os.path.join(HERE, 'pois.geojson')
FETCHED = '2026-11-16'

# --- Canonical Point Schema v1 ----------------------------------------------
# Spec lives in the private mapping workspace; cps_validate.py is vendored into
# this repo (stdlib only) so the public set can be checked without it.
#
# This set is PUBLIC and ODbL-1.0. Those two facts are declared once, here, at
# set level, and the validator treats an unset value as an error rather than
# defaulting - defaults are how private data leaks into a public artifact.
SET_NAME = 'chicago-emergency-2026'
VISIBILITY = 'public'
LICENCE = 'ODbL-1.0'

# Stable id namespace. Must match mapping/scripts/ingest_pois_json.py, so a
# record built here and the same record ingested from the legacy pois.json
# resolve to the SAME uuid. That is what makes the migration verifiable by
# diff instead of by trust.
CPS_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/emuehlstein/cps/v1")

# class -> (Maki symbol, OSM tags).
# 'class' is the rendering hint, 'osm' is the authority on what the thing is.
# 'x-' prefixes a deliberate extension where Maki has no equivalent; the
# prefix is what lets the validator tell an extension from a typo.
CLASS_MAP = {
    'aed':            ('defibrillator', {'emergency': 'defibrillator'}),
    'bleed-kit':      ('x-bleed-kit',   {'emergency': 'bleeding_control_kit'}),
    'fire-station':   ('fire-station',  {'amenity': 'fire_station'}),
    'police-station': ('police',        {'amenity': 'police'}),
    'library':        ('library',       {'amenity': 'library'}),
    'warming-center': ('shelter',       {'amenity': 'shelter',
                                         'shelter_type': 'warming'}),
    'hospital-er':    ('hospital',      {'amenity': 'hospital',
                                         'emergency': 'yes'}),
}

# Per-record provenance. CPS requires dct:source on EVERY feature - a set-level
# citation alone cannot tell you which of eight datasets a given row came from,
# and ODbL attribution is owed per source.
SOURCES = {
    'mrzc-49gi': 'Chicago Data Portal dataset mrzc-49gi (AED / Stop-the-Bleed), fetched ' + FETCHED,
    '28km-gtjn': 'Chicago Data Portal dataset 28km-gtjn (fire stations), fetched ' + FETCHED,
    'z8bn-74gv': 'Chicago Data Portal dataset z8bn-74gv (police stations), fetched ' + FETCHED,
    'x8fc-8rcq': 'Chicago Data Portal dataset x8fc-8rcq (library branches), fetched ' + FETCHED,
    'qhfc-4cw2': 'Chicago Data Portal dataset qhfc-4cw2 (senior centers), fetched ' + FETCHED,
    'bspy-6mw8': 'Chicago Data Portal dataset bspy-6mw8 (DFSS community service centers), fetched ' + FETCHED,
    'osm':       'OpenStreetMap contributors via Overpass (node+way+relation), fetched ' + FETCHED,
}


def load(fn):
    d = json.load(open(os.path.join(RAW, fn)))
    if isinstance(d, dict):
        d = d.get('elements') or d.get('features') or []
    return d


def titlecase(s):
    s = (s or '').strip()
    if not s.isupper():
        return s
    return re.sub(r"\b([A-Za-z])([A-Za-z']*)",
                  lambda m: m.group(1).upper() + m.group(2).lower(), s)


def latlon(r):
    loc = r.get('location') or {}
    if 'coordinates' in loc:
        c = loc['coordinates']
        return float(c[1]), float(c[0])
    if loc.get('latitude'):
        return float(loc['latitude']), float(loc['longitude'])
    if r.get('latitude'):
        return float(r['latitude']), float(r['longitude'])
    return None, None


pois = []


def add(name, lat, lon, cat, source, address=None, notes=None, tags=None):
    """Append one CPS v1 Feature.

    Takes a class name, not an icon: the symbol and the OSM tags are both
    derived from CLASS_MAP so they cannot drift apart. An unregistered class
    is a hard error rather than a silently unstyled marker.
    """
    if lat is None or lon is None:
        return
    if cat not in CLASS_MAP:
        raise SystemExit('unregistered class %r on %r - add it to CLASS_MAP' % (cat, name))
    symbol, osm = CLASS_MAP[cat]
    lat = round(float(lat), 6)
    lon = round(float(lon), 6)

    props = {'title': name}
    if notes:
        props['description'] = notes
    props['marker-symbol'] = symbol
    props['class'] = cat
    props['osm'] = dict(osm)
    if address:
        props['addr:full'] = address
    if tags:
        props['tags'] = tags
    props['dct:source'] = SOURCES[source]
    props['dct:modified'] = FETCHED

    # uuid5 over set|title|lon,lat - reproducible across runs and machines, so
    # re-running this builder produces no git churn, and it doubles as the
    # ATAK dedupe key that stops a rebuilt package stacking duplicate markers.
    key = '%s|%s|%s,%s' % (SET_NAME, name, lon, lat)
    pois.append({
        'type': 'Feature',
        'id': str(uuid.uuid5(CPS_NS, key)),
        'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
        'properties': props,
    })


# --- AEDs and Stop-the-Bleed kits -------------------------------------------
# Collapse on (building, address, device_type) so a single reception desk with
# four kits is one marker, but keep genuinely separate placements apart.
groups = collections.defaultdict(list)
for r in load('mrzc-49gi.json'):
    key = ((r.get('building_name') or '').strip(),
           (r.get('address') or '').strip(),
           r.get('device_type'))
    groups[key].append(r)

# How many address rows does each building+type span? More than one means the
# building needs its markers disambiguated by where they sit inside it.
spread = collections.Counter((b, d) for (b, a, d) in groups)

for (bldg, addr, dev), rows in sorted(groups.items()):
    lat, lon = latlon(rows[0])
    count = sum(int(r.get('number_of_devices') or 1) for r in rows)
    spots = [(r.get('location_in_building') or '').strip() for r in rows]
    spots = [s for s in spots if s]
    is_aed = dev == 'AED'
    label = 'AED' if is_aed else 'Bleed Kit'
    base = bldg or addr
    name = '%s - %s' % (base, label)
    if spread[(bldg, dev)] > 1 and spots:
        name = '%s (%s) - %s' % (base, spots[0][:40], label)
    if count > 1:
        name += ' x%d' % count
    if spots:
        notes = '%d device(s). In building: %s' % (
            count, '; '.join(spots[:8]) + (' ...' if len(spots) > 8 else ''))
    else:
        notes = '%d device(s).' % count
    notes += ' Inside a building - access depends on the building being open.'
    add(name, lat, lon,
        'aed' if is_aed else 'bleed-kit', 'mrzc-49gi',
        address=addr + ', Chicago IL', notes=notes,
        tags=['chicago', 'indoor', 'aed' if is_aed else 'bleed-kit'])

# --- Fire stations -----------------------------------------------------------
for r in load('28km-gtjn.json'):
    lat, lon = latlon(r)
    add('CFD %s' % (r.get('name') or '?'), lat, lon, 'fire-station', '28km-gtjn',
        address='%s, %s IL %s' % (titlecase(r.get('address')),
                                  titlecase(r.get('city')), r.get('zip') or ''),
        notes='Chicago Fire Department engine %s. Staffed 24/7.'
              % (r.get('engine') or '?'),
        tags=['chicago', '24-7', 'staffed'])

# --- Police stations ---------------------------------------------------------
for r in load('z8bn-74gv.json'):
    lat, lon = latlon(r)
    d = r.get('district_name') or r.get('district') or '?'
    nm = 'CPD Headquarters' if d.lower() == 'headquarters' else 'CPD %s District' % d
    add(nm, lat, lon, 'police-station', 'z8bn-74gv',
        address='%s, %s IL %s' % (r.get('address'), r.get('city'), r.get('zip') or ''),
        notes='Chicago Police district station. Lobby staffed 24/7.',
        tags=['chicago', '24-7', 'staffed'])

# --- Libraries ---------------------------------------------------------------
for r in load('x8fc-8rcq.json'):
    lat, lon = latlon(r)
    url = (r.get('website') or {}).get('url', '')
    add('CPL %s' % (r.get('branch_') or '?'), lat, lon, 'library', 'x8fc-8rcq',
        address='%s, %s IL %s' % (r.get('address'), r.get('city'), r.get('zip') or ''),
        notes='Chicago Public Library branch. Hours: %s. Phone %s. %s '
              'Daytime warming/cooling refuge, public restrooms, power and wifi.'
              % ((r.get('service_hours') or 'unknown').strip(),
                 r.get('phone') or 'n/a', url),
        tags=['chicago', 'daytime-only', 'warming', 'cooling', 'wifi', 'restroom'])

# --- Senior centers ----------------------------------------------------------
for r in load('qhfc-4cw2.json'):
    lat, lon = latlon(r)
    add('%s Senior Center' % (r.get('site_name') or '?'), lat, lon,
        'warming-center', 'qhfc-4cw2',
        address='%s, %s IL %s' % (r.get('address'), r.get('city'), r.get('zip') or ''),
        notes='%s. Hours: %s. Phone %s. Designated warming/cooling site during '
              'weather emergencies - call to confirm extended hours.'
              % (r.get('program') or 'Senior center',
                 (r.get('hours_of_operation') or 'unknown').strip(),
                 r.get('phone') or 'n/a'),
        tags=['chicago', 'warming', 'cooling', 'hours-unverified'])

# --- DFSS community service centers -----------------------------------------
# The dataset reports M-F 9am-5pm for all six. That is wrong in the way that
# matters: these are the city's primary extreme-cold warming centers and run
# extended or 24-hour hours during an activation. Hand-annotated.
for r in load('bspy-6mw8.json'):
    lat, lon = latlon(r)
    add('DFSS %s' % (r.get('site') or '?'), lat, lon,
        'warming-center', 'bspy-6mw8',
        address='%s, %s IL %s' % (r.get('address'), r.get('city'), r.get('zip') or ''),
        notes="DFSS Community Service Center. Dataset lists %s, but these are the "
              "city's primary warming centers and run EXTENDED / 24-hour hours during "
              "extreme-cold activations - the dataset does NOT reflect that. Call 311 "
              "or %s to confirm. Hours hand-annotated, not from the dataset."
              % ((r.get('hours_of_operation') or 'unknown').strip(),
                 r.get('phone') or '311'),
        tags=['chicago', 'warming', 'primary', 'hours-corrected'])

# --- Hospitals with an emergency department ---------------------------------
for e in load('hospitals-all.json'):
    t = e.get('tags') or {}
    if t.get('emergency') != 'yes' or not t.get('name'):
        continue
    lat, lon = e.get('lat'), e.get('lon')
    if lat is None and e.get('center'):
        lat, lon = e['center']['lat'], e['center']['lon']
    if lat is None:
        continue
    a = ' '.join(x for x in [t.get('addr:housenumber'), t.get('addr:street'),
                             t.get('addr:city')] if x)
    notes = 'Emergency department (OSM emergency=yes). 24/7 walk-in ER.'
    if t.get('phone'):
        notes += ' Phone %s.' % t['phone']
    if t.get('operator'):
        notes += ' Operator: %s.' % t['operator']
    add(t['name'], lat, lon, 'hospital-er', 'osm',
        address=a or None, notes=notes,
        tags=['chicago', '24-7', 'hospital', 'er'])

DESCRIPTION = (
    "Chicago-area emergency infrastructure snapshot, fetched %s from the Chicago Data "
    "Portal and OpenStreetMap. Public-access AEDs and Stop-the-Bleed kits, fire and "
    "police stations, library branches usable as daytime warming/cooling refuge, DFSS "
    "community service centers and senior centers used as warming sites, and hospitals "
    "with an emergency department. "
    "This is a dated snapshot of published open data, not a curated list - hours and "
    "device placement drift, and most AED/bleed-kit markers sit inside buildings only "
    "reachable when the building is open. "
    "Known defect: the DFSS dataset reports M-F 9am-5pm for all six centers; those are "
    "the primary extreme-cold warming centers and actually run extended or 24-hour "
    "hours during an activation. Those notes are hand-corrected. Call 311 to confirm "
    "before relying on any of this." % FETCHED)

ATTRIBUTION = ('Chicago Data Portal (City of Chicago open data) and '
               'OpenStreetMap contributors. OSM-derived records are '
               'ODbL-1.0; see ATTRIBUTION.md.')

doc = {
    'type': 'FeatureCollection',
    'name': 'Chicago Emergency 2026',
    'description': DESCRIPTION,
    # Declared, never defaulted. cps_validate.py errors on either being unset.
    'visibility': VISIBILITY,
    'dct:license': LICENCE,
    'dct:source': ATTRIBUTION,
    'dct:modified': FETCHED,
    'features': pois,
}
with open(OUT, 'w') as fh:
    json.dump(doc, fh, indent=2, ensure_ascii=False)
    fh.write('\n')

prop = lambda f, k: f['properties'].get(k)
counts = collections.Counter(prop(f, 'class') for f in pois)
ids = {f['id'] for f in pois}
names = collections.Counter(prop(f, 'title') for f in pois)
print('wrote %s' % OUT)
print('total features: %d  (visibility=%s licence=%s)' % (len(pois), VISIBILITY, LICENCE))
for k, v in sorted(counts.items(), key=lambda x: -x[1]):
    print('  %-15s %3d' % (k, v))
print('CPS ids unique: %d / %d  %s'
      % (len(ids), len(pois), 'OK' if len(ids) == len(pois) else 'COLLISION'))
dupnames = [(k, v) for k, v in names.items() if v > 1]
print('duplicate display names: %d' % len(dupnames))
for k, v in sorted(dupnames, key=lambda x: -x[1])[:5]:
    print('   %dx %s' % (v, k))
print('\nnow run:  python3 cps_validate.py --target public %s' % os.path.basename(OUT))
