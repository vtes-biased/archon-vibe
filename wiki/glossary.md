# Glossary

The vocabulary no generic tool knows. Read this before writing user-facing copy,
triaging a report, or naming anything.

## Terms

**VTES** — Vampire: The Eternal Struggle, the card game. **VEKN** — Vampire: Elder
Kindred Network, its official players' organization. **BCP** — Black Chantry
Productions, the publisher, and in the promo ledger the printer.

**Methuselah** — a player, in the game's own voice. **Predator** / **prey** — the
players to your right and left; ousting your prey is how you score. **Oust** —
reducing a Methuselah to zero pool, removing them from the game. **Withdraw** — a
player ending their own participation under the advanced rules.

**VP** (victory point), **GW** (game win), **TP** (tournament point) — the three
scoring axes ([domain](domain/tournament-rules.md#scoring)). **RtP** — rating
points. **Toss** — the random tiebreak for finals qualification.

**Crypt** / **library** — the two halves of a deck. **Group** — the numbered
generation band a vampire belongs to; a crypt uses one group or two consecutive
ones. **Advanced** — the upgraded printing of a vampire, a distinct card.

**Table** — one game of 4–5 players. **Seat** — a position at it. **Round** — one
simultaneous set of tables. **Finals** — the last round, of exactly five, seated by
ritual rather than algorithm. **Table bye** — the empty third position at a
four-player table, which still consumes a TP rank.

**Sanction** carries two unrelated senses, both used: a **penalty** (Caution,
Warning, Standings Adjustment, Disqualification, Suspension, Probation, Ban), and
**official approval** of an event. An event that loses approval is *unsanctioned*.

**SA** — Standings Adjustment, the −1 VP penalty. **DQ** — Disqualification.

**Proxy** is also two things, and the app keeps them apart: `Tournament.proxies` is
whether **proxy cards** are allowed, while a **proxy player**
(`Player.non_competing`) is a tournament official filling a vacant seat.

**IC** — Inner Circle, the app's global administrator tier. **NC** — National
Coordinator. **Prince** — a city-level organizer. **Ethics** — the Ethics
Committee. **Rulemonger**, **Judge**, **Sheriff** — judge certifications, which
are profile titles and grant no tournament power. The judges guide calls a Sheriff
a *Judgekin*, and legacy archon still stores that word.
**PTC** / **PT** — playtest coordinator and playtester. **DEV** — the OAuth
client manager role.

**TWDA** — the Tournament Winning Deck Archive. **krcg** — the community card-data
library. **archon** — both this app and the legacy spreadsheet-and-PHP system it
replaces; "legacy archon" always means the old one.

**Open rounds** — the non-VEKN house format with a per-player round cap.
**Self-organized rounds** — players seating their own pod inside one.

## Per-locale terms

Locale order everywhere is **fr · es · pt · it**. Reuse these verbatim; don't
re-coin. `—` means not yet recorded — derive from English and the rulebook.

**When a live locale file disagrees with this table, the live file wins.** Feature
names drift under renames and rewording and nobody backports the change here, so
re-verify a row against `frontend/messages/<locale>.json` before reusing it —
especially for house-format and beta-ish features.

| en | fr | es | pt | it |
|----|----|----|----|----|
| tournament | tournoi | torneo | torneio | torneo |
| round | Ronde | ronda | rodada | round¹ |
| standings | Classement | clasificación | classificação | classifica |
| standings adjustment | ajustement de classement | ajuste de clasificación | ajuste de classificação | aggiustamento di classifica |
| finals | Finale | final | final | finale² |
| seating | Placement | asientos | assentos | disposizione / seduta (finals only)³ |
| seat (position) | Siège (unit) / Placement (concept) | asiento | assento | posto |
| open seat | Placement libre | asiento libre | assento livre | posto libero |
| move here | Déplacer ici | mover aquí | mover aqui | sposta qui |
| seed (ranking) | Tête de série | cabeza de serie⁴ | cabeça de chave | testa di serie |
| name card (finals ritual) | carte nominative | tarjeta (con su nombre) | cartão (com seu nome) | cartellino (con il nome) |
| row / gap (finals ritual) | rangée / espace | fila / hueco | fileira / espaço | fila / spazio |
| lowest qualifier | tête de série la plus basse | cabeza de serie más baja | cabeça de chave mais baixa | testa di serie più bassa |
| toss | tirage | sorteo | sorteio | sorteggio |
| raffle | Tirage au sort (full) / tirage (compact labels) | sorteo | sorteio | estrazione |
| check-in | Enregistrement / Pointer⁵ | registro (de asistencia) / registrarse | check-in | check-in |
| player | joueur | jugador | jogador | giocatore |
| organizer | organisateur | organizador | organizador | organizzatore |
| co-organizer | co-organisateur | coorganizador (no hyphen) | co-organizador | Co-organizzatore |
| judge | arbitre (dominant) / juge (minority) | juez | juiz | giudice⁶ |
| override (verb / button) | Modifier | Anular | Substituir | Sovrascrivi |
| override (noun / concept) | modification | anulación | substituição | sovrascrittura |
| overridden (table status) | Modifiée | Anulado | Substituído | Sovrascritto |
| score (a table's VP result) | score | puntuación | pontuação | punteggio |
| set (a score, verb) | saisir | establecer | definir | impostare |
| locked (a score) | verrouillé | bloqueada/os | bloqueada/os | bloccato |
| sanction | sanction | sanción | sanção | sanzione |
| caution (milder level) | Avertissement⁷ | advertencia verbal | advertência verbal | avvertimento verbale |
| warning (stronger level) | Alerte⁷ | advertencia | advertência | avvertimento |
| disqualification | disqualification | descalificación | desqualificação | squalifica |
| league | ligue | liga | liga | campionato |
| offline mode | mode hors ligne | modo sin conexión | modo offline | modalità offline |
| device-locked | verrouillé (sur cet appareil) | bloqueado (en este dispositivo) | bloqueado (neste dispositivo) | bloccato (su questo dispositivo) |
| upon reconnection | lors de la reconnexion | al reconectar | quando reconectar | alla riconnessione |
| deck / decklist | Deck | mazo / lista de mazo⁸ | deck / lista de deck | deck / lista del mazzo⁸ |
| drop out | Abandonner | retirar(se) | desistir | Abbandona |
| drop player (organizer) | Retirer le joueur | Retirar jugador | Retirar jogador | Ritira giocatore |
| remove player | Retirer le joueur | eliminar jugador | remover jogador | rimuovi giocatore |
| predator / prey | Prédateur / Proie | depredador / presa | predador / presa | predatore / preda |
| game win | victoire de partie | victoria de partida | vitória de partida | game win¹ |
| crypt | Crypte | cripta | cripta | cripta |
| library | Bibliothèque | biblioteca | biblioteca | biblioteca |
| clock stop | Arrêt d'horloge | parar reloj / parada de reloj | parar relógio / parada de relógio | ferma orologio / arresto orologio |
| timer | Chronomètre | temporizador | cronômetro / temporizador (split)⁹ | timer¹ |
| clock skew | décalage | desfase | desvio | sfasamento |
| proxy (player or cards) | Proxy | Proxy | Proxy | Proxy |
| random (deck label) | Aléatoire | Aleatorio | Aleatório | Casuale |
| open rounds | Rondes ouvertes | Rondas abiertas | Rodadas Abertas | Round Aperti |
| self-organized rounds | Rondes auto-organisées | Rondas autoorganizadas (no hyphen) | Rodadas auto-organizadas | Round autogestiti |
| completed (player state) | Complété | Completado | Completado | Completato |
| announcement | Annonce | Anuncio | Anúncio | Annuncio |
| call judge | Appeler l'arbitre | Llamar al juez | Chamar juiz | Chiama il giudice |
| feedback | Commentaires | Comentarios | Feedback | Feedback |
| register (someone else) | inscrire | inscribir | inscrever | iscrivere¹⁰ |
| register (self, reflexive) | s'inscrire | registrarse | registrar-se | registrarsi |
| email | email | correo electrónico | e-mail | email |
| official (VEKN role) | officiel | oficial | oficial | ufficiale |
| registration desk | bureau des inscriptions | mostrador de inscripciones | balcão de inscrições | banco iscrizioni |
| add | ajouter | añadir | adicionar | aggiungere |
| Constructed / Limited | Construit / Limité¹¹ | Constructed / Limited | Constructed / Limited | Constructed / Limited |
| rating points | points de rating | puntos de rating | pontos de classificação¹² | punti rating |
| play record (profile tab) | Historique de jeu | Historial de juego | Histórico de partidas | Storico di gioco |
| in-person | en présentiel | presencial(es) | presencial(is) | in presenza |
| best N tournaments | N meilleurs tournois | mejores N torneos | melhores N torneios | migliori N tornei |
| National / Continental Championship | Championnat national / continental | Campeonato Nacional / Continental | National / Continental Championship (kept English) | Campionato Nazionale / Continentale |
| organizer access | accès organisateur | acceso de organizador | acesso de organizador | accesso come organizzatore |
| remove (role/list) vs delete (object) | retirer vs supprimer | eliminar (no split) | remover vs excluir | rimuovere vs eliminare |
| link (tournament to league) | lier | vincular | vincular | collegare |
| event (= tournament) | événement | evento | evento | evento |
| ranked / unranked | Classé / Non classé | Clasificado / No clasificado | Classificado / Não classificado | Classificato / Non classificato |
| casual (house format) | décontracté | casual | casual | casual |
| registration cap (soft) | plafond (des inscriptions) | tope (de inscripciones) | teto (de inscrições) | tetto (iscrizioni) |
| seats/spots (venue capacity) | places | plazas | vagas | posti |
| league champion | Champion | Campeón | Campeão | Campione |
| season | saison | temporada | temporada | stagione |
| crowned | couronné | coronado | coroado | incoronato |
| promo (card) | promo (fem.) | promo (fem.) | promo (fem.) | promo (fem., invariable pl. "le promo")¹³ |
| stock / holdings | stock | stock | estoque | stock |
| promo kind: card / pack / other | Carte / Lot / Autre | Carta / Lote / Otro | Carta / Pacote / Outro | Carta / Pacchetto / Altro |
| retire / reactivate (catalog) | Retirer / Réactiver | Retirar / Reactivar | Retirar / Reativar | Ritira / Riattiva |
| ledger | registre | registro | registro | registro |
| movement (one ledger row) | mouvement | movimiento | movimentação¹⁴ | movimento |
| assignment (ledger kind) | Attribution | Asignación | Atribuição | Assegnazione |
| distribution (ledger kind) | Distribution | Distribución | Distribuição | Distribuzione |
| intake (ledger kind) | Réception | Recepción | Recebimento | Ricezione |
| printer (BCP) | imprimeur | imprenta | gráfica | tipografia |
| received | reçue(s) / Reçu par | recibida(s) / Recibido por | recebida(s) / Recebido por | ricevuta/e / Ricevuto da |
| batch (print run) | lot | lote | lote | lotto |
| member (in a picker) | membre | miembro | membro | membro |
| account | compte | cuenta | conta | account (English loanword) |
| sign in (infinitive) | se connecter | iniciar sesión | entrar | accedi |
| catalog | Catalogue | Catálogo | Catálogo | Catalogo |
| developer portal | Portail développeur | Portal de desarrollador | Portal do desenvolvedor | Portale sviluppatore |
| Hall of Fame | Hall of Fame | Hall of Fame | Hall da Fama | Hall of Fame |

¹ Italian keeps English loanwords: *round*, *timer*, *override* (as a bare noun),
*game win*, *GP*. It never pluralizes them.
² Italian *Finali* plural for section headings, *finale* singular for time-config
labels; in a sentence "the final" is singular in all four.
³ Italian *posti*/*disposizione* for regular rounds, *seduta* for the finals
seating ritual specifically.
⁴ The Spanish UI label `finals_seed` renders a literal "Semilla #{n}" while prose
uses the correct official *cabeza de serie*. The two disagree in-file. Use *cabeza
de serie* for new prose; don't silently fix the label.
⁵ French has four real check-in words: `og_*` organizer guide uses
*pointer/pointage/pointé*; `pg_*`, the player's own action, uses
*s'enregistrer/Enregistré*; `state_checkin` is the state badge *Enregistrement*;
and enum references use the enum word. Never "En attente".
⁶ Italian *giudice*, never *arbitro*.
⁷ French sanction levels are counter-intuitive: the *milder* level (Caution) takes
the more formal-sounding word. Grep `sanction_level_caution` /
`sanction_level_warning` rather than reasoning from the English.
⁸ *mazo* (es) and *mazzo* (it) exist, but UI labels keep "deck". The
`og_deck_management` guide is the exception and uses its own doc-level word.
⁹ Portuguese has no dominant timer word: match the closest sibling in the same key
cluster.
¹⁰ The *action* of registering a player for a tournament is always
inscrire/inscribir/inscrever/iscrivere across all four — never the
registrare/registrarse family.
¹¹ French translates these; es/pt/it keep the English loanwords. Always check the
locale's own tab labels.
¹² Portuguese breaks from the others and translates "rating" here. Never "pontos
de rating" in pt.
¹³ "promo" is feminine in all four despite the -o. French's invariable "ces promos"
hides the risk — always check demonstratives and articles in es/pt/it.
¹⁴ Portuguese uses *movimentação*, not *movimento*, which is held by the
seating-move noun.

**Kept in English in every locale**: VEKN, VP, GW, TP, RtP, TWDA, VDB, Archon,
Discord, Markdown, IndexedDB, QR, Standard, Grand Prix, Inner Circle (IC), NC,
Prince, passkey, multideck, JSONL, gzip, BCP, file extensions, the four
reference-document titles, and "Tournament Winning Deck Archive (TWDA)".

**Traps**

- The tournament rank `<select>` renders **literal English** option values for
  every locale — they are raw enum values, not message keys. A translated rank term
  in prose does not imply a translated dropdown.
- "disputed" (a disputed table result) must not use the disputer/disputar family:
  that verb already means "to play a round" in these files. Use
  contestée / en disputa / em disputa / contestato.
- "VP" stays the bare abbreviation everywhere except one outlier that translates it
  to "PV". Follow the dominant "VP" for new strings.
- The Waiting state **displays as Check-in**; grep `state_checkin` before naming
  it.

Conventions, register and the per-locale rule set: [i18n](i18n.md).
