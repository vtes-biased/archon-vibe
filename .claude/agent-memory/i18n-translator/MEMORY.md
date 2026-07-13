# i18n Translator Memory

## Translation Infrastructure
- Files: `frontend/messages/{en,fr,es,pt,it}.json` — flat JSON, one key per string. No plurals/interpolation system; English copy must hand-pluralize (`{count} round(s)`).
- Key order in every locale follows `en.json` (source of truth): insert a new key immediately after the same preceding key as in en.json.
- `en.json` exceeds the 25k-token read limit — extract keys via `python3` or read with offset+limit.

## Tone & Register
- Semi-formal throughout, no slang. VTES game terms (Methuselah, Crypt, Pool, Torper…) use official Black Chantry rulebook translations — check blackchantry.com/utilities/rulebook/ before coining one; flag uncertain terms for human review.
- Organizer/management UI (offline session, force-unlock, takeover): plain administrative language, no game flavour.
- Form of address: es "usted", pt "você" (not "tu"), fr vouvoiement — formal throughout. **it is mixed, not uniform**: player-facing action UI uses informal "tu" ("puoi", "hai", "premi", "vai al profilo", imperatives like "Attiva"/"Raduna"/"Apri"), but the offline/organizer-administrative block (`offline_go_offline_msg`, `offline_go_offline_title`, `offline_locked_banner`) uses formal **Lei** ("Gestisca" not "Gestisci", "torna" 3rd-person) — checked 2026-07-12 via `tournament_new_offline_notice`. When writing new organizer-facing offline/admin strings in it, match the Lei register of that block; for player-facing action strings, match the tu register. If unsure which block a new key belongs to, check sibling keys in the same `offline_*`/`og_*` prefix rather than assuming one register for the whole file.
- es.json is **usted by default file-wide**, but has whole local sections that are consistently tú instead — not stray outliers. Confirmed 2026-07-13: the `profile_*`/`community_*` block (`profile_share`, `profile_official_contact_visibility`, `community_set_country_prompt`, `profile_sponsorship_banner`, `profile_find_coordinator`) is tú throughout ("Tu información...", "Establece tu país..."), and the `tournament_vekn_id_required_to_register`/`add_player_*`/`vekn_sponsor_to_register_*` block is also tú throughout. Before writing new es copy, check the **immediate sibling keys** (same prefix/section), not a file-wide word count — a global "usted is dominant" count can still be wrong for the specific section you're editing. Same rule applies to fr (vous vs formal) and pt (você) — always confirm against local siblings first.
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
| seating | Placement | asientos | assentos | disposizione / seduta (finals-specific)** |
| seat (position) | Siège (unit) / Placement (concept) | asiento | assento | posto |
| open seat | Placement libre | asiento libre | assento livre | posto libero |
| move here | Déplacer ici | mover aquí | mover aqui | sposta qui |
| seed (noun, ranking) | Tête de série | cabeza de serie†† | cabeça de chave | testa di serie |
| name card (finals seating ritual) | carte nominative | tarjeta (con su nombre) | cartão (com seu nome) | cartellino (con il nome) |
| row / gap (finals seating ritual) | rangée / espace | fila / hueco | fileira / espaço | fila / spazio |
| lowest qualifier (finals seating start order) | tête de série la plus basse | cabeza de serie más baja | cabeça de chave mais baixa | testa di serie più bassa |
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
| device-locked (adj., offline lock state) | verrouillé (sur cet appareil) | bloqueado (en este dispositivo) | bloqueado (neste dispositivo) | bloccato (su questo dispositivo) |
| upon reconnection (idiom, impersonal — avoids direct address) | lors de la reconnexion | al reconectar | quando reconectar | alla riconnessione |
| official (VEKN role, generic) | officiel | oficial | oficial | ufficiale |
| registration/check-in desk (physical, at a venue) | bureau des inscriptions | mostrador de inscripciones | balcão de inscrições | banco iscrizioni |

