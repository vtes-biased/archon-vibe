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
// Shared JSON→core→JSON functions (used by both WASM and PyO3 shims).
// Appear unused when neither feature is enabled (test builds).
// ============================================================================
#[allow(dead_code)]
mod shared {
    use super::*;

    pub fn can_change_role_json(
        actor_json: &str,
        target_json: &str,
        role_str: &str,
    ) -> Result<String, String> {
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

    pub fn can_edit_user_json(
        actor_json: &str,
        actor_uid: &str,
        target_uid: &str,
        target_json: &str,
    ) -> Result<String, String> {
        let actor = UserContext::from_json(&json::parse(actor_json).map_err(|e| e.to_string())?)?;
        let target = UserContext::from_json(&json::parse(target_json).map_err(|e| e.to_string())?)?;
        Ok(can_edit_user(&actor, actor_uid, target_uid, &target)
            .to_json()
            .dump())
    }

    pub fn compute_seating_json(config_json: &str) -> Result<String, String> {
        let config = json::parse(config_json).map_err(|e| e.to_string())?;
        let players: Vec<String> = config["players"]
            .members()
            .filter_map(|p| p.as_str().map(|s| s.to_string()))
            .collect();
        let rounds_count = config["rounds"].as_usize().unwrap_or(3);
        let previous_rounds: Option<Vec<Vec<Vec<String>>>> = if config["previous_rounds"].is_null()
        {
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
                        .map(|t| JsonValue::Array(t.iter().map(|p| p.as_str().into()).collect()))
                        .collect(),
                )
            })
            .collect();
        Ok(json::object! { rounds: rounds_json, score: score.to_json() }.dump())
    }

    pub fn score_seating_json(config_json: &str) -> Result<String, String> {
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
            let id: u32 = id_str
                .parse()
                .map_err(|_| format!("Invalid card ID: {id_str}"))?;
            d.cards.insert(id, count_val.as_u32().unwrap_or(0));
        }
        Ok(d)
    }

    pub fn parse_deck_json(text: &str, cards_json: &str) -> Result<String, String> {
        let card_map = cards::CardMap::load(cards_json)?;
        let result = deck::parse_deck(text, &card_map)?;
        let mut json = result.deck.to_json();
        if !result.unrecognized_lines.is_empty() {
            let lines: Vec<JsonValue> = result
                .unrecognized_lines
                .iter()
                .map(|l| l.as_str().into())
                .collect();
            json["unrecognized_lines"] = JsonValue::Array(lines);
        }
        Ok(json.dump())
    }

    pub fn validate_deck_json(
        deck_json: &str,
        cards_json: &str,
        format: &str,
    ) -> Result<String, String> {
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

    #[allow(clippy::too_many_arguments)]
    pub fn export_twda_json(
        deck_json: &str,
        cards_json: &str,
        tournament_name: &str,
        tournament_date: &str,
        tournament_place: &str,
        tournament_format: &str,
        tournament_url: &str,
        player_count: u32,
        player_name: &str,
    ) -> Result<String, String> {
        let card_map = cards::CardMap::load(cards_json)?;
        let value = json::parse(deck_json).map_err(|e| e.to_string())?;
        let d = deck_from_json(&value, true)?;
        Ok(deck::export_twda(
            &d,
            &card_map,
            tournament_name,
            tournament_date,
            tournament_place,
            tournament_format,
            tournament_url,
            player_count,
            player_name,
        ))
    }

    pub fn compute_league_standings_json(config_json: &str) -> Result<String, String> {
        league::compute_league_standings(config_json)
    }

    pub fn compute_player_issues_json(config_json: &str) -> Result<String, String> {
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
        let issues = seating::compute_player_issues(&rounds);
        Ok(JsonValue::Array(issues.iter().map(|i| i.to_json()).collect()).dump())
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
        #[allow(clippy::new_without_default)]
        pub fn new() -> Self {
            WasmEngine
        }

        #[wasm_bindgen(js_name = canChangeRole)]
        pub fn can_change_role(
            &self,
            actor_json: &str,
            target_json: &str,
            role: &str,
        ) -> Result<String, String> {
            can_change_role_json(actor_json, target_json, role)
        }

        #[wasm_bindgen(js_name = canManageVekn)]
        pub fn can_manage_vekn(
            &self,
            actor_json: &str,
            target_json: &str,
        ) -> Result<String, String> {
            can_manage_vekn_json(actor_json, target_json)
        }

        #[wasm_bindgen(js_name = canEditUser)]
        pub fn can_edit_user(
            &self,
            actor_json: &str,
            actor_uid: &str,
            target_uid: &str,
            target_json: &str,
        ) -> Result<String, String> {
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
        pub fn process_tournament_event(
            &self,
            tournament_json: &str,
            event_json: &str,
            actor_json: &str,
            sanctions_json: &str,
            decks_json: &str,
        ) -> Result<String, String> {
            super::tournament::process_tournament_event(
                tournament_json,
                event_json,
                actor_json,
                sanctions_json,
                decks_json,
            )
        }

        #[wasm_bindgen(js_name = computeRatingPoints)]
        pub fn compute_rating_points(
            &self,
            vp: f64,
            gw: i32,
            finalist_position: i32,
            player_count: i32,
            rank: &str,
        ) -> i32 {
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
        pub fn validate_deck(
            &self,
            deck_json: &str,
            cards_json: &str,
            format: &str,
        ) -> Result<String, String> {
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

        #[wasm_bindgen(js_name = computePlayerIssues)]
        pub fn compute_player_issues(&self, config_json: &str) -> Result<String, String> {
            compute_player_issues_json(config_json)
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
        r.map_err(pyo3::exceptions::PyValueError::new_err)
    }

    #[pyclass]
    pub struct PyEngine;

    #[pymethods]
    impl PyEngine {
        #[new]
        fn new() -> Self {
            PyEngine
        }

        fn can_change_role(
            &self,
            actor_json: &str,
            target_json: &str,
            role: &str,
        ) -> PyResult<String> {
            py_str(can_change_role_json(actor_json, target_json, role))
        }

        fn can_manage_vekn(&self, actor_json: &str, target_json: &str) -> PyResult<String> {
            py_str(can_manage_vekn_json(actor_json, target_json))
        }

        fn can_edit_user(
            &self,
            actor_json: &str,
            actor_uid: &str,
            target_uid: &str,
            target_json: &str,
        ) -> PyResult<String> {
            py_str(can_edit_user_json(
                actor_json,
                actor_uid,
                target_uid,
                target_json,
            ))
        }

        fn compute_seating(&self, config_json: &str) -> PyResult<String> {
            py_str(compute_seating_json(config_json))
        }

        fn score_seating(&self, config_json: &str) -> PyResult<String> {
            py_str(score_seating_json(config_json))
        }

        fn process_tournament_event(
            &self,
            tournament_json: &str,
            event_json: &str,
            actor_json: &str,
            sanctions_json: &str,
            decks_json: &str,
        ) -> PyResult<String> {
            py_str(super::tournament::process_tournament_event(
                tournament_json,
                event_json,
                actor_json,
                sanctions_json,
                decks_json,
            ))
        }

        fn compute_rating_points(
            &self,
            vp: f64,
            gw: i32,
            finalist_position: i32,
            player_count: i32,
            rank: &str,
        ) -> i32 {
            super::ratings::compute_rating_points(vp, gw, finalist_position, player_count, rank)
        }

        fn rating_category(&self, format: &str, online: bool) -> String {
            super::ratings::rating_category(format, online).to_string()
        }

        fn parse_deck(&self, text: &str, cards_json: &str) -> PyResult<String> {
            py_str(parse_deck_json(text, cards_json))
        }

        fn validate_deck(
            &self,
            deck_json: &str,
            cards_json: &str,
            format: &str,
        ) -> PyResult<String> {
            py_str(validate_deck_json(deck_json, cards_json, format))
        }

        fn enrich_deck(&self, deck_json: &str, cards_json: &str) -> PyResult<String> {
            py_str(enrich_deck_json(deck_json, cards_json))
        }

        fn compute_league_standings(&self, config_json: &str) -> PyResult<String> {
            py_str(compute_league_standings_json(config_json))
        }

        fn compute_player_issues(&self, config_json: &str) -> PyResult<String> {
            py_str(compute_player_issues_json(config_json))
        }

        #[allow(clippy::too_many_arguments)]
        fn export_twda(
            &self,
            deck_json: &str,
            cards_json: &str,
            tournament_name: &str,
            tournament_date: &str,
            tournament_place: &str,
            tournament_format: &str,
            tournament_url: &str,
            player_count: u32,
            player_name: &str,
        ) -> PyResult<String> {
            py_str(export_twda_json(
                deck_json,
                cards_json,
                tournament_name,
                tournament_date,
                tournament_place,
                tournament_format,
                tournament_url,
                player_count,
                player_name,
            ))
        }

        /// Check VP validity for a table. Returns error string or None if valid.
        fn check_table_vps(&self, vps: Vec<f64>) -> PyResult<Option<String>> {
            Ok(super::tournament::check_table_vps(&vps).map(|e| format!("{:?}", e)))
        }

        /// Compute game wins for each player at a table.
        fn compute_gw(&self, vps: Vec<f64>, adjustments: Vec<f64>) -> Vec<f64> {
            super::tournament::compute_gw(&vps, &adjustments)
        }

        /// Compute tournament points for each player at a table.
        fn compute_tp(&self, table_size: usize, vps: Vec<f64>) -> Vec<f64> {
            super::tournament::compute_tp(table_size, &vps)
        }
    }

    #[pymodule]
    fn archon_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add_class::<PyEngine>()?;
        Ok(())
    }
}

