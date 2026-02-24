//! Deck parsing, validation, enrichment, and TWDA export.
//!
//! Handles Lackey, JOL, TWDA, and freeform deck list formats.

use crate::cards::{Card, CardKind, CardMap};
use json::JsonValue;
use std::collections::HashMap;

/// A parsed deck: mapping of card_id → count, plus metadata.
#[derive(Debug, Clone, Default)]
pub struct Deck {
    pub name: String,
    pub author: String,
    pub comments: String,
    pub cards: HashMap<u32, u32>,    // card_id → count
    pub attribution: Option<String>, // None = anonymous, Some(vekn_id) = attributed to member
}

impl Deck {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn crypt_count(&self, card_map: &CardMap) -> u32 {
        self.cards
            .iter()
            .filter(|(&id, _)| {
                card_map
                    .by_id(id)
                    .map(|c| c.kind == CardKind::Crypt)
                    .unwrap_or(false)
            })
            .map(|(_, &count)| count)
            .sum()
    }

    pub fn library_count(&self, card_map: &CardMap) -> u32 {
        self.cards
            .iter()
            .filter(|(&id, _)| {
                card_map
                    .by_id(id)
                    .map(|c| c.kind == CardKind::Library)
                    .unwrap_or(false)
            })
            .map(|(_, &count)| count)
            .sum()
    }

    pub fn to_json(&self) -> JsonValue {
        let mut cards = JsonValue::new_object();
        for (&id, &count) in &self.cards {
            cards[id.to_string()] = count.into();
        }
        let mut obj = json::object! {
            name: self.name.as_str(),
            author: self.author.as_str(),
            comments: self.comments.as_str(),
            cards: cards
        };
        if let Some(ref attr) = self.attribution {
            obj["attribution"] = attr.as_str().into();
        }
        obj
    }
}

// ============================================================================
// Section headers detection
// ============================================================================

const SECTION_HEADERS: &[&str] = &[
    "crypt",
    "library",
    "master",
    "action",
    "political",
    "reaction",
    "combat",
    "equipment",
    "retainer",
    "event",
    "conviction",
    "ally",
    "allies",
    "modifier",
    "vote",
    "total",
];

fn is_section_header(line: &str) -> bool {
    let lower = line.trim().to_lowercase();
    let first_word = lower.split_whitespace().next().unwrap_or("");
    // Strip leading punctuation/numbers
    let cleaned = first_word.trim_matches(|c: char| !c.is_alphabetic());
    SECTION_HEADERS
        .iter()
        .any(|h| cleaned == *h || cleaned == format!("{h}s"))
}

fn is_comment_line(line: &str) -> bool {
    let trimmed = line.trim();
    trimmed.starts_with('#')
        || trimmed.starts_with("//")
        || trimmed.starts_with("--")
        || trimmed.is_empty()
}

// ============================================================================
// Line parsing
// ============================================================================

/// Try to parse a card line. Returns (card_id, count) or None.
fn parse_card_line(line: &str, card_map: &CardMap) -> Option<(u32, u32)> {
    let trimmed = line.trim();
    if trimmed.is_empty() || is_comment_line(trimmed) || is_section_header(trimmed) {
        return None;
    }

    // Strip inline comments: everything after --, //, or #
    let clean = strip_inline_comment(trimmed);
    let clean = clean.trim();
    if clean.is_empty() {
        return None;
    }

    // Try count-first: "2x Card Name" or "2 Card Name" or "2 * Card Name"
    if let Some(result) = try_count_first(clean, card_map) {
        return Some(result);
    }

    // Try name-first: "Card Name x2" or "Card Name 2" (Lackey format: "2\tCard Name")
    if let Some(result) = try_name_first(clean, card_map) {
        return Some(result);
    }

    // Try as bare card name (count=1)
    if let Some(card) = card_map.by_name(clean) {
        return Some((card.id, 1));
    }

    None
}

fn strip_inline_comment(line: &str) -> &str {
    // Be careful with card names like "AK-47" — only strip " -- " (with spaces)
    // and " // " (with spaces), or " # "
    for marker in &[" -- ", " // ", " # "] {
        if let Some(pos) = line.find(marker) {
            return &line[..pos];
        }
    }
    line
}