§ it "register" for organizer-registers-someone-else keeps "iscrivere" even though it.json glosses self-registration and generic "registrato/a" (deceased/status) with "registrare" — don't conflate; the *action* of registering a player for a tournament is always iscrivere/inscrire/inscribir/inscrever, not registrare/registrarse family, across all four Romance locales.

\* it keeps English loanword (round, not "turno"; override, not translated; timer = timer).
† finals it: "Finali" (plural) for section headings, "finale" (singular) for time-config labels.
‡ judge it: giudice — never "arbitro".
¶ deck: "mazo"(es)/"mazzo"(it) exist but UI labels keep "deck".
‖ predator es: an older table cell had "Predador" (likely a pt copy) — "depredador" is the correct Spanish; verify before reuse.
†† es "seed": the visible UI label `finals_seed` is literally "Semilla #{n}" (a literal, non-official rendering) while `og_finals_toss` prose already used the correct official term "cabeza de serie" before this note was written — the two disagree within the same file (checked 2026-07-12, not fixed since out of scope for that task; `finals_seed` may be worth flagging to the team). For new prose, use "cabeza de serie" (official term, matches existing prose); don't silently "fix" `finals_seed` without being asked. fr/pt/it don't have this split (fr `finals_seed`="Tête de série #{n}" already matches; pt/it UI label is the bare loanword "Seed #{n}" but prose uses the official term, which reads as a deliberate short-label-vs-descriptive-prose split, not a bug).
** it "seating": `rounds_alter_seating`/`rounds_seating_*` (regular rounds) use "posti"/"disposizione"; the finals-specific og_finals_toss section uses "seduta" for the finals seating ritual specifically (`Seduta delle Finali`, `Modifica Seduta Finale`) — keep "seduta" for finals-seating prose, "disposizione"/"posti" for regular-round seating UI.
- Clock stop has two keys: `timer_clock_stop` (imperative/button) vs `timer_policy_clock_stop` (noun/policy) — es/pt/it differ per the two cells above; fr is identical for both.
- "VEKN ID" word order (checked 2026-07-12 by grep frequency across each file, not a single example): fr/pt/it keep English order "VEKN ID" (dominant, e.g. `vekn_no_id` "Pas de VEKN ID"/"Sem VEKN ID"/"Nessun VEKN ID"); es reverses to "ID VEKN" (`vekn_no_id`="Sin ID VEKN"). Don't swap these per-language orders. **Refinement (2026-07-13)**: this is a *file-wide* default, but some local UI sections have their own established sub-convention that overrides it — check sibling keys in the same section before trusting the global count. Confirmed: the `tournament_vekn_id_required_to_register`/`add_player_no_vekn_id`/`vekn_sponsor_to_register_message` cluster uses fr "identifiant VEKN" (translated, not "VEKN ID") and es "ID de VEKN" (with "de", not the file's usual bare "ID VEKN") consistently across all 3 keys — while the `profile_claim_vekn_*`/`profile_abandon_vekn_*` cluster uses fr/es/pt/it "VEKN ID"/"ID VEKN" per the normal file-wide rule. it's `tournament_vekn_id_required_to_register` cluster likewise prefers "ID VEKN" (reversed) even though it's file-wide default is "VEKN ID".
- "desk" (as in "the organizer at the registration desk") must NOT be translated as table/mesa/tavolo — those words are already heavily overloaded in this codebase for the VTES *game table* (fr `table`, es/pt `mesa`, it `tavolo`, 80–107 occurrences each). Use `bureau`(fr)/`mostrador`(es)/`balcão`(pt)/`banco`(it) instead — see glossary row "registration/check-in desk". Coined 2026-07-13 for `vekn_guidance_new_member` and the `pg_login_reset` sponsor sentence; none of these words collided with existing strings at the time.
- Sponsorship guidance was reworded 2026-07-13 to stop pointing specifically at "the coordinator of your country" (fr coordinateur/es coordinador/pt coordenador/it coordinatore) and instead point at the generic "official" (VEKN official — NC, Prince, or tournament organizer are all examples) — reflects that sponsorship isn't NC-exclusive. When touching sponsor-adjacent copy (`profile_sponsorship_banner`, `community_sponsor_cta`, `pg_login_reset`, `vekn_guidance_*`), prefer "official"/officiel/oficial/ufficiale over "coordinator", unless the string is specifically and only about the National Coordinator role.
- "reported/pushed to VEKN" (the organization, not the vekn.net site) preposition, per `og_faq_q_vekn_push`: fr "sur VEKN" (or "à VEKN" for a "transmis à" verb), es "a VEKN" (no article), pt "para a VEKN" (WITH article — contraction, unlike es), it "al VEKN" (WITH article, a+il contraction). When the target is the *site* `vekn.net` instead, no article is needed in any of the four (it's a domain name): fr "transmis à vekn.net", es "reportados a vekn.net", pt "reportados para vekn.net", it "riportati a vekn.net". Don't conflate the two — "VEKN" (org) takes an article in pt/it but not es; "vekn.net" (site) never takes one.
- VEKN report "write-once" concept (results submitted once, never auto-updated after edits/reopening — only a VEKN admin can fix manually): no prior precedent existed before `finish_confirm_vekn`/`reopen_confirm_vekn_warn`/`vekn_out_of_sync_hint` (added 2026-07-12) — coined one canonical phrase per locale and reused it verbatim across all three keys for internal consistency: fr "le rapport n'est envoyé qu'une seule fois", es "el informe se envía una sola vez", pt "o relatório é enviado apenas uma vez", it "il rapporto viene inviato una sola volta". Reuse these exact phrases for any future VEKN-write-once string rather than re-coining.
- Dynamic-count sentences with a verb (e.g. "{count} player(s) will be ranked and rated") have no established precedent for verb number agreement (flat JSON, no plural system). Convention adopted 2026-07-12: keep the noun-level ambiguity marker per locale (fr `joueur(s)`, es `jugador/es`, pt `jogador/es`, it `giocatore/i`) but default the verb to **plural** form unconditionally (e.g. es "no tienen", not "no tiene/tienen") — a pragmatic compromise, not a confirmed team decision; flag if a stricter approach is ever requested.
- "Reporting/reported" verb choice differs by sense: "reporting VP scores at your table" (`pg_checkin_details` heading "Reporting Results") uses fr "Saisir"(entering)/es "Registro"/pt "Registrando"/it "Riportare"(same word, different sense) — don't reuse that heading's fr/es/pt verb for "reported to VEKN/vekn.net" (external system submission), which instead uses fr "transmis"/es "reportado"/pt "reportado"/it "riportato" (it happens to reuse the same word for both senses; fr/es/pt do not).
- "Decklist becomes public" (`finish_confirm_decks_*`, added 2026-07-12): coined by analogy with the existing "become visible to all members" pattern (`og_faq_a_decklists_mode`: fr "deviennent visibles"/es "se vuelven visibles"/pt "ficam visíveis"/it "diventano visibili") — no prior precedent for "public" specifically. Used: fr "deviennent publiques", es "se hacen públicas", pt "se tornam públicas", it "diventano pubbliche". "decklist" is feminine in all four (la/la/a/la), so agreement is `publique(s)`/`pública(s)`/`pública(s)`/`pubblica/pubbliche`.
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
5. To edit one paragraph inside a long markdown string safely (e.g. `og_finals_toss`, `og_force_takeover`): `txt.split('\n\n')` gives numbered segments (headings and paragraphs are separated by blank lines) — print them, find the target index, replace `segs[i]`, rejoin with `'\n\n'`. The segment split is stable across en/fr/es/pt/it since structure (heading/paragraph/list count) mirrors the source even when wording differs — safer than manual multi-line string matching for markdown bodies. Checked 2026-07-12 on a 4-locale `og_finals_toss` edit (15 segments each).
