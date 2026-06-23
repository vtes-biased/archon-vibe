# i18n Translator Memory

## Translation Infrastructure
- Files: `frontend/messages/{en,fr,es,pt,it}.json` — flat JSON, one key per string. No plurals/interpolation system; English copy must hand-pluralize (`{count} round(s)`).
- Key order in every locale follows `en.json` (source of truth): insert a new key immediately after the same preceding key as in en.json.
- `en.json` exceeds the 25k-token read limit — extract keys via `python3` or read with offset+limit.

## Tone & Register
- Semi-formal throughout, no slang. VTES game terms (Methuselah, Crypt, Pool, Torper…) use official Black Chantry rulebook translations — check blackchantry.com/utilities/rulebook/ before coining one; flag uncertain terms for human review.
- Organizer/management UI (offline session, force-unlock, takeover): plain administrative language, no game flavour.
- Form of address: es "usted", pt "você" (not "tu"), it "Lei", fr vouvoiement — formal throughout.
- "check-in" is a loanword kept as-is in es/pt/it (pt "check-in realizado" = confirmed); fr uses Enregistrement/Pointer. Don't render "failed" as "denied" (camera errors) — use "failed access" phrasing.

## VTES / UI Term Glossary (verified from existing locale files; `—` = not yet recorded, derive from en + rulebook)
| en | fr | es | pt | it |
|----|----|----|----|----|
| tournament | — | torneo | torneio | torneo |
| round | Ronde | ronda | rodada | round* |
| standings | Classement | clasificación | classificação | classifica |
| standings adjustment | — | ajuste de clasificación | ajuste de classificação | aggiustamento di classifica |
| finals | Finale | final | final | finale† |
| seating | Placement | distribución | assentos | disposizione |
| seat (position) | Placement | asiento | assento | posto |
| open seat | Placement libre | asiento libre | assento livre | posto libero |
| move here | Déplacer ici | mover aquí | mover aqui | sposta qui |
| seed | — | cabeza de serie | cabeça de chave | testa di serie |
| toss | — | sorteo | sorteio | sorteggio |
| raffle | — | sorteo | sorteio | estrazione |
| check-in | Enregistrement / Pointer | registro (de asistencia) / registrarse | check-in | check-in |
| player | — | jugador | jogador | giocatore |
| organizer | — | organizador | organizador | organizzatore |
| judge | arbitre | juez | juiz | giudice‡ |
| override | — | anulación | substituição | override* |
| sanction | — | sanción | sanção | sanzione |
| caution | — | advertencia verbal | advertência verbal | avvertimento verbale |
| warning | — | advertencia | advertência | avvertimento |
| disqualification | — | descalificación | desqualificação | squalifica |
| league | — | liga | liga | campionato |
| offline mode | — | modo sin conexión | modo offline | modalità offline |
| deck / decklist | Deck | mazo / lista de mazo¶ | deck / lista de deck | deck / lista del mazzo¶ |
| drop out | — | retirar(se) | desistir | — |
| remove player | — | eliminar jugador | remover jogador | — |
| predator / prey | Prédateur / Proie | depredador / presa‖ | predador / presa | predatore / preda |
| game win | — | victoria de partida | vitória de partida | — |
| crypt | Crypte | cripta | cripta | cripta |
| library | Bibliothèque | biblioteca | biblioteca | biblioteca |
| clock stop | Arrêt d'horloge | parar reloj / parada de reloj | parar relógio / parada de relógio | ferma orologio / arresto orologio |
| developer portal | Portail développeur | Portal de desarrollador | Portal do desenvolvedor | Portale sviluppatore |
| proxy (player) | Proxy | Proxy | Proxy | Proxy |
| random (deck label) | Aléatoire | Aleatorio | Aleatório | Casuale |
| drop player (organiser action) | Retirer le joueur | Retirar jugador | Retirar jogador | Ritira giocatore |

\* it keeps English loanword (round, not "turno"; override, not translated).
† finals it: "Finali" (plural) for section headings, "finale" (singular) for time-config labels.
‡ judge it: giudice — never "arbitro".
¶ deck: "mazo"(es)/"mazzo"(it) exist but UI labels keep "deck".
‖ predator es: an older table cell had "Predador" (likely a pt copy) — "depredador" is the correct Spanish; verify before reuse.
- Clock stop has two keys: `timer_clock_stop` (imperative/button) vs `timer_policy_clock_stop` (noun/policy) — es/pt/it differ per the two cells above; fr is identical for both.
- Keep in English (all langs): VEKN, VP, GW, TP, TWDA, VDB, Archon, Discord, Markdown, IndexedDB, QR, Constructed, Limited, Standard, Grand Prix, Inner Circle (IC), NC, Prince, passkey, multideck.

## Key Naming Conventions
- `nav_*` nav · `profile_*` profile · `help_*` help/docs · `common_*` shared · `offline_*` offline mode · `checkin_qr_*` QR check-in
- `tournament_*`/`tournaments_*` + sub-sections `rounds_*`, `finals_*`, `decks_*`, `players_*`
- `sanction_*`/`sanction_mgr_*` sanctions
- Help guides: `pg_*` Player Guide · `og_*` Organizer Guide (`og_cfg_*` config-tab, `og_faq_q_*`/`og_faq_a_*` FAQ) · `help_player_guide_*`/`help_organizer_guide_*` index entries
- Verified help strings: `help_toc_title` (fr Sommaire/es Contenido/pt Sumário/it Indice); `help_back_to_list` (fr Retour à l'aide/es Volver a la ayuda/pt Voltar à ajuda/it Torna alla guida); `nav_help` (fr Aide/es Ayuda/pt Ajuda/it Guida)

## Bulk Translation Workflow
1. Missing keys: `python3 -c "import json; en=json.load(open('en.json')); xx=json.load(open('xx.json')); print([k for k in en if k not in xx])"`
2. Build translations dict, `xx.update(translations)`, write with `json.dump(..., ensure_ascii=False, indent=2)` + trailing `'\n'`
3. Validate: `python3 -c "import json; json.load(open('xx.json')); print('ok')"`
4. Compile + check: `npx @inlang/paraglide-js compile --project project.inlang --outdir src/lib/paraglide` then `npm run check`
