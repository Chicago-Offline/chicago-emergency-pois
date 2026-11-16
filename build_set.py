#!/usr/bin/env python3
"""Build sets/chicago-emergency-2026/pois.json from raw open-data snapshots.

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
import json, collections, os, re

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'raw')
HERE = os.path.dirname(os.path.abspath(__file__))
# Self-contained: the built set lands next to the raw data it came from.
# POI_OUT overrides it for consumers that vendor this set elsewhere.
OUT = os.environ.get('POI_OUT') or os.path.join(HERE, 'pois.json')
FETCHED = '2026-11-16'


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


def add(name, lat, lon, cat, icon, address=None, notes=None, tags=None):
    if lat is None or lon is None:
        return
    p = {'name': name, 'lat': round(float(lat), 6), 'lon': round(float(lon), 6),
         'category': cat, 'icon': icon}
    if address:
        p['address'] = address
    if notes:
        p['notes'] = notes
    if tags:
        p['tags'] = tags
    pois.append(p)


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
    notes += (' Source: Chicago Data Portal mrzc-49gi, fetched %s.'
              ' Inside a building - access depends on the building being open.' % FETCHED)
    add(name, lat, lon,
        'aed' if is_aed else 'bleed-kit',
        'medical-aed' if is_aed else 'medical-first-aid',
        address=addr + ', Chicago IL', notes=notes,
        tags=['chicago', 'indoor', 'aed' if is_aed else 'bleed-kit'])

# --- Fire stations -----------------------------------------------------------
for r in load('28km-gtjn.json'):
    lat, lon = latlon(r)
    add('CFD %s' % (r.get('name') or '?'), lat, lon, 'fire-station', 'firehouse',
        address='%s, %s IL %s' % (titlecase(r.get('address')),
                                  titlecase(r.get('city')), r.get('zip') or ''),
        notes='Chicago Fire Department engine %s. Staffed 24/7. '
              'Source: Chicago Data Portal 28km-gtjn, fetched %s.'
              % (r.get('engine') or '?', FETCHED),
        tags=['chicago', '24-7', 'staffed'])

# --- Police stations ---------------------------------------------------------
for r in load('z8bn-74gv.json'):
    lat, lon = latlon(r)
    d = r.get('district_name') or r.get('district') or '?'
    nm = 'CPD Headquarters' if d.lower() == 'headquarters' else 'CPD %s District' % d
    add(nm, lat, lon, 'police-station', 'police',
        address='%s, %s IL %s' % (r.get('address'), r.get('city'), r.get('zip') or ''),
        notes='Chicago Police district station. Lobby staffed 24/7. '
              'Source: Chicago Data Portal z8bn-74gv, fetched %s.' % FETCHED,
        tags=['chicago', '24-7', 'staffed'])

# --- Libraries ---------------------------------------------------------------
for r in load('x8fc-8rcq.json'):
    lat, lon = latlon(r)
    url = (r.get('website') or {}).get('url', '')
    add('CPL %s' % (r.get('branch_') or '?'), lat, lon, 'library', 'Libraries',
        address='%s, %s IL %s' % (r.get('address'), r.get('city'), r.get('zip') or ''),
        notes='Chicago Public Library branch. Hours: %s. Phone %s. %s '
              'Daytime warming/cooling refuge, public restrooms, power and wifi. '
              'Source: Chicago Data Portal x8fc-8rcq, fetched %s.'
              % ((r.get('service_hours') or 'unknown').strip(),
                 r.get('phone') or 'n/a', url, FETCHED),
        tags=['chicago', 'daytime-only', 'warming', 'cooling', 'wifi', 'restroom'])

# --- Senior centers ----------------------------------------------------------
for r in load('qhfc-4cw2.json'):
    lat, lon = latlon(r)
    add('%s Senior Center' % (r.get('site_name') or '?'), lat, lon,
        'warming-center', 'Emergency Shelter',
        address='%s, %s IL %s' % (r.get('address'), r.get('city'), r.get('zip') or ''),
        notes='%s. Hours: %s. Phone %s. Designated warming/cooling site during '
              'weather emergencies - call to confirm extended hours. '
              'Source: Chicago Data Portal qhfc-4cw2, fetched %s.'
              % (r.get('program') or 'Senior center',
                 (r.get('hours_of_operation') or 'unknown').strip(),
                 r.get('phone') or 'n/a', FETCHED),
        tags=['chicago', 'warming', 'cooling', 'hours-unverified'])

# --- DFSS community service centers -----------------------------------------
# The dataset reports M-F 9am-5pm for all six. That is wrong in the way that
# matters: these are the city's primary extreme-cold warming centers and run
# extended or 24-hour hours during an activation. Hand-annotated.
for r in load('bspy-6mw8.json'):
    lat, lon = latlon(r)
    add('DFSS %s' % (r.get('site') or '?'), lat, lon,
        'warming-center', 'Emergency Shelter',
        address='%s, %s IL %s' % (r.get('address'), r.get('city'), r.get('zip') or ''),
        notes="DFSS Community Service Center. Dataset lists %s, but these are the "
              "city's primary warming centers and run EXTENDED / 24-hour hours during "
              "extreme-cold activations - the dataset does NOT reflect that. Call 311 "
              "or %s to confirm. Source: Chicago Data Portal bspy-6mw8, fetched %s; "
              "hours hand-annotated."
              % ((r.get('hours_of_operation') or 'unknown').strip(),
                 r.get('phone') or '311', FETCHED),
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
    notes += (' Source: OpenStreetMap via Overpass (node+way+relation), fetched %s.'
              % FETCHED)
    add(t['name'], lat, lon, 'hospital-er', 'Hospitals',
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

doc = {'name': 'Chicago Emergency 2026', 'description': DESCRIPTION, 'pois': pois}
json.dump(doc, open(OUT, 'w'), indent=2)

counts = collections.Counter(p['category'] for p in pois)
keys = {(p['category'], p['name'], p['lat'], p['lon']) for p in pois}
names = collections.Counter(p['name'] for p in pois)
print('wrote %s' % OUT)
print('total POIs: %d' % len(pois))
for k, v in sorted(counts.items(), key=lambda x: -x[1]):
    print('  %-15s %3d' % (k, v))
print('marker-uid keys unique: %d / %d  %s'
      % (len(keys), len(pois), 'OK' if len(keys) == len(pois) else 'COLLISION'))
dupnames = [(k, v) for k, v in names.items() if v > 1]
print('duplicate display names: %d' % len(dupnames))
for k, v in sorted(dupnames, key=lambda x: -x[1])[:5]:
    print('   %dx %s' % (v, k))