/// Parse "count [marker] name" format.
fn try_count_first(line: &str, card_map: &CardMap) -> Option<(u32, u32)> {
    // Match: optional markers, 1-2 digit count, optional x/*, then card name
    let bytes = line.as_bytes();
    let mut i = 0;

    // Skip leading markers: *, -, _
    while i < bytes.len() && matches!(bytes[i], b'*' | b'-' | b'_' | b' ') {
        i += 1;
    }

    // Read count (1-2 digits)
    let count_start = i;
    while i < bytes.len() && bytes[i].is_ascii_digit() {
        i += 1;
    }
    let count_end = i;
    if count_start == count_end || (count_end - count_start) > 2 {
        return None;
    }

    // Check this isn't "2nd", "3rd" etc.
    if i < bytes.len() && matches!(bytes.get(i..i + 2), Some(b"st" | b"nd" | b"rd" | b"th")) {
        return None;
    }

    let count: u32 = line[count_start..count_end].parse().ok()?;
    if count == 0 || count > 99 {
        return None;
    }

    // Skip separator: x, X, *, spaces, tabs, commas
    while i < bytes.len()
        && matches!(
            bytes[i],
            b'x' | b'X' | b'*' | b' ' | b'\t' | b',' | b'.' | b'-'
        )
    {
        i += 1;
    }

    let name = line[i..].trim();
    if name.is_empty() {
        return None;
    }

    // Try exact lookup first
    if let Some(card) = card_map.by_name(name) {
        return Some((card.id, count));
    }

    // Strip crypt tail (capacity, disciplines, group info after the name)
    // e.g., "Aabbt Kindred   4  for pre ser  Ministry:2"
    if let Some(card) = try_strip_crypt_tail(name, card_map) {
        return Some((card.id, count));
    }

    None
}

/// Parse "name [marker] count" format.
fn try_name_first(line: &str, card_map: &CardMap) -> Option<(u32, u32)> {
    // Look for trailing count: "Card Name x2", "Card Name (2)", "Card Name  2"
    let trimmed = line.trim();

    // Try tab-separated (Lackey): "count\tname"
    if let Some(tab_pos) = trimmed.find('\t') {
        let first = trimmed[..tab_pos].trim();
        let second = trimmed[tab_pos + 1..].trim();
        // Could be "count\tname" or "name\tcount"
        if let Ok(count) = first.parse::<u32>() {
            if count > 0 && count <= 99 {
                if let Some(card) = card_map.by_name(second) {
                    return Some((card.id, count));
                }
            }
        }
        if let Ok(count) = second.parse::<u32>() {
            if count > 0 && count <= 99 {
                if let Some(card) = card_map.by_name(first) {
                    return Some((card.id, count));
                }
            }
        }
    }

    // Try trailing count patterns: "name x2", "name *2", "name (2)"
    // Work backwards from the end
    let bytes = trimmed.as_bytes();
    let len = bytes.len();
    if len < 3 {
        return None;
    }

    // Handle "(N)" suffix
    if bytes[len - 1] == b')' {
        if let Some(paren_start) = trimmed.rfind('(') {
            let inside = trimmed[paren_start + 1..len - 1].trim();
            if let Ok(count) = inside.parse::<u32>() {
                if count > 0 && count <= 99 {
                    let name = trimmed[..paren_start].trim();
                    if let Some(card) = card_map.by_name(name) {
                        return Some((card.id, count));
                    }
                }
            }
        }
    }

    // Handle trailing "xN" or "N"
    let mut end = len;
    while end > 0 && bytes[end - 1].is_ascii_digit() {
        end -= 1;
    }
    if end < len && end > 0 {
        let count_str = &trimmed[end..];
        if count_str.len() <= 2 {
            if let Ok(count) = count_str.parse::<u32>() {
                if count > 0 && count <= 99 {
                    let mut name_end = end;
                    // Skip trailing x, X, *, space
                    while name_end > 0
                        && matches!(
                            bytes[name_end - 1],
                            b'x' | b'X' | b'*' | b' ' | b'\t' | b',' | b':'
                        )
                    {
                        name_end -= 1;
                    }
                    let name = trimmed[..name_end].trim();
                    if !name.is_empty() {
                        if let Some(card) = card_map.by_name(name) {
                            return Some((card.id, count));
                        }
                    }
                }
            }
        }
    }

    None
}

