//! The community-link type table: `(type, placement, media)`.

use crate::model::arg;

/// `placement` is where an *unpinned* link lands — a `channel` in its country
/// card, `content` in the pool. `media` facets the pool, empty for a channel.
pub const LINK_TYPES: &[(&str, &str, &str)] = &[
    ("discord", "channel", ""),
    ("telegram", "channel", ""),
    ("whatsapp", "channel", ""),
    ("forum", "channel", ""),
    ("website", "content", "text"),
    ("blog", "content", "text"),
    ("youtube", "content", "video"),
    ("twitch", "content", "video"),
    ("spotify", "content", "podcast"),
    ("instagram", "content", "social"),
    ("x", "content", "social"),
    ("bluesky", "content", "social"),
    ("facebook", "content", "social"),
    ("reddit", "content", "social"),
    ("other", "content", "text"),
];

pub const MEDIA_KINDS: &[&str] = &["video", "podcast", "text", "social"];

pub fn community_link_reference_json() -> String {
    let mut types = json::JsonValue::new_array();
    for (link_type, placement, media) in LINK_TYPES {
        let media = if media.is_empty() {
            json::Null
        } else {
            json::JsonValue::from(*media)
        };
        types
            .push(json::object! { arg::TYPE => *link_type, arg::PLACEMENT => *placement, arg::MEDIA => media })
            .unwrap();
    }
    let mut kinds = json::JsonValue::new_array();
    for kind in MEDIA_KINDS {
        kinds.push(*kind).unwrap();
    }
    json::object! { arg::TYPES => types, arg::MEDIA_KINDS => kinds }.dump()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_table_consistency() {
        let mut seen = std::collections::HashSet::new();
        for (link_type, placement, media) in LINK_TYPES {
            assert!(seen.insert(*link_type), "duplicate link type {link_type}");
            if *placement == "content" {
                assert!(
                    MEDIA_KINDS.contains(media),
                    "content type {link_type} has unknown media {media}"
                );
            } else {
                assert_eq!(*placement, "channel", "{link_type} placement");
                assert!(media.is_empty(), "channel type {link_type} carries a media");
            }
        }
    }
}
