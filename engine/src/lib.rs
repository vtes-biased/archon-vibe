use json::JsonValue;

// Modules
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

// WASM bindings (frontend)
#[cfg(feature = "wasm")]
mod wasm {
    use super::*;
    use wasm_bindgen::prelude::*;

    #[wasm_bindgen]
    pub struct WasmEngine {
        engine: Engine,
    }

    #[wasm_bindgen]
    impl WasmEngine {
        #[wasm_bindgen(constructor)]
        pub fn new() -> Self {
            WasmEngine {
                engine: Engine::new(),
            }
        }

        #[wasm_bindgen(js_name = processEvent)]
        pub fn process_event(&self, event_json: &str, objects_json: &str) -> Result<String, String> {
            let event_value = json::parse(event_json).map_err(|e| e.to_string())?;
            let event = BusinessEvent::from_json(&event_value)?;

            let objects_value = json::parse(objects_json).map_err(|e| e.to_string())?;
            let objects: Result<Vec<BaseObject>, String> = objects_value
                .members()
                .map(BaseObject::from_json)
                .collect();
            let objects = objects?;

            let crud_events = self.engine.process_event(event, &objects)?;
            let result =
                JsonValue::Array(crud_events.iter().map(|e| e.to_json()).collect());
            Ok(result.dump())
        }

        #[wasm_bindgen(js_name = validateObject)]
        pub fn validate_object(&self, object_json: &str) -> Result<(), String> {
            let value = json::parse(object_json).map_err(|e| e.to_string())?;
            let object = BaseObject::from_json(&value)?;
            self.engine.validate_object(&object)
        }

        /// Check if actor can change a role on target user.
        /// Returns JSON: { allowed: bool, reason: string | null }
        #[wasm_bindgen(js_name = canChangeRole)]
        pub fn can_change_role(
            &self,
            actor_json: &str,
            target_json: &str,
            role: &str,
        ) -> Result<String, String> {
            let actor_value = json::parse(actor_json).map_err(|e| e.to_string())?;
            let target_value = json::parse(target_json).map_err(|e| e.to_string())?;

            let actor = UserContext::from_json(&actor_value)?;
            let target = UserContext::from_json(&target_value)?;
            let role =
                Role::from_str(role).ok_or_else(|| format!("Unknown role: {}", role))?;

            let result = super::can_change_role(&actor, &target, role);
            Ok(result.to_json().dump())
        }

        /// Check if actor can manage VEKN IDs for target user.
        /// Returns JSON: { allowed: bool, reason: string | null }
        #[wasm_bindgen(js_name = canManageVekn)]
        pub fn can_manage_vekn(
            &self,
            actor_json: &str,
            target_json: &str,
        ) -> Result<String, String> {
            let actor_value = json::parse(actor_json).map_err(|e| e.to_string())?;
            let target_value = json::parse(target_json).map_err(|e| e.to_string())?;

            let actor = UserContext::from_json(&actor_value)?;
            let target = UserContext::from_json(&target_value)?;

            let result = super::can_manage_vekn(&actor, &target);
            Ok(result.to_json().dump())
        }

        /// Check if actor can edit target user's profile.
        /// Returns JSON: { allowed: bool, reason: string | null }
        #[wasm_bindgen(js_name = canEditUser)]
        pub fn can_edit_user(
            &self,
            actor_json: &str,
            actor_uid: &str,
            target_uid: &str,
            target_json: &str,
        ) -> Result<String, String> {
            let actor_value = json::parse(actor_json).map_err(|e| e.to_string())?;
            let target_value = json::parse(target_json).map_err(|e| e.to_string())?;

            let actor = UserContext::from_json(&actor_value)?;
            let target = UserContext::from_json(&target_value)?;

            let result = super::can_edit_user(&actor, actor_uid, target_uid, &target);
            Ok(result.to_json().dump())
        }

