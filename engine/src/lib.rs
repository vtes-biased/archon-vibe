use json::JsonValue;

// Modules
pub mod cards;
pub mod deck;
pub mod league;
mod permissions;
pub mod ratings;
pub mod seating;
pub mod tournament;

// Re-export permissions module items
pub use permissions::{
    can_change_role, can_edit_user, can_manage_vekn, PermissionResult, Role, UserContext,
};

// ============================================================================
// Base object structure matching the architecture
#[derive(Debug, Clone)]
pub struct BaseObject {
    pub uid: String,
    pub modified: String, // ISO 8601 timestamp
    pub data: JsonValue,
}

impl BaseObject {
    pub fn from_json(value: &JsonValue) -> Result<Self, String> {
        Ok(BaseObject {
            uid: value["uid"].as_str().ok_or("uid is required")?.to_string(),
            modified: value["modified"]
                .as_str()
                .ok_or("modified is required")?
                .to_string(),
            data: value.clone(),
        })
    }

    pub fn to_json(&self) -> JsonValue {
        self.data.clone()
    }
}

// Business event structure
#[derive(Debug, Clone)]
pub struct BusinessEvent {
    pub event_type: String,
    pub payload: JsonValue,
}

impl BusinessEvent {
    pub fn from_json(value: &JsonValue) -> Result<Self, String> {
        Ok(BusinessEvent {
            event_type: value["event_type"]
                .as_str()
                .ok_or("event_type is required")?
                .to_string(),
            payload: value["payload"].clone(),
        })
    }
}

// CRUD event structure
#[derive(Debug, Clone)]
pub enum CrudEvent {
    Create { object: BaseObject },
    Update { object: BaseObject },
    Delete { uid: String },
}

impl CrudEvent {
    pub fn to_json(&self) -> JsonValue {
        match self {
            CrudEvent::Create { object } => {
                json::object! {
                    type: "Create",
                    object: object.to_json()
                }
            }
            CrudEvent::Update { object } => {
                json::object! {
                    type: "Update",
                    object: object.to_json()
                }
            }
            CrudEvent::Delete { uid } => {
                json::object! {
                    type: "Delete",
                    uid: uid.clone()
                }
            }
        }
    }
}

// Core business logic engine
pub struct Engine {
    // State can be added here if needed
}

impl Engine {
    pub fn new() -> Self {
        Engine {}
    }

    /// Process a business event and return resulting CRUD events
    pub fn process_event(
        &self,
        event: BusinessEvent,
        _objects: &[BaseObject],
    ) -> Result<Vec<CrudEvent>, String> {
        // This is where business logic will be implemented
        // For now, just a placeholder that demonstrates the pattern
        match event.event_type.as_str() {
            _ => Err(format!("Unknown event type: {}", event.event_type)),
        }
    }

    /// Validate an object according to business rules
    pub fn validate_object(&self, object: &BaseObject) -> Result<(), String> {
        if object.uid.is_empty() {
            return Err("uid cannot be empty".to_string());
        }
        if object.modified.is_empty() {
            return Err("modified cannot be empty".to_string());
        }
        Ok(())
    }
}

impl Default for Engine {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================================================
// Shared JSON→core→JSON functions (used by both WASM and PyO3 shims).
// Appear unused when neither feature is enabled (test builds).
// ============================================================================
#[allow(dead_code)]
mod shared {
    use super::*;

    pub fn process_event_json(event_json: &str, objects_json: &str) -> Result<String, String> {
        let event_value = json::parse(event_json).map_err(|e| e.to_string())?;
        let event = BusinessEvent::from_json(&event_value)?;
        let objects_value = json::parse(objects_json).map_err(|e| e.to_string())?;
        let objects: Vec<BaseObject> = objects_value.members().map(BaseObject::from_json).collect::<Result<_, _>>()?;
        let crud_events = Engine::new().process_event(event, &objects)?;
        Ok(JsonValue::Array(crud_events.iter().map(|e| e.to_json()).collect()).dump())
    }

    pub fn validate_object_json(object_json: &str) -> Result<(), String> {
        let value = json::parse(object_json).map_err(|e| e.to_string())?;
        Engine::new().validate_object(&BaseObject::from_json(&value)?)
    }

