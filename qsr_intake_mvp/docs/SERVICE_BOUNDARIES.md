# Service boundary map

## Runtime responsibilities
- scheduling
- config loading
- discover / collect loops
- checkpoint persistence
- heartbeat emission
- local bridge file polling and upload retries

## Worker responsibilities
- parsing
- mapping
- normalization
- trust scoring
- replay
- interpreting Aloha integration payloads and fallback exports after raw landing

## Data boundaries
- raw: immutable source truth
- staging: parsed source-shaped records
- canonical: normalized business facts
- meta: record-level trust
- derived: aggregates and convenience outputs
- local bridge: collection/checkpoint/upload only, never business interpretation
