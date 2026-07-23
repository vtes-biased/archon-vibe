---
name: glossary
description: Core VTES/UI term glossary table (en/fr/es/pt/it) verified from existing locale files, with footnotes
metadata:
  type: project
---

## VTES / UI Term Glossary (verified from existing locale files; `—` = not yet recorded, derive from en + rulebook)
| en | fr | es | pt | it |
|----|----|----|----|----|
| tournament | — | torneo | torneio | torneo |
| round | Ronde | ronda | rodada | round* |
| standings | Classement | clasificación | classificação | classifica |
| standings adjustment | ajustement de classement | ajuste de clasificación | ajuste de classificação | aggiustamento di classifica |
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
| raffle | Tirage au sort (full) / tirage (short form used in compact labels & badges, e.g. `raffle_name_default`, `raffle_results_header`) | sorteo | sorteio | estrazione |
| check-in | Enregistrement / Pointer | registro (de asistencia) / registrarse | check-in | check-in |
| player | — | jugador | jogador | giocatore |
| organizer | — | organizador | organizador | organizzatore |
| judge | arbitre (dominant, ~9×) / juge (minority, `override_title`+`pg_override_judge` only) | juez | juiz | giudice‡ |
| override, as verb/button (`override_btn`/`_title`/`_save`/`_placeholder`, and inline "Use Override" refs like `err_tournament_use_drop_out`'s pattern) | Modifier | Anular | Substituir | Sovrascrivi (tu-imperative) |
| override, as noun/concept (`pg_override_judge`, `og_override_remove`) | substitution (⚠ differs from the verb-cluster's "Modifier" — pre-existing split, not fixed, see footnote ***) | anulación (same root as verb, consistent) | substituição (same root as verb, consistent) | override (bare English loanword — noun form only, per footnote *) |
| score (a table's VP result, as a noun) | score (kept as French loanword, not "résultat") | puntuación | pontuação | punteggio |
| set (a score, verb — organizer/judge action, `err_tournament_score_set_by_organizer`) | saisir (saisi/saisis) | establecer | definir | impostare |
| locked (a score, adj — distinct sense from device-locked) | verrouillé | bloqueada/os (agree w/ puntuación fem) | bloqueada/os (agree w/ pontuação fem) | bloccato |
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
| add (literal, "Add Player" button) | ajouter | añadir (peninsular; file also has alt "agregar") | adicionar | aggiungere |
| Constructed / Limited (tournament format names) | Construit / Limité‡‡ | Constructed / Limited | Constructed / Limited | Constructed / Limited |
| rating points (VEKN rating, abbreviated RtP in prose) | points de rating | puntos de rating | pontos de classificação§§ | punti rating |
| in-person (vs. online, event modality) | en présentiel | presencial(es) | presencial(is) | in presenza |
| best N tournaments (rating calc window, e.g. "best 8") | N meilleurs tournois | mejores N torneos | melhores N torneios | migliori N tornei |
| National/Continental Championship (tournament rank value) | Championnat national / Championnat continental (lowercase adjective; generic prose mid-sentence also lowercases the noun: "le championnat national ou continental") | Campeonato Nacional / Campeonato Continental (both words capitalized, incl. generic mid-sentence use) | National Championship / Continental Championship (kept English, not translated)¶¶ | Campionato Nazionale / Campionato Continentale (both words capitalized) |
| co-organizer (noun) | co-organisateur | coorganizador (no hyphen) | co-organizador (hyphenated) | Co-organizzatore (capitalized, hyphenated — matches its own `og_co_organizers` bold button reference) |
| organizer access (noun phrase, "you have/lose organizer access") | accès organisateur (no preposition) | acceso de organizador | acesso de organizador | accesso come organizzatore |
| remove (from a role/list — organizer, player) vs delete (permanent object deletion) | retirer (role/list) vs supprimer (object, e.g. banner/deck/tournament) | eliminar (both senses share this verb in es — no split) | remover (role/list) vs excluir (object) | rimuovere/rimuovi (role/list) vs eliminare/elimina (object) |
| link (a tournament to a league) | lier | vincular | vincular | collegare |
| event (= tournament, interchangeable in league-linking UI) | événement | evento | evento | evento |
| ranked/unranked (VEKN rating-eligibility badge — NOT the `tfield_rank` tournament-category sense) | Classé / Non classé | Clasificado / No clasificado | Classificado / Não classificado | Classificato / Non classificato |
| casual (house format) | décontracté | casual | casual | casual (English loanword) |
| registration cap (soft, non-blocking venue-capacity limit — distinct from the hard round "limit") | plafond (des inscriptions) | tope (de inscripciones) | teto (de inscrições) | tetto (iscrizioni) |
| seats/spots (generic venue-capacity sense, NOT the game-table "seat" row above) | places | plazas | vagas | posti |
| league champion (badge crowning the rank-1 standings player) | Champion | Campeón | Campeão | Campione |
| season (a league's points/scoring period) | saison | temporada | temporada | stagione |
| crowned (verb, "crowned Champion") | couronné | coronado | coroado | incoronato |
| promo (card) — not official rulebook terminology, coined; fem. noun all 4 locales, "le promo" invariable plural in it | promo (une promo / des promos) | promo (una promo / las promos) | promo (uma promo / as promos) | promo (una promo / le promo, invariable) |
| stock (an organizer's personal promo-card inventory) | stock (loanword) | stock (loanword) | estoque (translated) | stock (loanword) |
| promo kind: card / pack / other (catalog taxonomy, `promo_kind_*`) | Carte / Lot / Autre | Carta / Lote / Otro | Carta / Pacote / Outro | Carta / Pacchetto / Altro |
| promo catalog "retire" (soft-deactivate, keep for historical reports) / "reactivate" | Retirer / Réactiver | Retirar / Reactivar | Retirar / Reativar | Ritira / Riattiva (tu-imperative) |
| ledger (promo movement audit log, `promo_ledger_*`) | registre | registro | registro | registro |
| movement (one ledger transaction, `promo_movement_*`) | mouvement | movimiento | movimentação (NOT "movimento" — that's the seating-move noun, different domain) | movimento |
| assignment (ledger kind: stock handed to another official/holder) | Attribution | Asignación | Atribuição | Assegnazione |
| distribution (ledger kind: copies handed to players directly) | Distribution | Distribución | Distribuição | Distribuzione |
| intake (ledger kind: print batch received from BCP into a holder's stock, `promo_ledger_kind_intake`/`promo_movement_submit_intake`) — same root as "received" below, not the assignment/distribution roots | Réception | Recepción | Recebimento | Ricezione |
| printer (BCP, the VEKN's card printer/manufacturer, `promo_ledger_source_bcp`="BCP (printer)") — coined, no prior precedent; BCP itself stays untranslated (proper noun) | imprimeur | imprenta | gráfica | tipografia |
| received (a holder's total intake-or-assignment credit, `promo_holdings_received` — renamed 2026-07-17 from `promo_holdings_assigned`; also `promo_movement_received_by_label`="Received by") — same root as "intake" above | reçue(s) / Reçu par | recibida(s) / Recibido por | recebida(s) / Recebido por | ricevuta/e / Ricevuto da |
| holdings (a holder's per-promo remaining/received counts, `promo_holdings_*`/`promo_inventory_no_holdings`) — reuses "stock" rather than coining a separate word | stock | stock | estoque | stock |
| member (generic app user in a picker/search context, `user_picker_*`) | membre | miembro | membro | membro |
| National/Continental promo-rank badge (short form, `promo_rank_national`/`_continental` — drops "Championship", distinct from the full `tfield_rank` phrase above) | National / Continental | Nacional / Continental | National / Continental (kept English, matches pt's `tfield_ranked_no_proxies_hint` precedent of not translating this exact phrase) | Nazionale / Continentale |
| catalog (the promo card gallery's own section heading, `promo_catalog_title`, distinct from "gallery" which stays untranslated as a component/key name only — no UI string uses "gallery" itself) | Catalogue | Catálogo | Catálogo | Catalogo |

§ it "register" for organizer-registers-someone-else keeps "iscrivere" even though it.json glosses self-registration and generic "registrato/a" (deceased/status) with "registrare" — don't conflate; the *action* of registering a player for a tournament is always iscrivere/inscrire/inscribir/inscrever, not registrare/registrarse family, across all four Romance locales.

\* it keeps English loanword (round, not "turno"; override, not translated; timer = timer).
† finals it: "Finali" (plural) for section headings, "finale" (singular) for time-config labels.
‡ judge it: giudice — never "arbitro".
¶ deck: "mazo"(es)/"mazzo"(it) exist but UI labels keep "deck".
‖ predator es: an older table cell had "Predador" (likely a pt copy) — "depredador" is the correct Spanish; verify before reuse.
†† es "seed": the visible UI label `finals_seed` is literally "Semilla #{n}" (a literal, non-official rendering) while `og_finals_toss` prose already used the correct official term "cabeza de serie" before this note was written — the two disagree within the same file (checked 2026-07-12, not fixed since out of scope for that task; `finals_seed` may be worth flagging to the team). For new prose, use "cabeza de serie" (official term, matches existing prose); don't silently "fix" `finals_seed` without being asked. fr/pt/it don't have this split (fr `finals_seed`="Tête de série #{n}" already matches; pt/it UI label is the bare loanword "Seed #{n}" but prose uses the official term, which reads as a deliberate short-label-vs-descriptive-prose split, not a bug).
** it "seating": `rounds_alter_seating`/`rounds_seating_*` (regular rounds) use "posti"/"disposizione"; the finals-specific og_finals_toss section uses "seduta" for the finals seating ritual specifically (`Seduta delle Finali`, `Modifica Seduta Finale`) — keep "seduta" for finals-seating prose, "disposizione"/"posti" for regular-round seating UI.
‡‡ **Correction to the old "keep Constructed/Limited in English in all langs" rule in [[glossary_conventions]]**: that blanket claim is wrong for fr — fr.json actually translates them (`rankings_cat_constructed`="Construit", `rankings_cat_limited`="Limité", `..._online`="Construit/Limité en ligne", also used in the `pg_standings` help-guide format list). es/pt/it do keep the bare English loanwords "Constructed"/"Limited" (confirmed both in tab labels and in `pg_standings` prose). Always check the locale file's own tab labels for these two terms — don't assume file-wide "keep in English" applies to fr.
§§ pt breaks from fr/es/it here: fr/es/it all keep "rating" as an English loanword for the *rating points* concept (fr "points de rating", es "puntos de rating", it "punti rating", all confirmed via `pg_standings`'s "Rating e Classifiche"/"Ratings y clasificaciones"/"Rating e Classifiche" section, RtP abbreviation kept literally in all four). pt instead translates it to "classificação" ("pontos de classificação (RtP)", confirmed same section, "Classificações e Rankings" heading) even though pt.json elsewhere keeps bare "Rating" as a column header (`tournament_col_rating`="Rating", `user_detail_ratings`="Ratings"). Don't use "pontos de rating" for pt — it's wrong; use "pontos de classificação". Checked 2026-07-13.
¶¶ **Trap**: the actual `<select>` for tournament rank (`TournamentFields.svelte`) renders `<option value="National Championship">National Championship</option>` as **literal hardcoded English text for every locale** — it's the raw `TournamentRank` enum value (`src/lib/types.ts`), not passed through any `m.*()` message function. So the real UI dropdown always shows English regardless of interface language. The fr/es/it translations above come from `og_intro` help-guide prose (which *glosses* the English UI term, it doesn't relabel it) and were reused for the `tfield_ranked_no_proxies_hint`/`err_tournament_rank_forbids_*`/`err_tournament_vekn_frozen_field` cluster added 2026-07-13. Don't assume a translated rank term implies a translated dropdown — check `TournamentFields.svelte` before relabeling the actual `<option>` values.
*** **fr "override" verb/noun split** (found 2026-07-13, not fixed — out of scope for the task that found it): the `override_*` button cluster (same RoundsTab.svelte judge panel) uses the verb "Modifier", but the separate `pg_override_judge`/`og_override_remove` help-guide strings use the noun "substitution" for the identical concept. es/pt don't have this problem (their noun forms are the same root as the verb: anular→anulación, substituir→substituição). Worth a follow-up ticket; when writing new fr copy *inside the override button/panel cluster* use "Modifier", when writing new fr copy *in help-guide prose describing the feature* the existing precedent is "substitution" — don't silently unify them.
**"VP" vs "PV" gap** (found 2026-07-13): fr/es/pt/it overwhelmingly keep the bare abbreviation "VP" (9+ occurrences: `rounds_r3`, `user_detail_col_vp`, `league_standings_score(_opt)`, `err_tournament_invalid_score`, `og_faq_q/a_wrong_vp`, `og_scoring_details`, `score_legend_summary`) — matches the [[glossary_conventions]] "keep in English" list. But `proxy_hint` is a lone outlier that translates it to "PV" (Points de Victoire — the actual official Black Chantry abbreviation) in all four locales. This is a pre-existing inconsistency, not fixed (out of scope). For any new VP-related string, follow the dominant "VP" convention unless told to reconcile the gap.
**"disputed" false-friend trap**: don't translate "disputed" (as in "a disputed table result") using the disputer/disputar family in fr/es/pt/it — that verb is already established elsewhere in the file to mean "to play [a round]" (`og_open_rounds`/`og_faq_a_open_rounds`: fr "chaque joueur dispute...Rondes", es/pt/it "cada jugador/jogador/giocatore disputa..."). Using "disputée"/"disputada"/"disputada"/"disputato" for "a disputed table" would misleadingly read as "a table that was played". Used instead: fr "contestée", es "en disputa" (idiomatic prepositional phrase, not the participle), pt "em disputa", it "contestato" — coined 2026-07-13 for `override_usage_hint`.

See also: [[glossary_conventions]] for coined phrases and ordering rules not captured in this table, [[tone_register]], [[infrastructure]].
