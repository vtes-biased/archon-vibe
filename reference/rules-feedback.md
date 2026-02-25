# Rules Feedback: Gaps, Inconsistencies & Unclear Parts

Analysis of `vtes-rules.md` (game rules) and `tournament-rules.md` (VEKN tournament rules).

## Cross-document Contradictions

### 1. New card legality timing (major)

Tournament rules 2.1 says: "All new cards and game rules go immediately into effect for VEKN tournaments upon release date."
Tournament rules 4.3 says: "New VTES cards and rules... are allowed in Constructed tournament play beginning **30 days** after their retail release date."
These directly contradict each other. The intent seems to be: rules are immediate, cards have a 30-day Constructed wait (and are immediate in Limited), but 2.1 conflates both.

### 2. Rating formula example error (Appendix A.2.1)

The text says "in a **qualifier** with 50 players" but then adds +0.25 (the national championship bonus). Qualifiers explicitly "get no coefficient bonus." Either the example should say "national championship" or the +0.25 shouldn't be there. The arithmetic itself (2.889 - 1 + 0.25 = 2.139) is correct, but the label is wrong.

### 3. Infinite loop rule is misplaced

The infinite loop rule (tournament rules 4.9) is a fundamental game mechanic, but the game rules document never mentions it. It only exists in the tournament rules. This means casual (non-tournament) play has no official infinite loop rule.

## Game Rules Internal Issues

### 4. Placeholder text left in

Line 557: `"Political action cards can be identified through this icon <INSERT POLITICAL ACTION ICON>."` — This placeholder was never replaced.

### 5. Default bleed amount for allies is undefined

The bleed section says "all **vampires** have a bleed amount of 1" — but allies can also bleed ("Who can bleed: Any ready minion"). No default bleed amount is stated for allies generally. The imbued appendix explicitly says "Imbued have 1 strength and 1 bleed, by default" — which implies regular allies might not have a default of 1. In practice, ally cards state their own bleed, but the gap exists.

### 6. Default strength for allies is undefined

Similarly, "Vampires have a default strength of 1." No default for allies. The imbued appendix had to explicitly state "1 strength" for imbued, suggesting it isn't inherited from a general rule.

### 7. Negative bleed amounts

The rules say "the target Methuselah burns an amount of pool equal to the bleed amount." Card effects can reduce bleed. What happens if the bleed amount goes below 0? Does the target gain pool? Is it floored at 0? Not addressed.

### 8. Burn option icon — ambiguous grammar

The unlock phase advanced rules say a Methuselah "who does not control a minion who meets the requirements of this card **or is not a legal target**" may discard it. It's unclear whether "is not a legal target" refers to the Methuselah, the minion, or the card itself.

### 9. "During X, do Y" wording template scope

The rules say only one Y per X "with this card." But what if two different copies of the same card are in play? Can each trigger once? The template restricts per-card but doesn't address multiple copies explicitly.

### 10. Pronoun inconsistency

The document switches between "they/their" (modern) and "his/her" and "he or she" (older style) without consistency. E.g., line 2033: "Counters in excess of **his** capacity" while surrounding text uses "they/their."

### 11. Game end condition is never explicitly stated

The game is won by accumulating victory points, and players are ousted when pool reaches 0. But there's no explicit statement like "The game ends when only one Methuselah remains." It's only inferable from the oust/prey chain mechanics and the glossary entry for Victory Point.

### 12. Ally "as a vampire" capacity of 1 — limited scope unclear

When an ally plays a card "as a vampire," they have a capacity of 1. But the rules say this is "for use if the card requires an older vampire or a vampire of a given capacity." Other capacity-referencing effects (e.g., card effects that check capacity for non-requirement purposes) — do they also see the ally as capacity 1? The scope limitation is ambiguous.

## Tournament Rules Internal Issues

### 13. Duplicate sections: 3.2 and 3.4 (Pre-Game Procedure)

Both are titled "Pre-Game Procedure." Section 3.4 largely restates 3.2 and references it. This is confusing and likely an editing oversight.

### 14. Concession is group-only — not stated clearly enough

Section 3.5: "Players may concede a game at any time provided **all but one** of the players agree to concede." This means a single player **cannot** unilaterally concede mid-game — the entire table minus one must agree simultaneously. This is a significant constraint that could be stated more explicitly, since most card games allow individual concession.

### 15. Round end timing is ambiguous at phase boundaries

Section 3.1.1: "The game will end with the current minion action - if any -, or at the end of the current phase, if the notification didn't happen during the minion phase." What if the notification happens *between* phases? Does the current player complete their full turn? What about the discard phase — if time is called during the influence phase, does the player get their discard phase?

### 16. Finals with fewer than 5 qualifiers

The final round seating procedure (3.1.3) assumes exactly 5 finalists. What happens if one or more qualifiers drop out before the final? The rules don't address a 4-person final.

### 17. Late arrival scoring

Section 3.3.1 allows late arrivals but doesn't clarify their scoring for missed rounds. Do they have 0 GW / 0 VP / 0 TP for rounds they didn't play? This matters for final standings and qualification for the finals.

### 18. Multi-deck — no tracking mechanism

Section 3.1.5 allows multiple decks but provides no mechanism for tracking which deck was used in which round. This matters for the "Best-Performing Deck" finals method (3.1.5a), which requires knowing per-round performance by deck.

### 19. Play-to-win doesn't mention Tournament Points

Section 4.8 says play to win means maximizing GW, then VP. But TP is a scoring dimension (3.7.3) used as a tiebreaker. Should players also consider TP when VP is equal? The play-to-win rule is silent on this.

### 20. "Sufficiently randomized" is undefined

Sections 3.2 and 3.4 require decks to be "sufficiently randomized" but offer no definition or standard.

### 21. Tiebreakers stop at top 5

Section 3.1 says ties "for any of the **top five** rankings" are broken randomly. Ties for 6th place and below are left unaddressed.

### 22. 4-player table scoring disadvantage

Section 3.7.3 says the empty position gets 3rd place. This means at a 4-player table, the second-best player jumps from "2nd" to "4th" in TP terms (getting 24 TP instead of 48). This creates a significant competitive disadvantage for all players assigned to 4-player tables compared to 5-player tables. The rules acknowledge this design but don't justify it or offer compensation.

## Minor / Editorial

### 23. V5 format card pool dates go stale

Section 6.4 lists specific releases with dates, some still marked "Release date to be confirmed."

### 24. Restricted Trade deck sizes unexplained

The Restricted Trade (Michigan Draft) rules (7.4) specify exact deck sizes (50 library, 10 crypt) that differ from the general limited minimums, but don't explain why or reference the general rules.

### 25. Finalists all tie for second

Section 3.7.5: "The rest of the finalists **tie for second**, with no additional criteria considered to attempt to break that tie." This means 4 players all get "2nd place" regardless of VP differences in the final. This is a deliberate design choice but is quite unusual and could surprise organizers.
