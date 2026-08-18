//! Card database: load from JSON, lookup by ID or name.

use crate::error::EngineError;
use json::JsonValue;
use std::collections::HashMap;
use unicode_normalization::UnicodeNormalization;

/// NFD-decomposes (é → e + combining mark), drops combining marks, and maps the
/// few letters that don't decompose (ł, ø, æ, …) — small on purpose, VTES names are Latin-script.
pub fn fold_ascii(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.nfd() {
        match c {
            '\u{0300}'..='\u{036F}' => {} // combining diacritical mark — drop
            'ł' | 'Ł' => out.push('l'),
            'ø' | 'Ø' => out.push('o'),
            'đ' | 'Đ' | 'ð' | 'Ð' => out.push('d'),
            'ħ' | 'Ħ' => out.push('h'),
            'ı' => out.push('i'),
            'ŧ' | 'Ŧ' => out.push('t'),
            'æ' | 'Æ' => out.push_str("ae"),
            'œ' | 'Œ' => out.push_str("oe"),
            'þ' | 'Þ' => out.push_str("th"),
            'ß' => out.push_str("ss"),
            _ => out.push(c),
        }
    }
    out
}

#[derive(Debug, Clone)]
pub struct Card {
    pub id: u32,
    /// Bare name, for display (group/advanced are shown as separate badges).
    pub printed_name: String,
    /// Minimal disambiguator (most vampires bare; later groups/advanced suffixed);
    /// used for text decklist export.
    pub unique_name: String,
    /// Always group/advanced suffixed.
    pub full_name: String,
    pub kind: CardKind,
    pub types: Vec<String>,
    pub disciplines: Vec<String>,
    pub clan: String,
    pub group: String,
    pub capacity: u32,
    pub adv: bool,
    /// Legal in the VEKN "V5" constructed format (precomputed at build time).
    pub v5: bool,
    pub banned: String,
    pub sets: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum CardKind {
    Crypt,
    Library,
}

/// Folds accents to ASCII so an accent-free spelling matches ("Francois Villon"
/// for "François Villon"). The index and the query both pass through here, so
/// both sides fold identically.
pub fn normalize_name(name: &str) -> String {
    fold_ascii(name)
        .chars()
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

            let mut keys = vec![
                normalize_name(&card.printed_name),
                normalize_name(&card.unique_name),
                normalize_name(&card.full_name),
            ];
            if let JsonValue::Array(ref variants) = value["name_variants"] {
                for v in variants {
                    if let Some(s) = v.as_str() {
                        keys.push(normalize_name(s));
                    }
                }
            }

            cards.insert(id, card);

            // Ambiguous bare names resolve deterministically by preference — non-advanced
            // first, then lowest id — not "last insert wins", so a reprint can't change lookups.
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

    /// Exact normalized-name lookup only — no prefix fallback. Use where a lenient
    /// prefix match would misfire, e.g. a truncated "channel" resolving to "Channel 10".
    pub fn by_name_exact(&self, name: &str) -> Option<&Card> {
        let normalized = normalize_name(name);
        if normalized.is_empty() {
            return None;
        }
        self.name_index
            .get(&normalized)
            .and_then(|id| self.cards.get(id))
    }

    /// Disambiguates a multi-group vampire by an explicit group hint from the crypt
    /// tail (e.g. "6" in "Toreador:6"); falls back to an exact bare-name match.
    pub fn by_name_in_group(&self, name: &str, group: u32) -> Option<&Card> {
        let normalized = normalize_name(name);
        if normalized.is_empty() {
            return None;
        }
        let keyed = format!("{normalized} g{group}");
        if let Some(id) = self.name_index.get(&keyed) {
            return self.cards.get(id);
        }
        self.by_name_exact(name)
    }

    /// Look up a card by name. Tries exact normalized match, then prefix match.
    pub fn by_name(&self, name: &str) -> Option<&Card> {
        let normalized = normalize_name(name);
        if normalized.is_empty() {
            return None;
        }
        if let Some(&id) = self.name_index.get(&normalized) {
            return self.cards.get(&id);
        }
        // HashMap iteration order is nondeterministic, so pick a stable winner:
        // shortest matching name, then lowest id.
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

/// Lower is preferred: non-advanced before advanced, then lowest id (the
/// vampire's first release) — so a bare name defaults to the base card.
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
        printed_name: value["printed_name"].as_str().unwrap_or("").to_string(),
        unique_name: value["unique_name"].as_str().unwrap_or("").to_string(),
        full_name: value["full_name"].as_str().unwrap_or("").to_string(),
        kind,
        types,
        disciplines,
        clan: value["clan"].as_str().unwrap_or("").to_string(),
        group: value["group"].as_str().unwrap_or("").to_string(),
        capacity: value["capacity"].as_u32().unwrap_or(0),
        adv: value["adv"].as_bool().unwrap_or(false),
        v5: value["v5"].as_bool().unwrap_or(false),
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
                "printed_name": ".44 Magnum",
                "unique_name": ".44 Magnum",
                "full_name": ".44 Magnum",
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
                "printed_name": "Aabbt Kindred",
                "unique_name": "Aabbt Kindred",
                "full_name": "Aabbt Kindred (G2)",
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
        assert_eq!(magnum.printed_name, ".44 Magnum");
        assert_eq!(magnum.kind, CardKind::Library);

        let aabbt = cm.by_name("Aabbt Kindred").unwrap();
        assert_eq!(aabbt.id, 200001);
        assert_eq!(aabbt.kind, CardKind::Crypt);

        let magnum2 = cm.by_name("44 magnum").unwrap();
        assert_eq!(magnum2.id, 100001);
    }

    #[test]
    fn test_accent_folding() {
        let json = r#"{
            "200478": {"printed_name":"François Villon","unique_name":"François Villon (G2)","full_name":"François Villon (G2)","name_variants":[]},
            "201528": {"printed_name":"Bolesław Gutowski","unique_name":"Bolesław Gutowski","full_name":"Bolesław Gutowski","name_variants":[]}
        }"#;
        let cm = CardMap::load(json).unwrap();
        assert_eq!(cm.by_name("Francois Villon").unwrap().id, 200478);
        assert_eq!(cm.by_name("François Villon").unwrap().id, 200478);
        assert_eq!(cm.by_name("francois villon g2").unwrap().id, 200478);
        // ł has no NFD decomposition, so it folds only via the explicit map arm —
        // a branch the François (ç/ô) case never exercises.
        assert_eq!(cm.by_name("Boleslaw Gutowski").unwrap().id, 201528);
    }

