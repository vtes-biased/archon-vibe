use crate::model::{arg, tournament};
use json::JsonValue;

fn str_list_has(list: &JsonValue, value: &str) -> bool {
    list.members().any(|v| v.as_str() == Some(value))
}

/// `viewer`: `{uid, country, continent_countries, hidden, added}`; `event`: the
/// tournament's list fields plus `playing`, whether the viewer is registered in it.
pub fn matches_agenda(viewer: &JsonValue, event: &JsonValue, include_online: bool) -> bool {
    let uid = viewer[arg::UID].as_str().unwrap_or("");
    if str_list_has(&event[tournament::ORGANIZERS_UIDS], uid) {
        return true;
    }
    if event[arg::PLAYING].as_bool().unwrap_or(false) {
        return true;
    }
    if event[tournament::STATE].as_str() == Some("Finished") {
        return false;
    }
    if event[tournament::ONLINE].as_bool().unwrap_or(false) {
        return include_online;
    }
    let Some(country) = event[tournament::COUNTRY].as_str() else {
        return false;
    };
    if viewer[arg::COUNTRY].as_str() == Some(country) {
        return true;
    }
    matches!(
        event[tournament::RANK].as_str(),
        Some("National Championship" | "Continental Championship")
    ) && str_list_has(&viewer[arg::CONTINENT_COUNTRIES], country)
}

pub fn on_agenda(viewer: &JsonValue, event: &JsonValue, include_online: bool) -> bool {
    let uid = event[tournament::UID].as_str().unwrap_or("");
    if str_list_has(&viewer[arg::HIDDEN], uid) {
        return false;
    }
    if str_list_has(&viewer[arg::ADDED], uid) {
        return true;
    }
    matches_agenda(viewer, event, include_online)
}

pub fn toggle_entry(viewer: &JsonValue, event: &JsonValue) -> Option<&'static str> {
    let matched = matches_agenda(viewer, event, true);
    match (on_agenda(viewer, event, true), matched) {
        (true, true) => Some("hidden"),
        (false, false) => Some("added"),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn viewer() -> JsonValue {
        json::object! {
            uid: "me", country: "FR", continent_countries: ["FR", "DE"],
            hidden: [], added: [],
        }
    }

    #[test]
    fn online_filter_gates_an_online_event_in_the_viewers_own_country() {
        let event = json::object! { uid: "t", state: "Planned", online: true, country: "FR" };
        assert!(!matches_agenda(&viewer(), &event, false));
        assert!(matches_agenda(&viewer(), &event, true));
    }

    #[test]
    fn hidden_beats_an_own_event_and_added_survives_finish_and_the_online_filter() {
        let own = json::object! { uid: "own", state: "Planned", organizers_uids: ["me"] };
        let far = json::object! { uid: "far", state: "Finished", online: true };
        let mut v = viewer();
        v[arg::HIDDEN] = json::array!["own"];
        v[arg::ADDED] = json::array!["far"];
        assert!(!on_agenda(&v, &own, true));
        assert!(on_agenda(&v, &far, false));
        assert_eq!(toggle_entry(&v, &own), None);
        assert_eq!(toggle_entry(&v, &far), None);
        assert_eq!(toggle_entry(&viewer(), &own), Some("hidden"));
        assert_eq!(toggle_entry(&viewer(), &far), Some("added"));
    }
}
