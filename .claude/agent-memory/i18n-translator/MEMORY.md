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

## Extended Key Naming Conventions
- `pg_*` — Player Guide sections
- `og_*` — Organizer Guide sections
- `og_cfg_*` — Organizer Guide config tab descriptions
- `og_faq_q_*` / `og_faq_a_*` — FAQ questions/answers
- `help_player_guide_*` / `help_organizer_guide_*` — guide index entries

## VTES Term Glossary (Spanish)
- tournament = torneo, round = ronda, standings = clasificación
- check-in = registro de asistencia (noun), hacer check-in (verb)
- deck/decklist = mazo / lista de mazo (but keep "deck" for UI labels)
- player = jugador, organizer = organizador, judge = juez
- finals = finales, seed = cabeza de serie, toss = sorteo
- override = anulación, sanction = sanción
- caution = advertencia verbal, warning = advertencia
- disqualification = descalificación, standings adjustment = ajuste de clasificación
- raffle = sorteo, league = liga, offline mode = modo sin conexión
- game win (GW) = victoria de partida, predator = depredador, prey = presa
- drop out = retirar/retirarse, remove player = eliminar jugador
- Use "usted" (formal) for addressing users

## VTES Term Glossary (Brazilian Portuguese / pt)
- tournament = torneio, round = rodada, standings = classificação
- check-in = check-in (keep), deck/decklist = deck / lista de deck
- player = jogador, organizer = organizador, judge = juiz
- finals = final, seed = cabeça de chave, toss = sorteio
- override = substituição, sanction = sanção
- caution = advertência verbal, warning = advertência
- disqualification = desqualificação, standings adjustment = ajuste de classificação
- raffle = sorteio, league = liga, offline mode = modo offline
- GW = vitória de partida, predator = predador, prey = presa
- drop out = desistir, remove player = remover jogador
- Use "você" (not "tu")

## VTES Term Glossary (Italian)
- tournament = torneo, round = round (keep English)
- standings = classifica, check-in = check-in (keep)
- deck/decklist = deck / lista del mazzo
- player = giocatore, organizer = organizzatore, judge = giudice
- finals = finale/finali, seed = testa di serie, toss = sorteggio
- override = override (keep), sanction = sanzione
- caution = avvertimento verbale, warning = avvertimento
- disqualification = squalifica, standings adjustment = aggiustamento di classifica
- raffle = estrazione, league = campionato, offline mode = modalità offline
- predator = predatore, prey = preda
- GW/VP/TP kept as abbreviations
- "league" = "campionato" (confirmed: nav_leagues = "Campionati" in existing it.json)
- Use polite forms ("Lei") where addressing users

## Terms to Keep in English (all languages)
VEKN, VP, GW, TP, TWDA, VDB, Archon, Discord, Markdown, IndexedDB, QR,
Constructed, Limited, Standard, Grand Prix, Inner Circle (IC), NC, Prince,
passkey, multideck

## File Size Note
en.json exceeds 25000 token read limit. Use:
  python3 -c "import json; ..." to extract keys, or read with offset+limit (200 lines at a time).

## Bulk Translation Workflow
1. Extract missing keys: `python3 -c "import json; en=json.load(open('en.json')); xx=json.load(open('xx.json')); print([k for k in en if k not in xx])"`
2. Prepare translations dict in Python, `xx.update(translations)`, write back with `json.dump(..., ensure_ascii=False, indent=2)` + trailing newline `'\n'`
3. Validate: `python3 -c "import json; json.load(open('xx.json')); print('ok')"`
