## Why

Two small defects in `builders/compose.py` surface on every `localbox compose
generate` run:

1. The generator unconditionally writes `restart: unless-stopped` into every
   service definition, even overriding an explicit `extra={"restart": "always"}`
   the user put on the `ComposeConfig`. The test suite actively asserts this
   override (`test_named_field_overrides_extra`). Users cannot opt out of the
   restart policy, which is the wrong default — compose has no default restart
   policy of its own and that is usually what you want in local development.
2. Port entries like `0.0.0.0:80:80` are emitted as bare YAML scalars:
   ```
   ports:
     - 0.0.0.0:80:80
   ```
   Docker Compose logs `WARN[0000] unquoted port mapping: "0.0.0.0:80:80"`
   because a `host:host:container` triplet is legal YAML but fragile (YAML has
   historically parsed colon-separated strings as sexagesimals). Compose wants
   them quoted.

Both are tiny fixes that belong together: each is a defaults/formatting bug
in the same generator, each has a golden-file footprint, and bundling them
avoids two rounds of snapshot churn.

## What Changes

- Drop the hardcoded `service_def["restart"] = "unless-stopped"` assignment in
  `generate_service_definition`. Do **not** introduce a first-class `restart`
  field on `ComposeConfig` — users who want a restart policy already have
  `extra={"restart": "..."}`, which flows through naturally once the override
  is removed.
- Wrap every string written into `service_def["ports"]` in the existing
  `_QuotedStr` helper so PyYAML double-quotes them on emission, matching the
  format Docker Compose expects.
- Update `tests/test_compose_golden.py`:
  - `test_named_field_overrides_extra` becomes `test_extra_restart_passes_through`
    and asserts `defn["restart"] == "always"`.
  - `test_extra_empty_by_default` drops `restart` from `known_keys`.
  - The golden-file comparison test regenerates `tests/fixtures/docker-compose.golden.yml`.
- Update `tests/fixtures/docker-compose.golden.yml`: remove the three
  `restart: unless-stopped` lines and quote the port entries.

## Capabilities

### New Capabilities
- `compose-generation`: rules the docker-compose.yml generator follows beyond
  the env-resolution story already covered by `compose-env-resolution`. This
  change seeds the capability with two requirements: no default restart
  policy, and quoted port strings.

### Modified Capabilities
<!-- None — `compose-env-resolution` is unaffected; these are unrelated
     generator defaults/formatting rules. -->

## Impact

- Code:
  - `src/localbox/builders/compose.py` — delete the `service_def["restart"]`
    line in `generate_service_definition`; wrap port entries in `_QuotedStr`
    when populating `service_def["ports"]`.
- Tests:
  - `tests/test_compose_golden.py` — rename/rework two unit tests as above.
  - `tests/fixtures/docker-compose.golden.yml` — regenerate to drop `restart:`
    lines and double-quote the `ports:` list entries.
- Docs: none — restart policy was not documented, and port quoting is an
  internal formatting detail.
- APIs / dependencies: no public Python API changes, no new third-party deps.
  The user-visible change is strictly in the generated `docker-compose.yml`:
  no `restart` key unless the user asked for one, and ports are now quoted.