    pub fn can_change_role_json(actor_json: &str, target_json: &str, role_str: &str) -> Result<String, String> {
        let actor = UserContext::from_json(&json::parse(actor_json).map_err(|e| e.to_string())?)?;
        let target = UserContext::from_json(&json::parse(target_json).map_err(|e| e.to_string())?)?;
        let role = Role::from_str(role_str).ok_or_else(|| format!("Unknown role: {}", role_str))?;
        Ok(can_change_role(&actor, &target, role).to_json().dump())
    }

    pub fn can_manage_vekn_json(actor_json: &str, target_json: &str) -> Result<String, String> {
        let actor = UserContext::from_json(&json::parse(actor_json).map_err(|e| e.to_string())?)?;
        let target = UserContext::from_json(&json::parse(target_json).map_err(|e| e.to_string())?)?;
        Ok(can_manage_vekn(&actor, &target).to_json().dump())
    }

    pub fn can_edit_user_json(actor_json: &str, actor_uid: &str, target_uid: &str, target_json: &str) -> Result<String, String> {
        let actor = UserContext::from_json(&json::parse(actor_json).map_err(|e| e.to_string())?)?;
        let target = UserContext::from_json(&json::parse(target_json).map_err(|e| e.to_string())?)?;
        Ok(can_edit_user(&actor, actor_uid, target_uid, &target).to_json().dump())
    }

    pub fn compute_seating_json(config_json: &str) -> Result<String, String> {
        let config = json::parse(config_json).map_err(|e| e.to_string())?;
        let players: Vec<String> = config["players"].members()
            .filter_map(|p| p.as_str().map(|s| s.to_string())).collect();
        let rounds_count = config["rounds"].as_usize().unwrap_or(3);
        let previous_rounds: Option<Vec<Vec<Vec<String>>>> = if config["previous_rounds"].is_null() {
            None
        } else {
            Some(config["previous_rounds"].members().map(|r| {
                r.members().map(|t| {
                    t.members().filter_map(|p| p.as_str().map(|s| s.to_string())).collect()
                }).collect()
            }).collect())
        };
        let (rounds, score) = seating::compute_seating(&players, rounds_count, previous_rounds.as_deref())?;
        let rounds_json: Vec<JsonValue> = rounds.iter().map(|r| {
            JsonValue::Array(r.iter().map(|t| {
                JsonValue::Array(t.iter().map(|p| p.as_str().into()).collect())
            }).collect())
        }).collect();
        Ok(json::object! { rounds: rounds_json, score: score.to_json() }.dump())
    }

    pub fn score_seating_json(config_json: &str) -> Result<String, String> {
        let config = json::parse(config_json).map_err(|e| e.to_string())?;
        let rounds: Vec<Vec<Vec<String>>> = config["rounds"].members().map(|r| {
            r.members().map(|t| {
                t.members().filter_map(|p| p.as_str().map(|s| s.to_string())).collect()
            }).collect()
        }).collect();
        let score = seating::score_rounds(&rounds)?;
        let minimums = seating::compute_minimum_violations(&rounds);
        let mut result = score.to_json();
        result["minimums"] = JsonValue::Array(minimums.iter().map(|&x| x.into()).collect());
        Ok(result.dump())
    }

    /// Parse deck JSON into a Deck struct (shared helper for validate/enrich/export).
    pub fn deck_from_json(value: &JsonValue, with_metadata: bool) -> Result<deck::Deck, String> {
        let mut d = deck::Deck::new();
        d.name = value["name"].as_str().unwrap_or("").to_string();
        if with_metadata {
            d.author = value["author"].as_str().unwrap_or("").to_string();
            d.comments = value["comments"].as_str().unwrap_or("").to_string();
        }
        for (id_str, count_val) in value["cards"].entries() {
            let id: u32 = id_str.parse().map_err(|_| format!("Invalid card ID: {id_str}"))?;
            d.cards.insert(id, count_val.as_u32().unwrap_or(0));
        }
        Ok(d)
    }

    pub fn parse_deck_json(text: &str, cards_json: &str) -> Result<String, String> {
        let card_map = cards::CardMap::load(cards_json)?;
        Ok(deck::parse_deck(text, &card_map)?.to_json().dump())
    }

    pub fn validate_deck_json(deck_json: &str, cards_json: &str, format: &str) -> Result<String, String> {
        let card_map = cards::CardMap::load(cards_json)?;
        let value = json::parse(deck_json).map_err(|e| e.to_string())?;
        let d = deck_from_json(&value, false)?;
        let errors = deck::validate_deck(&d, &card_map, format);
        Ok(JsonValue::Array(errors.iter().map(|e| e.to_json()).collect()).dump())
    }