        /// Compute optimal seating for a tournament.
        /// Input JSON: { "players": [...], "rounds": N, "previous_rounds": [[...], ...] | null }
        /// Output JSON: { "rounds": [...], "score": {...} }
        #[wasm_bindgen(js_name = computeSeating)]
        pub fn compute_seating(&self, config_json: &str) -> Result<String, String> {
            let config = json::parse(config_json).map_err(|e| e.to_string())?;

            let players: Vec<String> = config["players"]
                .members()
                .filter_map(|p| p.as_str().map(|s| s.to_string()))
                .collect();

            let rounds_count = config["rounds"].as_usize().unwrap_or(3);

            let previous_rounds: Option<Vec<Vec<Vec<String>>>> =
                if config["previous_rounds"].is_null() {
                    None
                } else {
                    Some(
                        config["previous_rounds"]
                            .members()
                            .map(|r| {
                                r.members()
                                    .map(|t| {
                                        t.members()
                                            .filter_map(|p| p.as_str().map(|s| s.to_string()))
                                            .collect()
                                    })
                                    .collect()
                            })
                            .collect(),
                    )
                };

            let (rounds, score) =
                seating::compute_seating(&players, rounds_count, previous_rounds.as_deref())?;

            let rounds_json: Vec<JsonValue> = rounds
                .iter()
                .map(|r| {
                    JsonValue::Array(
                        r.iter()
                            .map(|t| {
                                JsonValue::Array(t.iter().map(|p| p.as_str().into()).collect())
                            })
                            .collect(),
                    )
                })
                .collect();

            let result = json::object! {
                rounds: rounds_json,
                score: score.to_json(),
            };
            Ok(result.dump())
        }

        /// Score an existing seating arrangement.
        /// Input JSON: { "rounds": [[[uid, ...], ...], ...] }
        /// Output JSON: { "rules": [...], "mean_vps": ..., "mean_transfers": ... }
        #[wasm_bindgen(js_name = scoreSeating)]
        pub fn score_seating(&self, config_json: &str) -> Result<String, String> {
            let config = json::parse(config_json).map_err(|e| e.to_string())?;

            let rounds: Vec<Vec<Vec<String>>> = config["rounds"]
                .members()
                .map(|r| {
                    r.members()
                        .map(|t| {
                            t.members()
                                .filter_map(|p| p.as_str().map(|s| s.to_string()))
                                .collect()
                        })
                        .collect()
                })
                .collect();

            let score = seating::score_rounds(&rounds)?;
            let minimums = seating::compute_minimum_violations(&rounds);
            let mut result = score.to_json();
            result["minimums"] = JsonValue::Array(
                minimums.iter().map(|&x| x.into()).collect()
            );
            Ok(result.dump())
        }

        /// Process a tournament event.
        /// Input: tournament JSON, event JSON, actor JSON
        /// Output: updated tournament JSON
        #[wasm_bindgen(js_name = processTournamentEvent)]
        pub fn process_tournament_event(
            &self,
            tournament_json: &str,
            event_json: &str,
            actor_json: &str,
        ) -> Result<String, String> {
            tournament::process_tournament_event(tournament_json, event_json, actor_json)
        }

        /// Compute rating points for a single tournament entry.
        #[wasm_bindgen(js_name = computeRatingPoints)]
        pub fn compute_rating_points(
            &self,
            vp: f64,
            gw: i32,
            finalist_position: i32,
            player_count: i32,
            rank: &str,
        ) -> i32 {
            ratings::compute_rating_points(vp, gw, finalist_position, player_count, rank)
        }

        /// Map format + online to rating category string.
        #[wasm_bindgen(js_name = ratingCategory)]
        pub fn rating_category(&self, format: &str, online: bool) -> String {
            ratings::rating_category(format, online).to_string()
        }
    }
}

// Python bindings (backend)
#[cfg(feature = "python")]
mod python {
    use super::*;
    use pyo3::prelude::*;

    #[pyclass]
    pub struct PyEngine {
        engine: Engine,
    }

    #[pymethods]
    impl PyEngine {
        #[new]
        fn new() -> Self {
            PyEngine {
                engine: Engine::new(),
            }
        }

        fn process_event(&self, event_json: &str, objects_json: &str) -> PyResult<String> {
            let event_value = json::parse(event_json)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
            let event = BusinessEvent::from_json(&event_value)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;

            let objects_value = json::parse(objects_json)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
            let objects: Result<Vec<BaseObject>, String> = objects_value
                .members()
                .map(BaseObject::from_json)
                .collect();
            let objects =
                objects.map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;

            let crud_events = self
                .engine
                .process_event(event, &objects)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;
            let result =
                JsonValue::Array(crud_events.iter().map(|e| e.to_json()).collect());
            Ok(result.dump())
        }

