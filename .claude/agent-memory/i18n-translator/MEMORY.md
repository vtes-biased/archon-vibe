# i18n Translator Memory

## Translation Infrastructure
- Files: `frontend/messages/{en,fr,es,pt,it}.json` — flat JSON, one key per string
- No plurals system observed; single string values throughout
- No interpolation variables observed yet

## Terminology Notes
- "check-in" (venue presence): borrowed loanword used as-is in PT/IT/ES. FR uses "enregistrement".
- "check-in" in PT (BR): "check-in" is natural; "check-in realizado" = confirmed.
- Avoid translating "failed" as "denied" (camera errors): use language-appropriate "failed access" phrasing.

## Known Fixes Applied
- EN `checkin_qr_scan_instruction`: "Archon app" → "the Archon app" (article required)
- FR/ES/PT/IT `checkin_qr_camera_error`: corrected "denied" wording to "failed" wording

## Links
- See `patterns.md` for per-language translation notes (TBD)
