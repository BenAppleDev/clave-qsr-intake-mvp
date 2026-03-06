# Service boundary map

## Runtime responsibilities
- scheduling
- config loading
- discover / collect loops
- checkpoint persistence
- heartbeat emission

## Worker responsibilities
- parsing
- mapping
- normalization
- trust scoring
- replay

## Data boundaries
- raw: immutable source truth
- staging: parsed source-shaped records
- canonical: normalized business facts
- meta: record-level trust
- derived: aggregates and convenience outputs