    #[test]
    fn test_shipped_names_normalize_to_ascii() {
        // Every name's normalized key must be pure ASCII, or an accent-free query
        // silently misses it. No ids/names pinned, so this survives daily rebuilds.
        let parsed = json::parse(include_str!("../data/cards.json")).unwrap();
        for (id, card) in parsed.entries() {
            for key in ["printed_name", "unique_name", "full_name"] {
                if let Some(name) = card[key].as_str() {
                    assert!(
                        normalize_name(name).is_ascii(),
                        "{id} {key} {name:?} normalizes to non-ASCII {:?}",
                        normalize_name(name)
                    );
                }
            }
            if let JsonValue::Array(ref variants) = card["name_variants"] {
                for v in variants.iter().filter_map(|v| v.as_str()) {
                    assert!(
                        normalize_name(v).is_ascii(),
                        "{id} variant {v:?} normalizes to non-ASCII"
                    );
                }
            }
        }
    }

    #[test]
    fn test_prefix_lookup_is_deterministic() {
        // "gov"/"abc" prefixes are shared on purpose, to exercise the tie-break.
        let json = r#"{
            "10": { "unique_name": "Govern", "full_name": "Govern" },
            "20": { "unique_name": "Governing", "full_name": "Governing" },
            "5":  { "unique_name": "Abcd", "full_name": "Abcd" },
            "9":  { "unique_name": "Abce", "full_name": "Abce" }
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
        // Mirrors real data: three "Theo Bell" printings share the bare key, with
        // G6 last in file order, guarding that preference (not insertion order) wins.
        let json = r#"{
            "201362": {"printed_name":"Theo Bell","unique_name":"Theo Bell (G2)","full_name":"Theo Bell (G2)","adv":false,"group":"2","name_variants":["Theo Bell"]},
            "201363": {"printed_name":"Theo Bell","unique_name":"Theo Bell (G2 ADV)","full_name":"Theo Bell (G2 ADV)","adv":true,"group":"2","name_variants":["Theo Bell (ADV)"]},
            "201613": {"printed_name":"Theo Bell","unique_name":"Theo Bell (G6)","full_name":"Theo Bell (G6)","adv":false,"group":"6","name_variants":[]}
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
