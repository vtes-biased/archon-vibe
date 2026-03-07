# Phase 2: Leagues — Design Notes

## Legacy Archon Reference (separate repo: archon)
- Backend: `src/archon/app/api/league.py`
- Models: `src/archon/models.py` lines 75-84, 228-232, 301-420
- Standings computation: `src/archon/db.py` lines 1403-1509
- Frontend: `src/front/league.ts`

## League Model Fields
```
uid, modified, deleted_at (BaseObject)
name, kind (League|Meta-League), standings_mode (RTP|Score|GP)
format (optional), online, country (optional=worldwide)
start, finish (optional=ongoing), timezone, description
organizers_uids[], parent_uid (optional, FK->leagues)
allow_no_finals (hint for Score leagues)
```

## Standings Modes Detail

### Score
- Sum prelim round GW/VP/TP per player across all finished league tournaments
- Subtract finals table scores for finalists (key subtlety!)
- Rank by GW desc > VP desc > TP desc
- Encourages participation over finalist performance

### RTP (Rating Points)
- Uses existing `compute_rating_points()` from engine/src/ratings.rs
- Formula: 5 + 4*VP + 8*GW + finalist_bonus * coefficient
- Sum across tournaments, rank by total desc

### GP (Grand Prix)
- Position-based: Winner=25, Finalists=15, 6th-10th=10..6, 11th+=3
- Sum across tournaments, rank by total desc
- From legacy archon: `src/archon/engine.py` lines 1242-1258

## Architecture Decision: Standings Not in SSE
- League SSE payload = config only (lean)
- Frontend computes standings from IndexedDB tournaments via WASM
- Avoids large SSE payloads and complex server-side computation during streaming
- Consistent with offline-first: all data needed is already in IndexedDB

## Key Naming
- PRODUCT.md uses "RTP", "GW/VP/TP", "Championship"
- Legacy archon uses "RTP", "Score", "GP"
- Decision: use RTP/Score/GP (matches legacy, concise)
