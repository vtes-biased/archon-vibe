//! VEKN Judges Guide v2 penalty reference — the single source of truth; a
//! revision applied here propagates to the backend, frontend and Discord bot.

/// (key, English label, baseline level).
pub type SubcategoryDef = (&'static str, &'static str, &'static str);
/// (key, English label, subcategories).
pub type CategoryDef = (&'static str, &'static str, &'static [SubcategoryDef]);

pub const CATEGORIES: &[CategoryDef] = &[
    (
        "procedural_error",
        "Procedural Error",
        // Procedural Errors (v2 §2)
        &[
            (
                "missed_mandatory_effect",
                "Missed Mandatory Effect",
                "caution",
            ),
            ("card_access_error", "Card Access Error", "caution"),
            ("game_rule_violation", "Game Rule Violation", "caution"),
            (
                "failure_to_maintain_game_state",
                "Failure to Maintain Game State",
                "standings_adjustment",
            ),
        ],
    ),
    (
        "tournament_error",
        "Tournament Error",
        // Tournament Errors (v2 §3)
        &[
            ("illegal_decklist", "Illegal Decklist", "warning"),
            (
                "illegal_main_deck_legal_decklist",
                "Illegal Main Deck (Legal Decklist)",
                "standings_adjustment",
            ),
            (
                "illegal_main_deck_no_decklist",
                "Illegal Main Deck (No Decklist)",
                "standings_adjustment",
            ),
            (
                "outside_assistance",
                "Outside Assistance",
                "standings_adjustment",
            ),
            ("slow_play", "Slow Play", "caution"),
            (
                "limited_procedure_violation",
                "Limited Procedure Violation",
                "caution",
            ),
            (
                "public_info_miscommunication",
                "Public Info Miscommunication",
                "warning",
            ),
            ("obscuring_game_state", "Obscuring Game State", "caution"),
            ("marked_cards", "Marked Cards", "warning"),
            (
                "insufficient_shuffling",
                "Insufficient Shuffling",
                "warning",
            ),
        ],
    ),
    (
        "unsportsmanlike_conduct",
        "Unsportsmanlike Conduct",
        // Unsportsmanlike Conduct (v2 §4)
        &[
            ("minor", "Minor", "warning"),
            ("major", "Major", "standings_adjustment"),
            (
                "aggressive_behaviour",
                "Aggressive Behaviour",
                "disqualification",
            ),
            (
                "bribery_and_wagering",
                "Bribery and Wagering",
                "disqualification",
            ),
            (
                "theft_of_tournament_material",
                "Theft of Tournament Material",
                "disqualification",
            ),
            ("stalling", "Stalling", "disqualification"),
            ("cheating", "Cheating", "disqualification"),
            ("fraud", "Fraud", "disqualification"),
            ("collusion", "Collusion", "disqualification"),
            (
                "health_and_safety_disruption",
                "Health and Safety Disruption",
                "warning",
            ),
            ("rage_quitting", "Rage Quitting", "disqualification"),
            (
                "failure_to_play_to_win",
                "Failure to Play to Win",
                "warning",
            ),
        ],
    ),
];

/// Tournament penalty levels as (key, English label), in severity order.
/// (Suspension/probation are VEKN-body sanctions, outside tournament scope.)
pub const LEVELS: &[(&str, &str)] = &[
    ("caution", "Caution"),
    ("warning", "Warning"),
    ("standings_adjustment", "Standings Adjustment"),
    ("disqualification", "Disqualification"),
];

/// Repeat-offence ladder (v2 §1.2.1): enter at the subcategory baseline,
/// climb one rung per prior offence of the same type, clamped at DQ.
pub const ESCALATION: &[&str] = &[
    "caution",
    "caution",
    "warning",
    "warning",
    "standings_adjustment",
    "standings_adjustment",
    "disqualification",
];

/// The full reference as wire JSON: categories (each with subcategories and a
/// baseline), levels, and the escalation ladder.
pub fn sanction_reference_json() -> String {
    let mut categories = json::JsonValue::new_array();
    for (key, label, subs) in CATEGORIES {
        let mut sub_arr = json::JsonValue::new_array();
        for (skey, slabel, baseline) in *subs {
            sub_arr
                .push(json::object! { key: *skey, label: *slabel, baseline: *baseline })
                .unwrap();
        }
        categories
            .push(json::object! { key: *key, label: *label, subcategories: sub_arr })
            .unwrap();
    }
    let mut levels = json::JsonValue::new_array();
    for (key, label) in LEVELS {
        levels
            .push(json::object! { key: *key, label: *label })
            .unwrap();
    }
    let mut escalation = json::JsonValue::new_array();
    for level in ESCALATION {
        escalation.push(*level).unwrap();
    }
    json::object! { categories: categories, levels: levels, escalation: escalation }.dump()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Data sanity: unique keys, every baseline (and escalation rung) is a
    /// known level. Guards a Judges-Guide edit from introducing a typo'd key.
    #[test]
    fn test_reference_consistency() {
        let level_keys: Vec<&str> = LEVELS.iter().map(|(k, _)| *k).collect();
        let mut seen = std::collections::HashSet::new();
        for (ckey, _, subs) in CATEGORIES {
            assert!(seen.insert(*ckey), "duplicate category key {ckey}");
            for (skey, _, baseline) in *subs {
                assert!(seen.insert(*skey), "duplicate subcategory key {skey}");
                assert!(
                    level_keys.contains(baseline),
                    "unknown baseline level {baseline} for {skey}"
                );
            }
        }
        for rung in ESCALATION {
            assert!(level_keys.contains(rung), "unknown escalation level {rung}");
        }
        let parsed = json::parse(&sanction_reference_json()).unwrap();
        assert_eq!(parsed["categories"].len(), 3);
        assert_eq!(parsed["levels"].len(), 4);
    }
}
