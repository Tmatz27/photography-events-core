# Sanitized public provider contract fixtures

The iNaturalist and WFIGS responses were captured on 2026-10-08 through official
public APIs with a descriptive User-Agent and spaced requests. Taxonomy,
native times, field topology and quality/visibility/category semantics are
retained. Stable identity fields and observation/perimeter coordinates are
fictional; descriptions are replaced; private fields, users and photos are
discarded. The GeoJSON transport feature ID does not establish source identity.

NWS was captured from the existing approved public Pismo point: one active CAP
alert and two forecast periods. Alert IDs/references and geometry are fictional;
only the parser's allowed public weather fields remain. Tests reset observation/
model times to a deterministic baseline and modify fields to create adversarial
variants. No test reaches the Internet.

RX/final perimeter, private/obscured/DATE-only/unknown-quality/malformed records
are explicit synthetic variants of the public response structure. They are not
claimed as live samples of those special cases. The current WFIGS view filters
out inactive/non-public history. Optional live tools are manual only.