        fn validate_object(&self, object_json: &str) -> PyResult<()> {
            let value = json::parse(object_json)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
            let object = BaseObject::from_json(&value)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;
            self.engine
                .validate_object(&object)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))
        }

        /// Check if actor can change a role on target user.
        /// Returns JSON: { allowed: bool, reason: string | null }
        fn can_change_role(
            &self,
            actor_json: &str,
            target_json: &str,
            role: &str,
        ) -> PyResult<String> {
            let actor_value = json::parse(actor_json)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
            let target_value = json::parse(target_json)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;

            let actor = UserContext::from_json(&actor_value)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;
            let target = UserContext::from_json(&target_value)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;
            let role = Role::from_str(role).ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err(format!("Unknown role: {}", role))
            })?;

            let result = super::can_change_role(&actor, &target, role);
            Ok(result.to_json().dump())
        }

        /// Check if actor can manage VEKN IDs for target user.
        /// Returns JSON: { allowed: bool, reason: string | null }
        fn can_manage_vekn(&self, actor_json: &str, target_json: &str) -> PyResult<String> {
            let actor_value = json::parse(actor_json)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
            let target_value = json::parse(target_json)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;

            let actor = UserContext::from_json(&actor_value)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;
            let target = UserContext::from_json(&target_value)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;

            let result = super::can_manage_vekn(&actor, &target);
            Ok(result.to_json().dump())
        }

        /// Check if actor can edit target user's profile.
        /// Returns JSON: { allowed: bool, reason: string | null }
        fn can_edit_user(
            &self,
            actor_json: &str,
            actor_uid: &str,
            target_uid: &str,
            target_json: &str,
        ) -> PyResult<String> {
            let actor_value = json::parse(actor_json)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
            let target_value = json::parse(target_json)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;

            let actor = UserContext::from_json(&actor_value)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;
            let target = UserContext::from_json(&target_value)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;

            let result = super::can_edit_user(&actor, actor_uid, target_uid, &target);
            Ok(result.to_json().dump())
        }

        /// Compute optimal seating for a tournament.
        /// Input JSON: { "players": [...], "rounds": N, "previous_rounds": [[...], ...] | null }
        /// Output JSON: { "rounds": [...], "score": {...} }
        fn compute_seating(&self, config_json: &str) -> PyResult<String> {
            let config = json::parse(config_json)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;

            let players: Vec<String> = config["players"]
                .members()
                .filter_map(|p| p.as_str().map(|s| s.to_string()))
                .collect();

            let rounds_count = config["rounds"].as_usize().unwrap_or(3);

            let previous_rounds: Option<Vec<Vec<Vec<String>>>> =
                if config["previous_rounds"].is_null() {
                    None
                } else {
                    Some(
                        config["previous_rounds"]
                            .members()
                            .map(|r| {
                                r.members()
                                    .map(|t| {
                                        t.members()
                                            .filter_map(|p| p.as_str().map(|s| s.to_string()))
                                            .collect()
                            })
                                    .collect()
                            })
                            .collect(),
                    )
                };

            let (rounds, score) =
                seating::compute_seating(&players, rounds_count, previous_rounds.as_deref())
                    .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;

            let rounds_json: Vec<JsonValue> = rounds
                .iter()
                .map(|r| {
                    JsonValue::Array(
                        r.iter()
                            .map(|t| {
                                JsonValue::Array(t.iter().map(|p| p.as_str().into()).collect())
                            })
                            .collect(),
                    )
                })
                .collect();

            let result = json::object! {
                rounds: rounds_json,
                score: score.to_json(),
            };
            Ok(result.dump())
        }

        /// Score an existing seating arrangement.
        /// Input JSON: { "rounds": [[[uid, ...], ...], ...] }
        /// Output JSON: { "rules": [...], "mean_vps": ..., "mean_transfers": ... }
        fn score_seating(&self, config_json: &str) -> PyResult<String> {
            let config = json::parse(config_json)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;

            let rounds: Vec<Vec<Vec<String>>> = config["rounds"]
                .members()
                .map(|r| {
                    r.members()
                        .map(|t| {
                            t.members()
                                .filter_map(|p| p.as_str().map(|s| s.to_string()))
                                .collect()
                        })
                        .collect()
                })
                .collect();

            let score = seating::score_rounds(&rounds)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;
            let minimums = seating::compute_minimum_violations(&rounds);
            let mut result = score.to_json();
            result["minimums"] = JsonValue::Array(
                minimums.iter().map(|&x| x.into()).collect()
            );
            Ok(result.dump())
        }

        /// Process a tournament event.
        /// Input: tournament JSON, event JSON, actor JSON
        /// Output: updated tournament JSON
        fn process_tournament_event(
            &self,
            tournament_json: &str,
            event_json: &str,
            actor_json: &str,
        ) -> PyResult<String> {
            tournament::process_tournament_event(tournament_json, event_json, actor_json)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e))
        }

        /// Compute rating points for a single tournament entry.
        fn compute_rating_points(
            &self,
            vp: f64,
            gw: i32,
            finalist_position: i32,
            player_count: i32,
            rank: &str,
        ) -> i32 {
            ratings::compute_rating_points(vp, gw, finalist_position, player_count, rank)
        }

        /// Map format + online to rating category string.
        fn rating_category(&self, format: &str, online: bool) -> String {
            ratings::rating_category(format, online).to_string()
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
