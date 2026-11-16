# Attribution

This database is assembled from two upstream sources with different terms.

## OpenStreetMap - 55 records (hospitals with an emergency department)

(c) OpenStreetMap contributors.

OSM data is published under the **Open Database License (ODbL) v1.0**. ODbL is a
share-alike licence for *databases*: any publicly distributed derived database
must carry the same licence and attribution. Because those 55 records are mixed
into `pois.json`, the combined database in this repository is released under
ODbL - see [LICENSE](LICENSE).

If you redistribute this data, or a package built from it, you must:

- credit "(c) OpenStreetMap contributors"
- keep the data under ODbL
- make any modified database available under the same terms

Reference: https://www.openstreetmap.org/copyright

## Chicago Data Portal - 668 records

City of Chicago open data, retrieved from https://data.cityofchicago.org

| Dataset ID | Contents | Records |
|---|---|---|
| `mrzc-49gi` | AEDs & Stop-the-Bleed kits | 444 |
| `28km-gtjn` | Fire stations | 92 |
| `x8fc-8rcq` | Library branches | 82 |
| `z8bn-74gv` | Police stations | 23 |
| `qhfc-4cw2` | Senior centers | 21 |
| `bspy-6mw8` | DFSS community service centers | 6 |

Published under the City of Chicago's Open Data Terms of Use. The City provides
these datasets as-is and makes no warranty as to accuracy, completeness or
fitness for any purpose, and is not the author of this repository.

## Editorial additions

The hours annotations on the six DFSS community service centers are
hand-authored corrections, not upstream data. They are flagged
`hours-corrected` in the `tags` field and the correction is described inline in
each record's `notes`.

## Not an official source

This repository is not affiliated with, endorsed by, or operated by the City of
Chicago, the Chicago Fire Department, the Chicago Police Department, the Chicago
Public Library, DFSS, or any hospital or health system named in the data.
