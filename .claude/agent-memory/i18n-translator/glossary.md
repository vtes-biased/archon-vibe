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
| add (literal, "Add Player" button) | ajouter | añadir (peninsular; file also has alt "agregar") | adicionar | aggiungere |

§ it "register" for organizer-registers-someone-else keeps "iscrivere" even though it.json glosses self-registration and generic "registrato/a" (deceased/status) with "registrare" — don't conflate; the *action* of registering a player for a tournament is always iscrivere/inscrire/inscribir/inscrever, not registrare/registrarse family, across all four Romance locales.

\* it keeps English loanword (round, not "turno"; override, not translated; timer = timer).
† finals it: "Finali" (plural) for section headings, "finale" (singular) for time-config labels.
‡ judge it: giudice — never "arbitro".
¶ deck: "mazo"(es)/"mazzo"(it) exist but UI labels keep "deck".
‖ predator es: an older table cell had "Predador" (likely a pt copy) — "depredador" is the correct Spanish; verify before reuse.
†† es "seed": the visible UI label `finals_seed` is literally "Semilla #{n}" (a literal, non-official rendering) while `og_finals_toss` prose already used the correct official term "cabeza de serie" before this note was written — the two disagree within the same file (checked 2026-07-12, not fixed since out of scope for that task; `finals_seed` may be worth flagging to the team). For new prose, use "cabeza de serie" (official term, matches existing prose); don't silently "fix" `finals_seed` without being asked. fr/pt/it don't have this split (fr `finals_seed`="Tête de série #{n}" already matches; pt/it UI label is the bare loanword "Seed #{n}" but prose uses the official term, which reads as a deliberate short-label-vs-descriptive-prose split, not a bug).
** it "seating": `rounds_alter_seating`/`rounds_seating_*` (regular rounds) use "posti"/"disposizione"; the finals-specific og_finals_toss section uses "seduta" for the finals seating ritual specifically (`Seduta delle Finali`, `Modifica Seduta Finale`) — keep "seduta" for finals-seating prose, "disposizione"/"posti" for regular-round seating UI.

See also: [[glossary_conventions]] for coined phrases and ordering rules not captured in this table, [[tone_register]], [[infrastructure]].