    pub fn enrich_deck_json(deck_json: &str, cards_json: &str) -> Result<String, String> {
        let card_map = cards::CardMap::load(cards_json)?;
        let value = json::parse(deck_json).map_err(|e| e.to_string())?;
        let d = deck_from_json(&value, true)?;
        Ok(deck::enrich_deck(&d, &card_map).dump())
    }

    pub fn export_twda_json(
        deck_json: &str, cards_json: &str,
        tournament_name: &str, tournament_date: &str, tournament_place: &str,
        tournament_format: &str, tournament_url: &str,
        player_count: u32, player_name: &str,
    ) -> Result<String, String> {
        let card_map = cards::CardMap::load(cards_json)?;
        let value = json::parse(deck_json).map_err(|e| e.to_string())?;
        let d = deck_from_json(&value, true)?;
        Ok(deck::export_twda(&d, &card_map, tournament_name, tournament_date, tournament_place, tournament_format, tournament_url, player_count, player_name))
    }

    pub fn compute_league_standings_json(config_json: &str) -> Result<String, String> {
        league::compute_league_standings(config_json)
    }
}

// ============================================================================
// WASM bindings (frontend) — thin shims over shared functions
// ============================================================================
#[cfg(feature = "wasm")]
mod wasm {
    use super::shared::*;
    use wasm_bindgen::prelude::*;

    #[wasm_bindgen]
    pub struct WasmEngine;

    #[wasm_bindgen]
    impl WasmEngine {
        #[wasm_bindgen(constructor)]
        pub fn new() -> Self { WasmEngine }

        #[wasm_bindgen(js_name = processEvent)]
        pub fn process_event(&self, event_json: &str, objects_json: &str) -> Result<String, String> {
            process_event_json(event_json, objects_json)
        }

        #[wasm_bindgen(js_name = validateObject)]
        pub fn validate_object(&self, object_json: &str) -> Result<(), String> {
            validate_object_json(object_json)
        }

        #[wasm_bindgen(js_name = canChangeRole)]
        pub fn can_change_role(&self, actor_json: &str, target_json: &str, role: &str) -> Result<String, String> {
            can_change_role_json(actor_json, target_json, role)
        }

        #[wasm_bindgen(js_name = canManageVekn)]
        pub fn can_manage_vekn(&self, actor_json: &str, target_json: &str) -> Result<String, String> {
            can_manage_vekn_json(actor_json, target_json)
        }

        #[wasm_bindgen(js_name = canEditUser)]
        pub fn can_edit_user(&self, actor_json: &str, actor_uid: &str, target_uid: &str, target_json: &str) -> Result<String, String> {
            can_edit_user_json(actor_json, actor_uid, target_uid, target_json)
        }

        #[wasm_bindgen(js_name = computeSeating)]
        pub fn compute_seating(&self, config_json: &str) -> Result<String, String> {
            compute_seating_json(config_json)
        }

        #[wasm_bindgen(js_name = scoreSeating)]
        pub fn score_seating(&self, config_json: &str) -> Result<String, String> {
            score_seating_json(config_json)
        }

        #[wasm_bindgen(js_name = processTournamentEvent)]
        pub fn process_tournament_event(&self, tournament_json: &str, event_json: &str, actor_json: &str, sanctions_json: &str) -> Result<String, String> {
            super::tournament::process_tournament_event(tournament_json, event_json, actor_json, sanctions_json)
        }

        #[wasm_bindgen(js_name = computeRatingPoints)]
        pub fn compute_rating_points(&self, vp: f64, gw: i32, finalist_position: i32, player_count: i32, rank: &str) -> i32 {
            super::ratings::compute_rating_points(vp, gw, finalist_position, player_count, rank)
        }

        #[wasm_bindgen(js_name = ratingCategory)]
        pub fn rating_category(&self, format: &str, online: bool) -> String {
            super::ratings::rating_category(format, online).to_string()
        }

        #[wasm_bindgen(js_name = parseDeck)]
        pub fn parse_deck(&self, text: &str, cards_json: &str) -> Result<String, String> {
            parse_deck_json(text, cards_json)
        }

        #[wasm_bindgen(js_name = validateDeck)]
        pub fn validate_deck(&self, deck_json: &str, cards_json: &str, format: &str) -> Result<String, String> {
            validate_deck_json(deck_json, cards_json, format)
        }

        #[wasm_bindgen(js_name = enrichDeck)]
        pub fn enrich_deck(&self, deck_json: &str, cards_json: &str) -> Result<String, String> {
            enrich_deck_json(deck_json, cards_json)
        }

