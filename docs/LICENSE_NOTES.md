# Source and redistribution notes

The City of Tampa's Conditions and Use page states that data on its system is
public information and is generally available to copy or distribute. It also
disclaims guarantees about accuracy and completeness and warns that map data
is a reasonable representation rather than an official survey or deed.

Source: https://www.tampa.gov/about-us/tampagov/conditions-and-use

City seals, copyrighted artwork, and unrelated protected material are not
included. City of Tampa and Tampa GIS attribution should be retained.

The v0.8.0 public archive is City-only, source-bounded, and privacy-minimized.
Configured contact and source-user/editor fields are removed from the bundled
core GeoJSON and processed source properties. Separately dated context
snapshots use strict analytical field whitelists and exclude owner, mailing,
contact, legal-description, and source-user/editor fields. It excludes the HCPA archive,
extracted DBF, and HCPA nearest-centroid fallback rows. An optional local
HCPA-enriched build remains available for research, but should not be
redistributed until the current HCPA terms are confirmed.

The MIT license applies to original code and documentation, not to government
source records. `DATA_LICENSE.md` is the controlling release note for data
scope and attribution.

This note describes observed source terms and is not legal advice.
