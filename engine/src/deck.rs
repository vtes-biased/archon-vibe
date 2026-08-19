//! Deck parsing, validation, enrichment, and TWDA export, for Lackey, JOL, TWDA
//! and freeform deck list formats.

use crate::cards::{Card, CardKind, CardMap};
use crate::error::EngineError;
use json::JsonValue;
use std::collections::HashMap;

/// A parsed deck: mapping of card_id → count, plus metadata.
#[derive(Debug, Clone, Default)]
pub struct Deck {
    pub name: String,
    pub author: String,
    pub comments: String,
    pub cards: HashMap<u32, u32>,
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
        json::object! {
            name: self.name.as_str(),
            author: self.author.as_str(),
            comments: self.comments.as_str(),
            cards: cards
        }
    }
}

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

fn parse_card_line(line: &str, card_map: &CardMap) -> Option<(u32, u32)> {
    let trimmed = line.trim();
    if trimmed.is_empty() || is_comment_line(trimmed) || is_section_header(trimmed) {
        return None;
    }

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
    let bytes = line.as_bytes();
    let mut i = 0;

    // Skip leading markers: *, -, _, and an x/X multiplier before the count ("x2",
    // "xx2"); a bare x-name (no count) just falls through to the bare-name lookup below.
    while i < bytes.len() && matches!(bytes[i], b'*' | b'-' | b'_' | b' ' | b'x' | b'X') {
        i += 1;
    }

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

    // x/X after the count is a marker only when whitespace follows it; otherwise
    // it's the card name's first letter — "1x Xaviar" is count 1 of "Xaviar", not "aviar".
    while i < bytes.len() {
        match bytes[i] {
            b'*' | b' ' | b'\t' | b',' | b'.' | b'-' => i += 1,
            b'x' | b'X' => {
                let mut j = i;
                while j < bytes.len() && matches!(bytes[j], b'x' | b'X') {
                    j += 1;
                }
                if j < bytes.len() && matches!(bytes[j], b' ' | b'\t') {
                    i = j;
                } else {
                    break;
                }
            }
            _ => break,
        }
    }

    let name = line[i..].trim();
    if name.is_empty() {
        return None;
    }

    if let Some(card) = card_map.by_name(name) {
        return Some((card.id, count));
    }

    // Strip crypt tail (capacity, disciplines, group info after the name); the
    // trailing "Clan:Group" token (e.g. "Toreador:6") disambiguates multi-group vampires.
    let group = parse_crypt_tail_group(name);
    if let Some(card) = try_strip_crypt_tail(name, group, card_map) {
        return Some((card.id, count));
    }

    None
}

/// Group hint from a krcg-style crypt tail: the N in a trailing "Clan:N" or "gN"
/// token (e.g. "Toreador:6" → 6, "g6" → 6); None when the last token carries none.
fn parse_crypt_tail_group(line: &str) -> Option<u32> {
    let last = line.split_whitespace().next_back()?;
    let digits = last.rsplit(':').next().unwrap_or(last);
    let digits = digits.strip_prefix(['g', 'G']).unwrap_or(digits);
    digits.parse::<u32>().ok().filter(|g| (1..=99).contains(g))
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
                if let Some(card) = card_map.by_name_exact(second) {
                    return Some((card.id, count));
                }
            }
        }
        if let Ok(count) = second.parse::<u32>() {
            if count > 0 && count <= 99 {
                if let Some(card) = card_map.by_name_exact(first) {
                    return Some((card.id, count));
                }
            }
        }
    }

    let bytes = trimmed.as_bytes();
    let len = bytes.len();
    if len < 3 {
        return None;
    }

    if bytes[len - 1] == b')' {
        if let Some(paren_start) = trimmed.rfind('(') {
            let inside = trimmed[paren_start + 1..len - 1].trim();
            if let Ok(count) = inside.parse::<u32>() {
                if count > 0 && count <= 99 {
                    let name = trimmed[..paren_start].trim();
                    if let Some(card) = card_map.by_name_exact(name) {
                        return Some((card.id, count));
                    }
                }
            }
        }
    }

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
                        if let Some(card) = card_map.by_name_exact(name) {
                            return Some((card.id, count));
                        }
                    }
                }
            }
        }
    }

    None
}

/// Matches each trimmed candidate by EXACT name (a lenient prefix match would let
/// a half-trimmed stem resolve back to a longer card); prefers a known `group` over the earliest.
fn try_strip_crypt_tail<'a>(
    name: &str,
    group: Option<u32>,
    card_map: &'a CardMap,
) -> Option<&'a Card> {
    let words: Vec<&str> = name.split_whitespace().collect();
    for take in (1..words.len()).rev() {
        let candidate = words[..take].join(" ");
        // Don't override an explicit qualifier already in the name (e.g. "(ADV)").
        let match_ = match group {
            Some(g) if !candidate.ends_with(')') => card_map.by_name_in_group(&candidate, g),
            _ => card_map.by_name_exact(&candidate),
        };
        if let Some(card) = match_ {
            return Some(card);
        }
    }
    None
}

