//! Card database: load from JSON, lookup by ID or name.

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
    pub fn load(json_str: &str) -> Result<Self, String> {
        let data = json::parse(json_str).map_err(|e| format!("JSON parse error: {e}"))?;
        let mut cards = HashMap::new();
        let mut name_index = HashMap::new();

        for (id_str, value) in data.entries() {
            let id: u32 = id_str.parse().map_err(|_| format!("Invalid card ID: {id_str}"))?;
            let card = parse_card(id, value)?;

            // Index by normalized name
            name_index.insert(normalize_name(&card.name), id);
            name_index.insert(normalize_name(&card.printed_name), id);

            // Index name variants
            if let JsonValue::Array(ref variants) = value["name_variants"] {
                for v in variants {
                    if let Some(s) = v.as_str() {
                        name_index.insert(normalize_name(s), id);
                    }
                }
            }

            cards.insert(id, card);
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
        // Prefix match (first match wins)
        for (indexed_name, &id) in &self.name_index {
            if indexed_name.starts_with(&normalized) {
                return self.cards.get(&id);
            }
        }
        None
    }

    pub fn len(&self) -> usize {
        self.cards.len()
    }

    pub fn is_empty(&self) -> bool {
        self.cards.is_empty()
    }
}

fn parse_card(id: u32, value: &JsonValue) -> Result<Card, String> {
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
}
