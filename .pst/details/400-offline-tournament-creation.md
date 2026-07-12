# Offline tournament creation — resolution notes

Landed as detect-and-adapt on the create form: when `navigator.onLine` is false
(reactive via window online/offline listeners), submit routes to
`createTournamentOffline` (the previously dead chain: local WASM
`create_tournament` → born `offline_mode` + device-locked → `markOffline`), with
a warning banner on the form. The backend `go_online` endpoint already handles a
tournament the server has never seen (`existing is None` → upsert-insert), and
officials-only comes free (engine `can_manage_tournaments` gate + the client
role gate on the form). VEKN calendar push: nothing to do — the organizer's
"Publish to VEKN" action and the hourly batch push cover it once online.

## GeoNames-embark subtask dropped (wrong premise)

The ticket called for embarking `cities.json` (~5.6MB) into IndexedDB so
"venue autocomplete works offline". Investigation at implementation time:

- **The tournament form's venue autocomplete never uses GeoNames.**
  `VenueAutocomplete.svelte` suggests from `getVenuesByCountry` — venues of
  past tournaments already in IndexedDB — so it is offline-first by
  construction. The country select uses the eagerly-bundled ~32KB
  `countries.json`.
- GeoNames cities feed only `CityAutocomplete` (profile / member editing),
  which is not part of the create flow — and even there the
  `geonames-cities` Vite chunk is precached by the hand-rolled service
  worker (`ASSETS = [...build, ...files]`, no size cap), so it resolves
  offline once the SW is installed.

Free-text venue entry (the requested fallback) is the input's default
behavior. Embarking 5.6MB into IndexedDB would have duplicated an
already-precached asset for a flow that doesn't consume it.