/// Try to strip JOL/TWDA crypt tail info to find the card name.
fn try_strip_crypt_tail<'a>(name: &str, card_map: &'a CardMap) -> Option<&'a Card> {
    // Progressively trim from the right, trying to match after each trim
    let words: Vec<&str> = name.split_whitespace().collect();
    for take in (1..words.len()).rev() {
        let candidate = words[..take].join(" ");
        if let Some(card) = card_map.by_name(&candidate) {
            return Some(card);
        }
    }
    None
}

// ============================================================================
// Deck parsing
// ============================================================================

/// Parse a deck list text into a Deck. Auto-detects format.
pub fn parse_deck(text: &str, card_map: &CardMap) -> Result<Deck, String> {
    let mut deck = Deck::new();
    let mut header_lines: Vec<String> = Vec::new();
    let mut found_card = false;

    for line in text.lines() {
        // Collect header/metadata before first card
        if !found_card {
            // Check for name/author headers
            let lower = line.trim().to_lowercase();
            if lower.starts_with("deck name:") || lower.starts_with("name:") {
                deck.name = line
                    .trim()
                    .split_once(':')
                    .map(|x| x.1)
                    .unwrap_or("")
                    .trim()
                    .to_string();
                continue;
            }
            if lower.starts_with("created by:")
                || lower.starts_with("author:")
                || lower.starts_with("deck by:")
            {
                deck.author = line
                    .trim()
                    .split_once(':')
                    .map(|x| x.1)
                    .unwrap_or("")
                    .trim()
                    .to_string();
                continue;
            }
        }

        if let Some((card_id, count)) = parse_card_line(line, card_map) {
            found_card = true;
            *deck.cards.entry(card_id).or_insert(0) += count;
        } else if !found_card && !line.trim().is_empty() && !is_comment_line(line) {
            header_lines.push(line.trim().to_string());
        }
    }

    if deck.cards.is_empty() {
        return Err("No cards found in deck list".to_string());
    }

    // If no name was explicitly set, use first header line
    if deck.name.is_empty() && !header_lines.is_empty() {
        deck.name = header_lines.remove(0);
    }

    Ok(deck)
}

// ============================================================================
// Validation
// ============================================================================