        #[wasm_bindgen(js_name = computeLeagueStandings)]
        pub fn compute_league_standings(&self, config_json: &str) -> Result<String, String> {
            compute_league_standings_json(config_json)
        }
    }
}

// ============================================================================
// Python bindings (backend) — thin shims over shared functions
// ============================================================================
#[cfg(feature = "python")]
mod python {
    use super::shared::*;
    use pyo3::prelude::*;

    fn py_str(r: Result<String, String>) -> PyResult<String> {
        r.map_err(|e| pyo3::exceptions::PyValueError::new_err(e))
    }

    fn py_unit(r: Result<(), String>) -> PyResult<()> {
        r.map_err(|e| pyo3::exceptions::PyValueError::new_err(e))
    }

    #[pyclass]
    pub struct PyEngine;

    #[pymethods]
    impl PyEngine {
        #[new]
        fn new() -> Self { PyEngine }

        fn process_event(&self, event_json: &str, objects_json: &str) -> PyResult<String> {
            py_str(process_event_json(event_json, objects_json))
        }

        fn validate_object(&self, object_json: &str) -> PyResult<()> {
            py_unit(validate_object_json(object_json))
        }

        fn can_change_role(&self, actor_json: &str, target_json: &str, role: &str) -> PyResult<String> {
            py_str(can_change_role_json(actor_json, target_json, role))
        }

        fn can_manage_vekn(&self, actor_json: &str, target_json: &str) -> PyResult<String> {
            py_str(can_manage_vekn_json(actor_json, target_json))
        }

        fn can_edit_user(&self, actor_json: &str, actor_uid: &str, target_uid: &str, target_json: &str) -> PyResult<String> {
            py_str(can_edit_user_json(actor_json, actor_uid, target_uid, target_json))
        }

        fn compute_seating(&self, config_json: &str) -> PyResult<String> {
            py_str(compute_seating_json(config_json))
        }

        fn score_seating(&self, config_json: &str) -> PyResult<String> {
            py_str(score_seating_json(config_json))
        }

        fn process_tournament_event(&self, tournament_json: &str, event_json: &str, actor_json: &str, sanctions_json: &str) -> PyResult<String> {
            py_str(super::tournament::process_tournament_event(tournament_json, event_json, actor_json, sanctions_json))
        }

        fn compute_rating_points(&self, vp: f64, gw: i32, finalist_position: i32, player_count: i32, rank: &str) -> i32 {
            super::ratings::compute_rating_points(vp, gw, finalist_position, player_count, rank)
        }

        fn rating_category(&self, format: &str, online: bool) -> String {
            super::ratings::rating_category(format, online).to_string()
        }

        fn parse_deck(&self, text: &str, cards_json: &str) -> PyResult<String> {
            py_str(parse_deck_json(text, cards_json))
        }

        fn validate_deck(&self, deck_json: &str, cards_json: &str, format: &str) -> PyResult<String> {
            py_str(validate_deck_json(deck_json, cards_json, format))
        }

        fn enrich_deck(&self, deck_json: &str, cards_json: &str) -> PyResult<String> {
            py_str(enrich_deck_json(deck_json, cards_json))
        }

        fn compute_league_standings(&self, config_json: &str) -> PyResult<String> {
            py_str(compute_league_standings_json(config_json))
        }

        fn export_twda(
            &self, deck_json: &str, cards_json: &str,
            tournament_name: &str, tournament_date: &str, tournament_place: &str,
            tournament_format: &str, tournament_url: &str,
            player_count: u32, player_name: &str,
        ) -> PyResult<String> {
            py_str(export_twda_json(deck_json, cards_json, tournament_name, tournament_date, tournament_place, tournament_format, tournament_url, player_count, player_name))
        }
    }

    #[pymodule]
    fn archon_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add_class::<PyEngine>()?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_validate_object() {
        let engine = Engine::new();
        let data = json::object! {
            uid: "test-uid",
            modified: "2025-11-08T12:00:00Z"
        };
        let object = BaseObject::from_json(&data).unwrap();

        assert!(engine.validate_object(&object).is_ok());

        let invalid_data = json::object! {
            uid: "",
            modified: "2025-11-08T12:00:00Z"
        };
        let invalid_object = BaseObject::from_json(&invalid_data).unwrap();
        assert!(engine.validate_object(&invalid_object).is_err());
    }
}
