# Data terms and attribution

## Public release scope

Version 0.7.0's public archive is a **City-only, source-bounded edition**. It
contains privacy-minimized source snapshots and derived outputs from City of
Tampa-hosted GIS services. Before packaging, the build removes project-contact
name, phone, and email fields and configured source-user/editor fields from the
GeoJSON snapshots and processed properties. It does not contain the HCPA
bulk-download archive, extracted DBF, or HCPA nearest-centroid fallback
matches.

The MIT license in `LICENSE` applies to Jack Lenga's original code and
documentation only. It does not relicense government source records.

## City of Tampa data

The City of Tampa states on its Conditions and Use page that information on
its system is public information and is generally available to copy or
distribute, while disclaiming completeness and survey-level accuracy. Users
must review the current terms themselves:

https://www.tampa.gov/about-us/tampagov/conditions-and-use

Retain attribution to the City of Tampa and Tampa GIS, retain the source URLs
and retrieval timestamp, and do not imply City endorsement. City seals,
copyrighted artwork, and unrelated protected material are not included.

Recommended attribution:

> Source records: City of Tampa and Tampa GIS. Dataset integration and
> documentation: Jack Lenga, Tampa Published Development Records:
> Source-Bounded Census.

## Optional HCPA enrichment

`build_release.py --include-hcpa` can create a non-public experimental local
build using the Hillsborough County Property Appraiser latitude/longitude
table. Explicit general-purpose redistribution terms were not established for
that bulk file. The public archive therefore excludes this optional input and
its fallback match rows. Confirm HCPA's current terms before distributing an
HCPA-enriched edition.

This file records the release's source and attribution policy; it is not legal
advice.