#[derive(Debug, Clone)]
pub struct ValidationError {
    pub severity: Severity,
    pub message: String,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Severity {
    Error,
    Warning,
}

impl ValidationError {
    pub fn to_json(&self) -> JsonValue {
        json::object! {
            severity: match self.severity {
                Severity::Error => "error",
                Severity::Warning => "warning",
            },
            message: self.message.as_str()
        }
    }
}

/// Validate a deck against Standard format rules.
pub fn validate_deck(deck: &Deck, card_map: &CardMap, format: &str) -> Vec<ValidationError> {
    let mut errors = Vec::new();

    let crypt_count = deck.crypt_count(card_map);
    let library_count = deck.library_count(card_map);

    // Crypt size
    if crypt_count < 12 {
        errors.push(ValidationError {
            severity: Severity::Error,
            message: format!("Crypt has {crypt_count} cards (minimum 12)"),
        });
    }

    // Library size
    if library_count < 60 {
        errors.push(ValidationError {
            severity: Severity::Error,
            message: format!("Library has {library_count} cards (minimum 60)"),
        });
    }
    if library_count > 90 {
        errors.push(ValidationError {
            severity: Severity::Error,
            message: format!("Library has {library_count} cards (maximum 90)"),
        });
    }

    // Check for banned cards
    for &id in deck.cards.keys() {
        if let Some(card) = card_map.by_id(id) {
            if !card.banned.is_empty() {
                errors.push(ValidationError {
                    severity: Severity::Error,
                    message: format!("{} is banned (since {})", card.name, card.banned),
                });
            }
        }
    }

    // Check group rule: crypt cards must be from at most 2 consecutive groups
    let mut groups: Vec<u32> = Vec::new();
    for &id in deck.cards.keys() {
        if let Some(card) = card_map.by_id(id) {
            if card.kind == CardKind::Crypt && card.group != "any" {
                if let Ok(g) = card.group.parse::<u32>() {
                    if !groups.contains(&g) {
                        groups.push(g);
                    }
                }
            }
        }
    }
    groups.sort();
    if groups.len() > 2 {
        errors.push(ValidationError {
            severity: Severity::Error,
            message: format!("Crypt uses {} groups (maximum 2 consecutive)", groups.len()),
        });
    } else if groups.len() == 2 && groups[1] - groups[0] > 1 {
        errors.push(ValidationError {
            severity: Severity::Error,
            message: format!(
                "Crypt groups {} and {} are not consecutive",
                groups[0], groups[1]
            ),
        });
    }

    // V5 format: only V5-legal cards
    if format == "V5" {
        for &id in deck.cards.keys() {
            if let Some(card) = card_map.by_id(id) {
                // V5 cards have V5 or newer sets
                let has_v5_print = card.sets.iter().any(|s| {
                    s.starts_with("V5")
                        || s.starts_with("New Blood")
                        || s == "Shadows of Berlin"
                        || s.starts_with("Sabbat")
                        || s == "Promo"
                        || s == "Print on Demand"
                        || s == "Fall of London"
                        || s.starts_with("Echoes")
                });
                if !has_v5_print {
                    errors.push(ValidationError {
                        severity: Severity::Warning,
                        message: format!("{} may not be V5-legal", card.name),
                    });
                }
            }
        }
    }

    errors
}

// ============================================================================
// Enrichment
// ============================================================================

/// Enrich a deck with card details for display.
pub fn enrich_deck(deck: &Deck, card_map: &CardMap) -> JsonValue {
    let mut crypt = Vec::new();
    let mut library = Vec::new();

    for (&id, &count) in &deck.cards {
        if let Some(card) = card_map.by_id(id) {
            let entry = json::object! {
                id: id,
                count: count,
                name: card.name.as_str(),
                printed_name: card.printed_name.as_str(),
                types: JsonValue::Array(card.types.iter().map(|t| t.as_str().into()).collect()),
                disciplines: JsonValue::Array(card.disciplines.iter().map(|d| d.as_str().into()).collect()),
                clan: card.clan.as_str(),
                group: card.group.as_str(),
                capacity: card.capacity,
            };
            match card.kind {
                CardKind::Crypt => crypt.push(entry),
                CardKind::Library => library.push(entry),
            }
        }
    }

    // Sort crypt by capacity descending, then name
    crypt.sort_by(|a, b| {
        let cap_cmp = b["capacity"].as_u32().cmp(&a["capacity"].as_u32());
        if cap_cmp == std::cmp::Ordering::Equal {
            a["name"].as_str().cmp(&b["name"].as_str())
        } else {
            cap_cmp
        }
    });

    // Sort library by canonical TWDA type order, then name
    library.sort_by(|a, b| {
        let type_a = a["types"][0].as_str().unwrap_or("");
        let type_b = b["types"][0].as_str().unwrap_or("");
        library_type_index(type_a)
            .cmp(&library_type_index(type_b))
            .then_with(|| a["name"].as_str().cmp(&b["name"].as_str()))
    });

    let crypt_count: u32 = crypt.iter().map(|c| c["count"].as_u32().unwrap_or(0)).sum();
    let library_count: u32 = library
        .iter()
        .map(|c| c["count"].as_u32().unwrap_or(0))
        .sum();

    json::object! {
        name: deck.name.as_str(),
        author: deck.author.as_str(),
        comments: deck.comments.as_str(),
        crypt: {
            count: crypt_count,
            cards: JsonValue::Array(crypt)
        },
        library: {
            count: library_count,
            cards: JsonValue::Array(library)
        }
    }
}

// ============================================================================
// TWDA Export
// ============================================================================

/// Canonical TWDA library type ordering.
const LIBRARY_TYPE_ORDER: &[&str] = &[
    "Master",
    "Conviction",
    "Action",
    "Action/Combat",
    "Action/Reaction",
    "Ally",
    "Equipment",
    "Political Action",
    "Retainer",
    "Power",
    "Action Modifier",
    "Action Modifier/Combat",
    "Action Modifier/Reaction",
    "Reaction",
    "Combat",
    "Combat/Reaction",
    "Event",
];

fn library_type_index(t: &str) -> usize {
    LIBRARY_TYPE_ORDER
        .iter()
        .position(|&x| x == t)
        .unwrap_or(LIBRARY_TYPE_ORDER.len())
}

/// Export a deck in TWDA text format.
///
/// Parameters:
/// - `tournament_format`: e.g. "2R+F", "3R+F"
/// - `tournament_url`: URL to the tournament page (can be empty)
#[allow(clippy::too_many_arguments)]
pub fn export_twda(
    deck: &Deck,
    card_map: &CardMap,
    tournament_name: &str,
    tournament_date: &str,
    tournament_place: &str,
    tournament_format: &str,
    tournament_url: &str,
    player_count: u32,
    player_name: &str,
) -> String {
    let mut lines = Vec::new();

    // Header
    lines.push(tournament_name.to_string());
    lines.push(tournament_place.to_string());
    lines.push(tournament_date.to_string());
    if !tournament_format.is_empty() {
        lines.push(tournament_format.to_string());
    }
    lines.push(format!("{player_count} players"));
    lines.push(player_name.to_string());
    if !tournament_url.is_empty() {
        lines.push(String::new());
        lines.push(tournament_url.to_string());
    }
    lines.push(String::new());

    if !deck.name.is_empty() {
        lines.push(format!("Deck Name: {}", deck.name));
    }
    if !deck.author.is_empty() {
        lines.push(format!("Created by: {}", deck.author));
    }
    if !deck.comments.is_empty() {
        lines.push(String::new());
        lines.push(deck.comments.clone());
    }
    if !deck.name.is_empty() || !deck.author.is_empty() || !deck.comments.is_empty() {
        lines.push(String::new());
    }

    // Crypt
    let mut crypt_entries: Vec<(&Card, u32)> = deck
        .cards
        .iter()
        .filter_map(|(&id, &count)| {
            card_map
                .by_id(id)
                .filter(|c| c.kind == CardKind::Crypt)
                .map(|c| (c, count))
        })
        .collect();
    crypt_entries.sort_by(|a, b| {
        b.0.capacity
            .cmp(&a.0.capacity)
            .then_with(|| a.0.name.cmp(&b.0.name))
    });

    let crypt_total: u32 = crypt_entries.iter().map(|(_, c)| c).sum();

    lines.push(format!("Crypt ({crypt_total} cards)"));
    lines.push("-".repeat(lines.last().map(|l| l.len()).unwrap_or(0)));

    for (card, count) in &crypt_entries {
        let disc = if card.disciplines.is_empty() {
            "-none-".to_string()
        } else {
            card.disciplines.join(" ")
        };
        lines.push(format!(
            "{}x {:30} {:>2}  {:20} {}:{}",
            count, card.name, card.capacity, disc, card.clan, card.group
        ));
    }

    // Library
    let mut lib_entries: Vec<(&Card, u32)> = deck
        .cards
        .iter()
        .filter_map(|(&id, &count)| {
            card_map
                .by_id(id)
                .filter(|c| c.kind == CardKind::Library)
                .map(|c| (c, count))
        })
        .collect();
    lib_entries.sort_by(|a, b| {
        let type_a = a.0.types.first().map(|s| s.as_str()).unwrap_or("");
        let type_b = b.0.types.first().map(|s| s.as_str()).unwrap_or("");
        library_type_index(type_a)
            .cmp(&library_type_index(type_b))
            .then_with(|| a.0.name.cmp(&b.0.name))
    });

    let lib_total: u32 = lib_entries.iter().map(|(_, c)| c).sum();
    lines.push(String::new());
    lines.push(format!("Library ({lib_total} cards)"));

    let mut current_type = String::new();
    for (card, count) in &lib_entries {
        let card_type = card.types.first().map(|s| s.as_str()).unwrap_or("Other");
        if card_type != current_type {
            current_type = card_type.to_string();
            let type_count: u32 = lib_entries
                .iter()
                .filter(|(c, _)| c.types.first().map(|s| s.as_str()).unwrap_or("") == card_type)
                .map(|(_, c)| c)
                .sum();
            // TODO: Add trifle counts when card data includes trifle flag
            lines.push(format!("{card_type} ({type_count})"));
        }
        lines.push(format!("{}x {}", count, card.name));
    }

    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_cards_json() -> &'static str {
        r#"{
            "100001": {
                "id": 100001, "name": ".44 Magnum", "printed_name": ".44 Magnum",
                "kind": "library", "types": ["Equipment"], "disciplines": [],
                "clan": "", "group": "", "capacity": 0, "adv": false,
                "banned": "", "sets": ["Jyhad"], "name_variants": ["44 Magnum"]
            },
            "100002": {
                "id": 100002, "name": "419 Operation", "printed_name": "419 Operation",
                "kind": "library", "types": ["Action"], "disciplines": [],
                "clan": "", "group": "", "capacity": 0, "adv": false,
                "banned": "", "sets": ["Jyhad"], "name_variants": []
            },
            "100519": {
                "id": 100519, "name": "Delaying Tactics", "printed_name": "Delaying Tactics",
                "kind": "library", "types": ["Reaction"], "disciplines": [],
                "clan": "", "group": "", "capacity": 0, "adv": false,
                "banned": "", "sets": ["Jyhad"], "name_variants": ["Delaying"]
            },
            "200001": {
                "id": 200001, "name": "Aabbt Kindred (G2)", "printed_name": "Aabbt Kindred",
                "kind": "crypt", "types": ["Vampire"], "disciplines": ["for", "pre", "ser"],
                "clan": "Ministry", "group": "2", "capacity": 4, "adv": false,
                "banned": "", "sets": ["Final Nights"], "name_variants": ["Aabbt Kindred"]
            },
            "200002": {
                "id": 200002, "name": "Test Vampire (G3)", "printed_name": "Test Vampire",
                "kind": "crypt", "types": ["Vampire"], "disciplines": ["dom"],
                "clan": "Ventrue", "group": "3", "capacity": 7, "adv": false,
                "banned": "", "sets": ["Jyhad"], "name_variants": ["Test Vampire"]
            }
        }"#
    }

    #[test]
    fn test_parse_count_first() {
        let cm = CardMap::load(test_cards_json()).unwrap();

        // Standard: "2x .44 Magnum"
        assert_eq!(parse_card_line("2x .44 Magnum", &cm), Some((100001, 2)));
        // Without x: "3 Delaying Tactics"
        assert_eq!(
            parse_card_line("3 Delaying Tactics", &cm),
            Some((100519, 3))
        );
        // With asterisk: "1 * 419 Operation"
        assert_eq!(parse_card_line("1 * 419 Operation", &cm), Some((100002, 1)));
    }

    #[test]
    fn test_parse_419_operation() {
        let cm = CardMap::load(test_cards_json()).unwrap();
        // "419 Operation" should NOT be parsed as count=419
        // Since 419 is 3 digits, our parser rejects it as a count
        assert_eq!(parse_card_line("2 419 Operation", &cm), Some((100002, 2)));
        // Bare name
        assert_eq!(parse_card_line("419 Operation", &cm), Some((100002, 1)));
    }

    #[test]
    fn test_parse_tab_separated() {
        let cm = CardMap::load(test_cards_json()).unwrap();
        // Lackey format
        assert_eq!(parse_card_line("4\t.44 Magnum", &cm), Some((100001, 4)));
    }

    #[test]
    fn test_parse_deck_basic() {
        let cm = CardMap::load(test_cards_json()).unwrap();
        let text = "Deck Name: Test Deck\nCreated by: Tester\n\n2x .44 Magnum\n3 419 Operation\n1 Delaying Tactics\n";
        let deck = parse_deck(text, &cm).unwrap();
        assert_eq!(deck.name, "Test Deck");
        assert_eq!(deck.author, "Tester");
        assert_eq!(deck.cards.get(&100001), Some(&2));
        assert_eq!(deck.cards.get(&100002), Some(&3));
        assert_eq!(deck.cards.get(&100519), Some(&1));
    }

    #[test]
    fn test_section_headers_skipped() {
        let cm = CardMap::load(test_cards_json()).unwrap();
        let text = "Crypt (12 cards)\n2x Aabbt Kindred\nLibrary (61 cards)\n2x .44 Magnum\n";
        let deck = parse_deck(text, &cm).unwrap();
        assert_eq!(deck.cards.len(), 2);
    }

    #[test]
    fn test_validate_deck() {
        let cm = CardMap::load(test_cards_json()).unwrap();
        let mut deck = Deck::new();
        deck.cards.insert(100001, 5);
        let errors = validate_deck(&deck, &cm, "Standard");
        // Should have errors for insufficient crypt and library
        assert!(errors.iter().any(|e| e.message.contains("Crypt")));
        assert!(errors.iter().any(|e| e.message.contains("Library")));
    }
}
