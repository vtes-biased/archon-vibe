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

## Naming Conventions
- `nav_*` — navigation items
- `profile_*` — profile page strings
- `help_*` — help/docs section
- `common_*` — shared UI strings
- `tournament_*` / `tournaments_*` — tournament feature
- `rounds_*`, `finals_*`, `decks_*`, `players_*` — tournament sub-sections
- `sanction_*` / `sanction_mgr_*` — sanctions system
- `offline_*` — offline mode
- `checkin_qr_*` — QR check-in feature

## VTES Term Translations (verified from existing files)
| Term | fr | es | pt | it |
|------|----|----|----|----|
| Crypte/Crypt | Crypte | Cripta | Cripta | Cripta |
| Bibliothèque/Library | Bibliothèque | Biblioteca | Biblioteca | Biblioteca |
| VP (Victory Point) | VP | VP | VP | VP |
| GW (Game Win) | GW | GW | GW | GW |
| Predator/Prey | Prédateur/Proie | Predador/Presa | Predador/Presa | Predatore/Preda |
| Standings | Classement | Clasificación | Classificação | Classifica |
| Round | Ronde | Ronda | Rodada | Round (kept) |
| Finals | Finale | Final | Final | Finale |
| Seating | Placement | Distribución | Assentos | Disposizione |
| Check-in | Enregistrement / Pointer | Registro / Registrarse | Check-in | Check-in |
| Deck | Deck | Mazo (but "deck" used in context) | Deck | Mazzo (but "deck" used) |

Note: "Ronde" is used in fr for round (not "Round"). PT uses "Rodada" for round in some contexts.
IT: "round" is kept as loanword (not "turno"). IT finals = "Finali" (plural) for section headings, "finale" (singular) for time-config labels.

## Judge Terminology
| Lang | Term | Note |
|------|------|-------|
| fr | arbitre | established in override_judge_comment and judge_call_* |
| es | juez | established in override_judge_comment and judge_call_* |
| pt | juiz | established in override_judge_comment and judge_call_* |
| it | giudice | do NOT use "arbitro" |

## Clock Stop
| Lang | timer_clock_stop | timer_policy_clock_stop |
|------|-----------------|------------------------|
| fr | Arrêt d'horloge | Arrêt d'horloge |
| es | Parar reloj | Parada de reloj |
| pt | Parar relógio | Parada de relógio |
| it | Ferma orologio | Arresto orologio |

## Developer Portal
- fr: "Portail développeur", es: "Portal de desarrollador", pt: "Portal do desenvolvedor", it: "Portale sviluppatore"

## Help Section
- `help_toc_title`: fr=Sommaire, es=Contenido, pt=Sumário, it=Indice
- `help_back_to_list`: fr=Retour à l'aide, es=Volver a la ayuda, pt=Voltar à ajuda, it=Torna alla guida
- `nav_help`: fr=Aide, es=Ayuda, pt=Ajuda, it=Guida
