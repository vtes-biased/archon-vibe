//! Card database: load from JSON, lookup by ID or name.

use crate::error::EngineError;
use json::JsonValue;
use std::collections::HashMap;

#[derive(Debug, Clone)]
pub struct Card {
    pub id: u32,
    pub name: String,
    pub printed_name: String,
    pub kind: CardKind,
    pub types: Vec<String>,
    pub disciplines: Vec<String>,
    pub clan: String,
    pub group: String,
    pub capacity: u32,
    pub adv: bool,
    pub banned: String,
    pub sets: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum CardKind {
    Crypt,
    Library,
}

/// Normalize a card name for fuzzy lookup: lowercase, strip non-alphanumeric.
pub fn normalize_name(name: &str) -> String {
    name.chars()
        .filter_map(|c| {
            if c.is_alphanumeric() || c == ' ' {
                Some(c.to_ascii_lowercase())
            } else {
                None
            }
        })
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

pub struct CardMap {
    pub cards: HashMap<u32, Card>,
    /// Normalized name → card ID (exact match lookup)
    name_index: HashMap<String, u32>,
}

impl CardMap {
    /// Load cards from JSON string (output of update_cards.py).
    pub fn load(json_str: &str) -> Result<Self, EngineError> {
        let data = json::parse(json_str).map_err(|e| format!("JSON parse error: {e}"))?;
        let mut cards = HashMap::new();
        let mut name_index = HashMap::new();

        for (id_str, value) in data.entries() {
            let id: u32 = id_str
                .parse()
                .map_err(|_| format!("Invalid card ID: {id_str}"))?;
            let card = parse_card(id, value)?;

            // Collect every normalized name this card answers to.
            let mut keys = vec![
                normalize_name(&card.name),
                normalize_name(&card.printed_name),
            ];
            if let JsonValue::Array(ref variants) = value["name_variants"] {
                for v in variants {
                    if let Some(s) = v.as_str() {
                        keys.push(normalize_name(s));
                    }
                }
            }

            cards.insert(id, card);

            // Several crypt cards share an ambiguous bare name — e.g. all three
            // "Theo Bell" printings (G2 / G2 ADV / G6) index "theo bell". Their
            // adv/grouped forms also get distinct qualified keys ("theo bell g2",
            // "theo bell g2 adv", "theo bell g6"); the bare key is the only
            // collision. Resolve it deterministically by preference instead of
            // "last insert wins": non-advanced first, then lowest id (first
            // release) — so the parenthesis-less name defaults to the base card,
            // and a later reprint never silently changes how it resolves.
            for key in keys {
                if key.is_empty() {
                    continue;
                }
                match name_index.get(&key).copied() {
                    Some(existing) if existing != id => {
                        let prefer_new = match (cards.get(&existing), cards.get(&id)) {
                            (Some(old), Some(new)) => name_pref(new) < name_pref(old),
                            _ => true,
                        };
                        if prefer_new {
                            name_index.insert(key, id);
                        }
                    }
                    _ => {
                        name_index.insert(key, id);
                    }
                }
            }
        }

        Ok(CardMap { cards, name_index })
    }

    pub fn by_id(&self, id: u32) -> Option<&Card> {
        self.cards.get(&id)
    }

    /// Look up a card by name. Tries exact normalized match, then prefix match.
    pub fn by_name(&self, name: &str) -> Option<&Card> {
        let normalized = normalize_name(name);
        if normalized.is_empty() {
            return None;
        }
        // Exact match
        if let Some(&id) = self.name_index.get(&normalized) {
            return self.cards.get(&id);
        }
        // Prefix match: HashMap iteration order is nondeterministic, so pick a
        // stable winner — the shortest matching name (closest to the query),
        // then the lowest id.
        let mut best: Option<(usize, u32)> = None; // (name length, id)
        for (indexed_name, &id) in &self.name_index {
            if indexed_name.starts_with(&normalized) {
                let cand = (indexed_name.len(), id);
                if best.is_none_or(|b| cand < b) {
                    best = Some(cand);
                }
            }
        }
        best.and_then(|(_, id)| self.cards.get(&id))
    }

    pub fn len(&self) -> usize {
        self.cards.len()
    }

    pub fn is_empty(&self) -> bool {
        self.cards.is_empty()
    }
}

/// Preference key for resolving an ambiguous (shared) normalized name. Lower is
/// preferred: non-advanced before advanced, then lowest id. The lowest id is the
/// vampire's first release, which is the non-advanced, lowest-group printing — so
/// a bare, parenthesis-less name defaults to that base card.
fn name_pref(card: &Card) -> (u8, u32) {
    (card.adv as u8, card.id)
}

fn parse_card(id: u32, value: &JsonValue) -> Result<Card, EngineError> {
    let kind = match value["kind"].as_str().unwrap_or("library") {
        "crypt" => CardKind::Crypt,
        _ => CardKind::Library,
    };

    let types: Vec<String> = value["types"]
        .members()
        .filter_map(|v| v.as_str().map(String::from))
        .collect();

    let disciplines: Vec<String> = value["disciplines"]
        .members()
        .filter_map(|v| v.as_str().map(String::from))
        .collect();

    let sets: Vec<String> = value["sets"]
        .members()
        .filter_map(|v| v.as_str().map(String::from))
        .collect();

    Ok(Card {
        id,
        name: value["name"].as_str().unwrap_or("").to_string(),
        printed_name: value["printed_name"].as_str().unwrap_or("").to_string(),
        kind,
        types,
        disciplines,
        clan: value["clan"].as_str().unwrap_or("").to_string(),
        group: value["group"].as_str().unwrap_or("").to_string(),
        capacity: value["capacity"].as_u32().unwrap_or(0),
        adv: value["adv"].as_bool().unwrap_or(false),
        banned: value["banned"].as_str().unwrap_or("").to_string(),
        sets,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_json() -> &'static str {
        r#"{
            "100001": {
                "id": 100001,
                "name": ".44 Magnum",
                "printed_name": ".44 Magnum",
                "kind": "library",
                "types": ["Equipment"],
                "disciplines": [],
                "clan": "",
                "group": "",
                "capacity": 0,
                "adv": false,
                "banned": "",
                "sets": ["Jyhad"],
                "name_variants": ["44 Magnum"]
            },
            "200001": {
                "id": 200001,
                "name": "Aabbt Kindred (G2)",
                "printed_name": "Aabbt Kindred",
                "kind": "crypt",
                "types": ["Vampire"],
                "disciplines": ["for", "pre", "ser"],
                "clan": "Ministry",
                "group": "2",
                "capacity": 4,
                "adv": false,
                "banned": "",
                "sets": ["Final Nights"],
                "name_variants": ["Aabbt Kindred"]
            }
        }"#
    }

    #[test]
    fn test_load_and_lookup() {
        let cm = CardMap::load(sample_json()).unwrap();
        assert_eq!(cm.len(), 2);

        let magnum = cm.by_id(100001).unwrap();
        assert_eq!(magnum.name, ".44 Magnum");
        assert_eq!(magnum.kind, CardKind::Library);

        let aabbt = cm.by_name("Aabbt Kindred").unwrap();
        assert_eq!(aabbt.id, 200001);
        assert_eq!(aabbt.kind, CardKind::Crypt);

        // Normalized lookup
        let magnum2 = cm.by_name("44 magnum").unwrap();
        assert_eq!(magnum2.id, 100001);
    }

    #[test]
    fn test_prefix_lookup_is_deterministic() {
        // Several names share the "gov"/"abc" prefixes. HashMap iteration order is
        // nondeterministic, so the lookup must pick a stable winner: shortest
        // matching name, then lowest id.
        let json = r#"{
            "10": { "name": "Govern" },
            "20": { "name": "Governing" },
            "5":  { "name": "Abcd" },
            "9":  { "name": "Abce" }
        }"#;
        let cm = CardMap::load(json).unwrap();
        // Shortest match wins: "govern" (6) over "governing" (9).
        assert_eq!(cm.by_name("gov").unwrap().id, 10);
        // Equal length => lowest id wins: "abcd"/"abce" both len 4 => id 5.
        assert_eq!(cm.by_name("abc").unwrap().id, 5);
        // Stable across repeated calls.
        assert_eq!(cm.by_name("gov").unwrap().id, cm.by_name("gov").unwrap().id);
    }

    #[test]
    fn test_ambiguous_bare_name_prefers_nonadv_first_release() {
        // Mirrors real data: three "Theo Bell" printings all index the bare key
        // "theo bell". File order puts G6 last, so "last insert wins" would pick
        // G6; preference must instead pick the non-adv first release (lowest id,
        // = G2 here). The (ADV) and (G6) qualifiers still resolve via their unique
        // exact keys.
        let json = r#"{
            "201362": {"name":"Theo Bell (G2)","printed_name":"Theo Bell","adv":false,"group":"2","name_variants":["Theo Bell"]},
            "201363": {"name":"Theo Bell (G2 ADV)","printed_name":"Theo Bell","adv":true,"group":"2","name_variants":["Theo Bell (ADV)"]},
            "201613": {"name":"Theo Bell (G6)","printed_name":"Theo Bell","adv":false,"group":"6","name_variants":[]}
        }"#;
        let cm = CardMap::load(json).unwrap();
        assert_eq!(
            cm.by_name("Theo Bell").unwrap().id,
            201362,
            "bare name => non-adv first release (lowest id)"
        );
        assert_eq!(
            cm.by_name("Theo Bell (ADV)").unwrap().id,
            201363,
            "(ADV) => advanced card"
        );
        assert_eq!(cm.by_name("Theo Bell (G2)").unwrap().id, 201362);
        assert_eq!(cm.by_name("Theo Bell (G6)").unwrap().id, 201613);
        assert_eq!(cm.by_name("Theo Bell (G2 ADV)").unwrap().id, 201363);
    }
}
