# i18n Translator Memory

## Translation Infrastructure
- Files: `frontend/messages/{en,fr,es,pt,it}.json` — flat JSON, one key per string. No plurals/interpolation system; English copy must hand-pluralize (`{count} round(s)`).
- Key order in every locale follows `en.json` (source of truth): insert a new key immediately after the same preceding key as in en.json.
- `en.json` exceeds the 25k-token read limit — extract keys via `python3` or read with offset+limit.

## Tone & Register
- Semi-formal throughout, no slang. VTES game terms (Methuselah, Crypt, Pool, Torper…) use official Black Chantry rulebook translations — check blackchantry.com/utilities/rulebook/ before coining one; flag uncertain terms for human review.
- Organizer/management UI (offline session, force-unlock, takeover): plain administrative language, no game flavour.
- Form of address: es "usted", pt "você" (not "tu"), fr vouvoiement — formal throughout. **it uses informal "tu"** (not "Lei" — verified across it.json: "puoi", "hai", "premi", "vai al profilo", imperatives like "Attiva"/"Raduna"/"Apri"; a prior version of this memory wrongly said "Lei", corrected 2026-07-02).
- es.json has a handful of pre-existing "tú" outliers (`tournament_vekn_id_required_to_register`: "Necesitas...Pide...te"; `profile_sponsorship_banner`: "Contacta") — a word-count check (168× "su" / 131× "puede" / 34× "tiene" vs 1× "tienes") confirms usted is the dominant, intended register. Don't copy the outliers into new strings; write new es imperatives as usted (busque, pida, registre, cree...).
- Button-label verb mood convention (from `create_and_register_btn`, `add_player_deceased_confirm`, `create_dedup_create_new`, checked 2026-07-07): fr/es/pt use the **infinitive** for button labels regardless of register elsewhere ("Créer & Inscrire" / "Crear e Inscribir" / "Criar & Inscrever"); it uses **tu-imperative** ("Crea & Iscrivi", not "Creare & Iscrivere"). Running body text (not buttons) uses the normal vous/usted/você/tu-conjugated imperative in all four (e.g. `profile_sponsorship_banner` fr "Contactez", it "Chiedi").
- "check-in" is a loanword kept as-is in es/pt/it (pt "check-in realizado" = confirmed); fr uses Enregistrement/Pointer. Don't render "failed" as "denied" (camera errors) — use "failed access" phrasing.
- Referencing a named UI feature/button inline in a sentence (own app or third-party, e.g. Discord's "Add Friend"): wrap in the locale's quote convention — fr `« text »` (guillemets + non-breaking space), es/it `«text»` (guillemets, no space), pt `“text”` (curly quotes). Source `en.json` sometimes uses curly quotes too (see `notifications_ios_body`). For third-party product features (Discord, etc.), use that product's own localized UI term per language, not a literal translation — verify via web search if unsure (e.g. Discord's "Add Friend" = fr "Ajouter un ami", es "Añadir amigo", pt-BR "Adicionar amigo", it "Aggiungi amico").

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
| open rounds (house format) | Rondes libres | Rondas abiertas | Rodadas abertas | Round liberi |
| self-organized rounds | Rondes auto-organisées | Rondas auto-organizadas | Rodadas auto-organizadas | Round auto-organizzati |
| completed (player state) | Complété | Completado | Completado | Completato |
| announcement (tournament broadcast) | Annonce | Anuncio | Anúncio | Annuncio |
| proxy (non-competing player) | Proxy | Proxy | Proxy | Proxy |
| call judge (in-app button) | Appeler l'arbitre | Llamar al árbitro | Chamar árbitro | Chiama giudice |
| timer | minuteur | temporizador | cronômetro | timer* |
| feedback (section/UI) | Commentaires | Comentarios | Feedback | Feedback |
| register (organizer registers a player/member) | inscrire | inscribir | inscrever | iscrivere§ |
| register (self, reflexive) | s'inscrire | registrarse | registrar-se | registrarsi |
| email (noun) | email (no accent/hyphen) | correo electrónico (spelled out, not the loanword) | e-mail (hyphenated) | email |

§ it "register" for organizer-registers-someone-else keeps "iscrivere" even though it.json glosses self-registration and generic "registrato/a" (deceased/status) with "registrare" — don't conflate; the *action* of registering a player for a tournament is always iscrivere/inscrire/inscribir/inscrever, not registrare/registrarse family, across all four Romance locales.

\* it keeps English loanword (round, not "turno"; override, not translated; timer = timer).
† finals it: "Finali" (plural) for section headings, "finale" (singular) for time-config labels.
‡ judge it: giudice — never "arbitro".
¶ deck: "mazo"(es)/"mazzo"(it) exist but UI labels keep "deck".
‖ predator es: an older table cell had "Predador" (likely a pt copy) — "depredador" is the correct Spanish; verify before reuse.
- Clock stop has two keys: `timer_clock_stop` (imperative/button) vs `timer_policy_clock_stop` (noun/policy) — es/pt/it differ per the two cells above; fr is identical for both.
- Keep in English (all langs): VEKN, VP, GW, TP, TWDA, VDB, Archon, Discord, Markdown, IndexedDB, QR, Constructed, Limited, Standard, Grand Prix, Inner Circle (IC), NC, Prince, passkey, multideck.
- NOTE/TIP callout titles per locale: fr NOTE→NOTE, TIP→CONSEIL; es NOTE→NOTA, TIP→CONSEJO; it NOTE→NOTA, TIP→CONSIGLIO (pg_ context) / SUGGERIMENTO (first-install); pt NOTE→NOTA, TIP→DICA. AVERTISSEMENT(fr)/ADVERTENCIA(es)/ATTENZIONE(it) for warnings.
- Anchor link convention: fr/es/pt keep English slugs unchanged; it localizes slugs to match the translated heading (e.g. `#self-organized-rounds` → `#ronde-auto-organizzate`, `#seating-rules-reference` → `#riferimento-regole-di-seduta`).
- `og_force_takeover` was split in en.json: the tail (Archon Import + Leagues + Seating Rules Reference + FAQ heading) moved to new key `og_reference`. When any locale's `og_force_takeover` still contains that tail, it must be trimmed to only the Force Takeover subsection.

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
