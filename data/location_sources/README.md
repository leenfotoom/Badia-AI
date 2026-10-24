# Cell-location source data

BADIA AI resolves the existing 968 cell centroids to bilingual, human-readable
locations entirely offline. Runtime clicks never call a geocoding service.

## Included public sources

- `geoBoundaries-JOR-ADM1.geojson`: Jordan ADM1 boundaries from geoBoundaries,
  pinned to commit `9469f09592ced973a3448cf66b6100b741b64c0d`. The source metadata
  identifies 12 governorates, boundary year 2006, and the Creative Commons
  Attribution 2.5 Generic licence. Source:
  <https://www.geoboundaries.org/api/current/gbOpen/JOR/ADM1/>
- `GeoNames-JO.zip`: Jordan country dump from GeoNames, licensed under Creative
  Commons Attribution 4.0. Source:
  <https://download.geonames.org/export/dump/JO.zip>

Exact SHA-256 hashes of the included downloads are recorded in
`data/cell_locations.json`.

## Assignment method

`scripts/build_cell_locations.py` performs point-in-polygon assignment for each
cell centroid. Six centroids fall just outside the public ADM1 geometry because
of small coast/border differences between the project grid and the boundary
dataset. For those only, the script accepts a unique nearest ADM1 boundary no
more than 2 km away and records both the method and distance on the cell. It
fails rather than guessing when the distance is larger or the nearest result is
ambiguous.

Locality names come from significant GeoNames populated places in the same
governorate. A locality is shown only within 18 km. Otherwise a broad Badia
regional label is used where geographically appropriate, or the governorate
alone. This conservative rule avoids falsely placing remote desert cells inside
a city.