#[derive(Debug)]
pub struct ParseResult {
    pub deck: Deck,
    pub unrecognized_lines: Vec<String>,
}

/// Returns the parsed deck plus any lines that looked like card entries but
/// couldn't be matched.
pub fn parse_deck(text: &str, card_map: &CardMap) -> Result<ParseResult, EngineError> {
    let mut deck = Deck::new();
    let mut header_lines: Vec<String> = Vec::new();
    let mut unrecognized_lines: Vec<String> = Vec::new();
    let mut found_card = false;

    for line in text.lines() {
        if !found_card {
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
        } else if found_card
            && !line.trim().is_empty()
            && !is_comment_line(line.trim())
            && !is_section_header(line.trim())
        {
            unrecognized_lines.push(line.trim().to_string());
        }
    }

    if deck.cards.is_empty() {
        return Err(EngineError::DeckNoCards);
    }

    if deck.name.is_empty() && !header_lines.is_empty() {
        deck.name = header_lines.remove(0);
    }

    Ok(ParseResult {
        deck,
        unrecognized_lines,
    })
}

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

pub fn validate_deck(deck: &Deck, card_map: &CardMap, format: &str) -> Vec<ValidationError> {
    let mut errors = Vec::new();

    let mut unknown_count = 0u32;
    for (&id, &count) in &deck.cards {
        if card_map.by_id(id).is_none() {
            unknown_count += count;
        }
    }
    if unknown_count > 0 {
        errors.push(ValidationError {
            severity: Severity::Error,
            message: format!(
                "{unknown_count} card(s) not found in card database (unknown or outdated IDs)"
            ),
        });
    }

    let crypt_count = deck.crypt_count(card_map);
    let library_count = deck.library_count(card_map);

    if crypt_count < 12 {
        errors.push(ValidationError {
            severity: Severity::Error,
            message: format!("Crypt has {crypt_count} cards (minimum 12)"),
        });
    }

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

    for &id in deck.cards.keys() {
        if let Some(card) = card_map.by_id(id) {
            if !card.banned.is_empty() {
                errors.push(ValidationError {
                    severity: Severity::Error,
                    message: format!("{} is banned (since {})", card.unique_name, card.banned),
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

    // V5 format: only V5-legal cards (legality precomputed at build time from the
    // VEKN set allowlist + promo whitelist — see scripts/update_cards.py).
    if format == "V5" {
        for &id in deck.cards.keys() {
            if let Some(card) = card_map.by_id(id) {
                if !card.v5 {
                    errors.push(ValidationError {
                        severity: Severity::Warning,
                        message: format!("{} is not V5-legal", card.unique_name),
                    });
                }
            }
        }
    }

    errors
}

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

pub fn library_type_order_json() -> String {
    JsonValue::Array(
        LIBRARY_TYPE_ORDER
            .iter()
            .map(|&t| JsonValue::from(t))
            .collect(),
    )
    .dump()
}

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
            .then_with(|| a.0.unique_name.cmp(&b.0.unique_name))
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
            count, card.unique_name, card.capacity, disc, card.clan, card.group
        ));
    }

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
            .then_with(|| a.0.unique_name.cmp(&b.0.unique_name))
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
            lines.push(format!("{card_type} ({type_count})"));
        }
        lines.push(format!("{}x {}", count, card.unique_name));
    }

    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_cards_json() -> &'static str {
        r#"{
            "100001": {
                "id": 100001, "printed_name": ".44 Magnum", "unique_name": ".44 Magnum", "full_name": ".44 Magnum",
                "kind": "library", "types": ["Equipment"], "disciplines": [],
                "clan": "", "group": "", "capacity": 0, "adv": false, "v5": true,
                "banned": "", "sets": ["Jyhad"], "name_variants": ["44 Magnum"]
            },
            "100002": {
                "id": 100002, "printed_name": "419 Operation", "unique_name": "419 Operation", "full_name": "419 Operation",
                "kind": "library", "types": ["Action"], "disciplines": [],
                "clan": "", "group": "", "capacity": 0, "adv": false,
                "banned": "", "sets": ["Jyhad"], "name_variants": []
            },
            "100519": {
                "id": 100519, "printed_name": "Delaying Tactics", "unique_name": "Delaying Tactics", "full_name": "Delaying Tactics",
                "kind": "library", "types": ["Reaction"], "disciplines": [],
                "clan": "", "group": "", "capacity": 0, "adv": false,
                "banned": "", "sets": ["Jyhad"], "name_variants": ["Delaying"]
            },
            "100010": {
                "id": 100010, "printed_name": "Channel 10", "unique_name": "Channel 10", "full_name": "Channel 10",
                "kind": "library", "types": ["Master"], "disciplines": [],
                "clan": "", "group": "", "capacity": 0, "adv": false,
                "banned": "", "sets": ["Jyhad"], "name_variants": []
            },
            "200001": {
                "id": 200001, "printed_name": "Aabbt Kindred", "unique_name": "Aabbt Kindred", "full_name": "Aabbt Kindred (G2)",
                "kind": "crypt", "types": ["Vampire"], "disciplines": ["for", "pre", "ser"],
                "clan": "Ministry", "group": "2", "capacity": 4, "adv": false,
                "banned": "", "sets": ["Final Nights"], "name_variants": ["Aabbt Kindred"]
            },
            "200002": {
                "id": 200002, "printed_name": "Test Vampire", "unique_name": "Test Vampire", "full_name": "Test Vampire (G3)",
                "kind": "crypt", "types": ["Vampire"], "disciplines": ["dom"],
                "clan": "Ventrue", "group": "3", "capacity": 7, "adv": false,
                "banned": "", "sets": ["Jyhad"], "name_variants": ["Test Vampire"]
            },
            "200103": {
                "id": 200103, "printed_name": "Annabelle Triabell", "unique_name": "Annabelle Triabell (G3)", "full_name": "Annabelle Triabell (G3)",
                "kind": "crypt", "types": ["Vampire"], "disciplines": ["aus", "cel", "pre"],
                "clan": "Toreador", "group": "3", "capacity": 9, "adv": false,
                "banned": "", "sets": ["Camarilla Edition"], "name_variants": ["Annabelle Triabell"]
            },
            "201693": {
                "id": 201693, "printed_name": "Annabelle Triabell", "unique_name": "Annabelle Triabell (G6)", "full_name": "Annabelle Triabell (G6)",
                "kind": "crypt", "types": ["Vampire"], "disciplines": ["aus", "cel", "pre"],
                "clan": "Toreador", "group": "6", "capacity": 9, "adv": false,
                "banned": "", "sets": ["Fall of London"], "name_variants": []
            },
            "201477": {
                "id": 201477, "printed_name": "Xaviar", "unique_name": "Xaviar", "full_name": "Xaviar (G3)",
                "kind": "crypt", "types": ["Vampire"], "disciplines": ["ani", "for", "pot"],
                "clan": "Gangrel", "group": "3", "capacity": 10, "adv": false,
                "banned": "", "sets": ["Jyhad"], "name_variants": ["Xaviar"]
            }
        }"#
    }

    #[test]
    fn test_parse_count_first() {
        let cm = CardMap::load(test_cards_json()).unwrap();

        assert_eq!(parse_card_line("2x .44 Magnum", &cm), Some((100001, 2)));
        assert_eq!(
            parse_card_line("3 Delaying Tactics", &cm),
            Some((100519, 3))
        );
        assert_eq!(parse_card_line("1 * 419 Operation", &cm), Some((100002, 1)));
    }

    #[test]
    fn test_count_marker_keeps_x_name() {
        // The x/X count marker must not swallow the card name's leading 'x':
        // "1x Xaviar" is count 1 of Xaviar, not "aviar".
        let cm = CardMap::load(test_cards_json()).unwrap();
        assert_eq!(parse_card_line("1x Xaviar", &cm), Some((201477, 1)));
        assert_eq!(parse_card_line("2x Xaviar (G3)", &cm), Some((201477, 2)));
        assert_eq!(parse_card_line("1 Xaviar", &cm), Some((201477, 1)));
        assert_eq!(parse_card_line("2xx .44 Magnum", &cm), Some((100001, 2)));
        // leading x/X multiplier before the count ("x2", "xx2")
        assert_eq!(parse_card_line("x2 Xaviar", &cm), Some((201477, 2)));
        assert_eq!(parse_card_line("xx2 .44 Magnum", &cm), Some((100001, 2)));
    }

    #[test]
    fn test_parse_419_operation() {
        let cm = CardMap::load(test_cards_json()).unwrap();
        // "419 Operation" is not parsed as count=419: 419 is 3 digits, and the
        // parser rejects that as a count.
        assert_eq!(parse_card_line("2 419 Operation", &cm), Some((100002, 2)));
        assert_eq!(parse_card_line("419 Operation", &cm), Some((100002, 1)));
    }

    #[test]
    fn test_parse_tab_separated() {
        let cm = CardMap::load(test_cards_json()).unwrap();
        // Lackey format
        assert_eq!(parse_card_line("4\t.44 Magnum", &cm), Some((100001, 4)));
    }

    #[test]
    fn test_crypt_tail_group_disambiguates_multigroup_vampire() {
        // Modern TWDA/krcg crypt lines carry the group only in the "Clan:N" tail. Annabelle
        // exists in G3 (200103) and G6 (201693); bare name defaults to G3, so the tail must win.
        let cm = CardMap::load(test_cards_json()).unwrap();
        assert_eq!(
            parse_card_line(
                "1x Annabelle Triabell    9 AUS CEL PRE dom for   primogen   Toreador:6",
                &cm
            ),
            Some((201693, 1)),
            "Toreador:6 tail must resolve to the G6 printing"
        );
        // No tail group => unchanged default to the earliest printing (G3).
        assert_eq!(
            parse_card_line("1x Annabelle Triabell  9  aus cel pre", &cm),
            Some((200103, 1))
        );
    }

    #[test]
    fn test_countless_number_name_not_miscounted() {
        // A count-less line ending in a number must not have the number stripped
        // as a count: "Channel 10" is the card, count 1 — not 10x "Channel".
        let cm = CardMap::load(test_cards_json()).unwrap();
        assert_eq!(parse_card_line("Channel 10", &cm), Some((100010, 1)));
        // A real post-count still parses.
        assert_eq!(parse_card_line("Channel 10 x2", &cm), Some((100010, 2)));
    }

    #[test]
    fn test_parse_deck_basic() {
        let cm = CardMap::load(test_cards_json()).unwrap();
        let text = "Deck Name: Test Deck\nCreated by: Tester\n\n2x .44 Magnum\n3 419 Operation\n1 Delaying Tactics\n";
        let result = parse_deck(text, &cm).unwrap();
        assert_eq!(result.deck.name, "Test Deck");
        assert_eq!(result.deck.author, "Tester");
        assert_eq!(result.deck.cards.get(&100001), Some(&2));
        assert_eq!(result.deck.cards.get(&100002), Some(&3));
        assert_eq!(result.deck.cards.get(&100519), Some(&1));
        assert!(result.unrecognized_lines.is_empty());
    }

    #[test]
    fn test_parse_deck_unrecognized_lines() {
        let cm = CardMap::load(test_cards_json()).unwrap();
        let text = "2x .44 Magnum\n3x Nonexistent Card\n1 Delaying Tactics\n";
        let result = parse_deck(text, &cm).unwrap();
        assert_eq!(result.deck.cards.len(), 2);
        assert_eq!(result.unrecognized_lines, vec!["3x Nonexistent Card"]);
    }

    #[test]
    fn test_section_headers_skipped() {
        let cm = CardMap::load(test_cards_json()).unwrap();
        let text = "Crypt (12 cards)\n2x Aabbt Kindred\nLibrary (61 cards)\n2x .44 Magnum\n";
        let result = parse_deck(text, &cm).unwrap();
        assert_eq!(result.deck.cards.len(), 2);
        assert!(result.unrecognized_lines.is_empty());
    }

    #[test]
    fn test_validate_deck() {
        let cm = CardMap::load(test_cards_json()).unwrap();
        let mut deck = Deck::new();
        deck.cards.insert(100001, 5);
        let errors = validate_deck(&deck, &cm, "Standard");
        assert!(errors.iter().any(|e| e.message.contains("Crypt")));
        assert!(errors.iter().any(|e| e.message.contains("Library")));
    }

    #[test]
    fn test_v5_format_flags_non_v5_cards() {
        // V5 format warns on cards not flagged v5-legal (flag precomputed at build);
        // Standard never emits a V5 warning. Fixture marks 100001 v5:true, 100002 not.
        let cm = CardMap::load(test_cards_json()).unwrap();
        let mut deck = Deck::new();
        deck.cards.insert(100001, 2);
        deck.cards.insert(100002, 2);
        let v5 = validate_deck(&deck, &cm, "V5");
        let v5_msgs: Vec<&str> = v5.iter().map(|e| e.message.as_str()).collect();
        assert!(
            v5_msgs
                .iter()
                .any(|m| m.contains("419 Operation") && m.contains("V5-legal")),
            "non-v5 card warns"
        );
        assert!(
            !v5_msgs.iter().any(|m| m.contains(".44 Magnum")),
            "v5-legal card does not warn"
        );
        assert!(
            !validate_deck(&deck, &cm, "Standard")
                .iter()
                .any(|e| e.message.contains("V5-legal")),
            "Standard emits no V5 warning"
        );
    }
}
