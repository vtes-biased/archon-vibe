use json::JsonValue;

pub mod cards;
pub mod deck;
pub mod error;
pub mod league;
mod permissions;
pub mod ratings;
pub mod sanctions;
pub mod seating;
pub mod tournament;

pub use error::EngineError;

pub use permissions::{
    can_change_country, can_change_role, can_delete_sanction, can_edit_league, can_issue_sanction,
    can_lift_sanction, can_link_tournament_to_league, can_take_tournament_offline, check,
    is_official, is_organizer, unconditional_capabilities, Capability, OwnedResource,
    PermissionResult, Request, Role, SanctionContext, UserContext,
};

// Shared JSON→core→JSON functions used by both WASM and PyO3 shims; appear
// unused when neither feature is enabled (test builds).
#[allow(dead_code)]
mod shared {
    use super::*;
    use crate::error::EngineError;

    pub fn can_change_role_json(
        actor_json: &str,
        target_json: &str,
        role_str: &str,
    ) -> Result<String, EngineError> {
        let actor = UserContext::from_json(&json::parse(actor_json)?)?;
        let target = UserContext::from_json(&json::parse(target_json)?)?;
        let role = Role::from_str(role_str)
            .ok_or_else(|| EngineError::internal(format!("Unknown role: {}", role_str)))?;
        Ok(can_change_role(&actor, &target, role).to_json().dump())
    }

    /// The single authorization entry point for both bindings. Request shape:
    /// `{actor, actor_uid, target_uid?, target_country?, resource?}` — supply only the fields the rule reads.
    pub fn check_permission_json(
        capability: &str,
        request_json: &str,
    ) -> Result<String, EngineError> {
        let capability = Capability::from_str(capability)
            .ok_or_else(|| EngineError::internal(format!("Unknown capability: {}", capability)))?;
        let value = json::parse(request_json)?;
        let actor = UserContext::from_json(&value["actor"])?;
        let resource = value["resource"]
            .is_object()
            .then(|| OwnedResource::from_json(&value["resource"]));
        let mut request = Request::new(&actor, value["actor_uid"].as_str().unwrap_or(""));
        request.target_uid = value["target_uid"].as_str();
        request.target_country = value["target_country"].as_str();
        request.resource = resource.as_ref();
        Ok(check(capability, &request).to_json().dump())
    }

    pub fn unconditional_capabilities_json(actor_json: &str) -> Result<String, EngineError> {
        let actor = UserContext::from_json(&json::parse(actor_json)?)?;
        let names: Vec<JsonValue> = unconditional_capabilities(&actor)
            .into_iter()
            .map(JsonValue::from)
            .collect();
        Ok(JsonValue::Array(names).dump())
    }

    pub fn is_official_json(actor_json: &str) -> Result<bool, EngineError> {
        Ok(is_official(&UserContext::from_json(&json::parse(
            actor_json,
        )?)?))
    }

    pub fn can_change_country_json(
        actor_json: &str,
        target_json: &str,
    ) -> Result<String, EngineError> {
        let actor = UserContext::from_json(&json::parse(actor_json)?)?;
        let target = UserContext::from_json(&json::parse(target_json)?)?;
        Ok(can_change_country(&actor, &target).to_json().dump())
    }

    pub fn can_link_tournament_to_league_json(
        actor_json: &str,
        actor_uid: &str,
        league_json: &str,
    ) -> Result<String, EngineError> {
        let actor = UserContext::from_json(&json::parse(actor_json)?)?;
        let league = OwnedResource::from_json(&json::parse(league_json)?);
        Ok(can_link_tournament_to_league(&actor, actor_uid, &league)
            .to_json()
            .dump())
    }

    pub fn can_take_tournament_offline_json(
        actor_json: &str,
        actor_uid: &str,
        tournament_json: &str,
    ) -> Result<String, EngineError> {
        let actor = UserContext::from_json(&json::parse(actor_json)?)?;
        let tournament = OwnedResource::from_json(&json::parse(tournament_json)?);
        Ok(can_take_tournament_offline(&actor, actor_uid, &tournament)
            .to_json()
            .dump())
    }

    pub fn can_issue_sanction_json(
        actor_json: &str,
        actor_uid: &str,
        level: &str,
        tournament_json: &str,
    ) -> Result<String, EngineError> {
        let actor = UserContext::from_json(&json::parse(actor_json)?)?;
        let tournament = OwnedResource::from_json(&json::parse(tournament_json)?);
        Ok(can_issue_sanction(&actor, actor_uid, level, &tournament)
            .to_json()
            .dump())
    }

    pub fn can_lift_sanction_json(
        actor_json: &str,
        actor_uid: &str,
        ctx_json: &str,
    ) -> Result<String, EngineError> {
        let actor = UserContext::from_json(&json::parse(actor_json)?)?;
        let ctx = SanctionContext::from_json(&json::parse(ctx_json)?);
        Ok(can_lift_sanction(&actor, actor_uid, &ctx).to_json().dump())
    }

    pub fn can_delete_sanction_json(
        actor_json: &str,
        actor_uid: &str,
        ctx_json: &str,
    ) -> Result<String, EngineError> {
        let actor = UserContext::from_json(&json::parse(actor_json)?)?;
        let ctx = SanctionContext::from_json(&json::parse(ctx_json)?);
        Ok(can_delete_sanction(&actor, actor_uid, &ctx)
            .to_json()
            .dump())
    }

    pub fn score_seating_json(config_json: &str) -> Result<String, EngineError> {
        let config = json::parse(config_json)?;
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
    pub fn deck_from_json(
        value: &JsonValue,
        with_metadata: bool,
    ) -> Result<deck::Deck, EngineError> {
        let mut d = deck::Deck::new();
        d.name = value["name"].as_str().unwrap_or("").to_string();
        if with_metadata {
            d.author = value["author"].as_str().unwrap_or("").to_string();
            d.comments = value["comments"].as_str().unwrap_or("").to_string();
        }
        for (id_str, count_val) in value["cards"].entries() {
            let id: u32 = id_str
                .parse()
                .map_err(|_| EngineError::internal(format!("Invalid card ID: {id_str}")))?;
            d.cards.insert(id, count_val.as_u32().unwrap_or(0));
        }
        Ok(d)
    }

    pub fn parse_deck_json(text: &str, cards_json: &str) -> Result<String, EngineError> {
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
    ) -> Result<String, EngineError> {
        let card_map = cards::CardMap::load(cards_json)?;
        let value = json::parse(deck_json)?;
        let d = deck_from_json(&value, false)?;
        let errors = deck::validate_deck(&d, &card_map, format);
        Ok(JsonValue::Array(errors.iter().map(|e| e.to_json()).collect()).dump())
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
    ) -> Result<String, EngineError> {
        let card_map = cards::CardMap::load(cards_json)?;
        let value = json::parse(deck_json)?;
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

    pub fn create_tournament_json(
        config_json: &str,
        actor_json: &str,
    ) -> Result<String, EngineError> {
        super::tournament::create_tournament(config_json, actor_json)
    }

    pub fn compute_league_standings_json(config_json: &str) -> Result<String, EngineError> {
        league::compute_league_standings(config_json)
    }

    /// Preview GW/TP for one table exactly as SetScore computes them (SA cascade
    /// included) — keeps UI previews in lockstep with persisted results.
    pub fn preview_scores_json(config_json: &str) -> Result<String, EngineError> {
        super::tournament::preview_scores_json(config_json)
    }

    /// Reorders preliminary standings into final placement (winner first, other
    /// finalists tied for 2nd, then non-finalists), tagging each with `rank`.
    pub fn compute_final_standings_json(config_json: &str) -> Result<String, EngineError> {
        let config = json::parse(config_json)?;
        let winner = config["winner"].as_str().unwrap_or("");
        let ranked = super::tournament::compute_final_standings(&config["standings"], winner);
        Ok(json::JsonValue::Array(ranked).dump())
    }

    pub fn finals_qualification_json(config_json: &str) -> Result<String, EngineError> {
        let config = json::parse(config_json)?;
        Ok(
            super::tournament::finals_qualification(&config["tournament"], &config["standings"])
                .dump(),
        )
    }

    /// Returns `null` when the table is scorable, else `{ code, seats }` so the
    /// UI can say *why* a table won't close instead of leaving it silently unfinished.
    pub fn check_table_vps_json(config_json: &str) -> Result<String, EngineError> {
        let config = json::parse(config_json)?;
        let vps: Vec<f64> = config["vps"]
            .members()
            .map(|v| v.as_f64().unwrap_or(0.0))
            .collect();
        Ok(match super::tournament::check_table_vps(&vps) {
            Some(e) => e.to_json().dump(),
            None => "null".to_string(),
        })
    }

    pub fn compute_player_issues_json(config_json: &str) -> Result<String, EngineError> {
        let config = json::parse(config_json)?;
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

#[cfg(feature = "wasm")]
mod wasm {
    use super::shared::*;
    use wasm_bindgen::prelude::*;

    #[wasm_bindgen]
    pub struct WasmEngine;

    /// Err arm crosses into JS as a thrown string carrying the EngineError wire
    /// JSON ({"code","params","message"}); engine.ts re-throws it as a typed error.
    fn js_str(r: Result<String, super::EngineError>) -> Result<String, String> {
        r.map_err(|e| e.to_json())
    }

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
            js_str(can_change_role_json(actor_json, target_json, role))
        }

        #[wasm_bindgen(js_name = checkPermission)]
        pub fn check_permission(
            &self,
            capability: &str,
            request_json: &str,
        ) -> Result<String, String> {
            js_str(check_permission_json(capability, request_json))
        }

        #[wasm_bindgen(js_name = isOfficial)]
        pub fn is_official(&self, actor_json: &str) -> Result<bool, String> {
            is_official_json(actor_json).map_err(|e| e.to_json())
        }

        #[wasm_bindgen(js_name = canChangeCountry)]
        pub fn can_change_country(
            &self,
            actor_json: &str,
            target_json: &str,
        ) -> Result<String, String> {
            js_str(can_change_country_json(actor_json, target_json))
        }

        #[wasm_bindgen(js_name = canLinkTournamentToLeague)]
        pub fn can_link_tournament_to_league(
            &self,
            actor_json: &str,
            actor_uid: &str,
            league_json: &str,
        ) -> Result<String, String> {
            js_str(can_link_tournament_to_league_json(
                actor_json,
                actor_uid,
                league_json,
            ))
        }

        #[wasm_bindgen(js_name = canTakeTournamentOffline)]
        pub fn can_take_tournament_offline(
            &self,
            actor_json: &str,
            actor_uid: &str,
            tournament_json: &str,
        ) -> Result<String, String> {
            js_str(can_take_tournament_offline_json(
                actor_json,
                actor_uid,
                tournament_json,
            ))
        }

        #[wasm_bindgen(js_name = canIssueSanction)]
        pub fn can_issue_sanction(
            &self,
            actor_json: &str,
            actor_uid: &str,
            level: &str,
            tournament_json: &str,
        ) -> Result<String, String> {
            js_str(can_issue_sanction_json(
                actor_json,
                actor_uid,
                level,
                tournament_json,
            ))
        }

        #[wasm_bindgen(js_name = canLiftSanction)]
        pub fn can_lift_sanction(
            &self,
            actor_json: &str,
            actor_uid: &str,
            ctx_json: &str,
        ) -> Result<String, String> {
            js_str(can_lift_sanction_json(actor_json, actor_uid, ctx_json))
        }

        #[wasm_bindgen(js_name = canDeleteSanction)]
        pub fn can_delete_sanction(
            &self,
            actor_json: &str,
            actor_uid: &str,
            ctx_json: &str,
        ) -> Result<String, String> {
            js_str(can_delete_sanction_json(actor_json, actor_uid, ctx_json))
        }

        #[wasm_bindgen(js_name = scoreSeating)]
        pub fn score_seating(&self, config_json: &str) -> Result<String, String> {
            js_str(score_seating_json(config_json))
        }

        #[wasm_bindgen(js_name = previewScores)]
        pub fn preview_scores(&self, config_json: &str) -> Result<String, String> {
            js_str(preview_scores_json(config_json))
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
            js_str(super::tournament::process_tournament_event(
                tournament_json,
                event_json,
                actor_json,
                sanctions_json,
                decks_json,
            ))
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

        /// A player's SA-adjusted (vp, gw), finals included, as `[vp, gw]` — the
        /// same aggregation the backend rating uses (standings are prelim-only).
        #[wasm_bindgen(js_name = computeRatingVpGw)]
        pub fn compute_rating_vp_gw(
            &self,
            tournament_json: &str,
            sanctions_json: &str,
            user_uid: &str,
        ) -> Result<Vec<f64>, String> {
            let tournament =
                json::parse(tournament_json).map_err(|e| super::EngineError::from(e).to_json())?;
            let sanctions =
                json::parse(sanctions_json).map_err(|e| super::EngineError::from(e).to_json())?;
            let (vp, gw) =
                super::tournament::compute_rating_vp_gw(&tournament, &sanctions, user_uid);
            Ok(vec![vp, gw])
        }

        #[wasm_bindgen(js_name = ratingCategory)]
        pub fn rating_category(&self, format: &str, online: bool) -> String {
            super::ratings::rating_category(format, online).to_string()
        }

        /// "eligible" or the blocking reason: "open_rounds" | "no_results" | "few_players" | "no_final".
        #[wasm_bindgen(js_name = rankingEligibility)]
        pub fn ranking_eligibility(&self, tournament_json: &str) -> Result<String, String> {
            let t =
                json::parse(tournament_json).map_err(|e| super::EngineError::from(e).to_json())?;
            Ok(super::ratings::ranking_eligibility(&t).to_string())
        }

        /// Field size for the rating coefficient and the win floors — not the
        /// played-player set, which callers still enumerate themselves.
        #[wasm_bindgen(js_name = attestedPlayerCount)]
        pub fn attested_player_count(&self, tournament_json: &str) -> Result<usize, String> {
            let t =
                json::parse(tournament_json).map_err(|e| super::EngineError::from(e).to_json())?;
            Ok(super::ratings::attested_player_count(&t))
        }

        #[wasm_bindgen(js_name = parseDeck)]
        pub fn parse_deck(&self, text: &str, cards_json: &str) -> Result<String, String> {
            js_str(parse_deck_json(text, cards_json))
        }

        #[wasm_bindgen(js_name = validateDeck)]
        pub fn validate_deck(
            &self,
            deck_json: &str,
            cards_json: &str,
            format: &str,
        ) -> Result<String, String> {
            js_str(validate_deck_json(deck_json, cards_json, format))
        }

        #[wasm_bindgen(js_name = createTournament)]
        pub fn create_tournament(
            &self,
            config_json: &str,
            actor_json: &str,
        ) -> Result<String, String> {
            js_str(create_tournament_json(config_json, actor_json))
        }

        #[wasm_bindgen(js_name = computeLeagueStandings)]
        pub fn compute_league_standings(&self, config_json: &str) -> Result<String, String> {
            js_str(compute_league_standings_json(config_json))
        }

        #[wasm_bindgen(js_name = computeFinalStandings)]
        pub fn compute_final_standings(&self, config_json: &str) -> Result<String, String> {
            js_str(compute_final_standings_json(config_json))
        }

        #[wasm_bindgen(js_name = finalsQualification)]
        pub fn finals_qualification(&self, config_json: &str) -> Result<String, String> {
            js_str(finals_qualification_json(config_json))
        }

        #[wasm_bindgen(js_name = checkTableVps)]
        pub fn check_table_vps(&self, config_json: &str) -> Result<String, String> {
            js_str(check_table_vps_json(config_json))
        }

        #[wasm_bindgen(js_name = computePlayerIssues)]
        pub fn compute_player_issues(&self, config_json: &str) -> Result<String, String> {
            js_str(compute_player_issues_json(config_json))
        }

        /// Judges-Guide penalty reference (categories, baselines, levels,
        /// escalation) — static data owned by engine/src/sanctions.rs.
        #[wasm_bindgen(js_name = sanctionReference)]
        pub fn sanction_reference(&self) -> String {
            crate::sanctions::sanction_reference_json()
        }

        #[wasm_bindgen(js_name = foldAscii)]
        pub fn fold_ascii(&self, s: &str) -> String {
            crate::cards::fold_ascii(s)
        }

        /// Offline sanction management: the device-locked client recomputes
        /// standings from IDB sanctions (mirrors PyEngine.update_standings).
        #[wasm_bindgen(js_name = updateStandings)]
        pub fn update_standings(
            &self,
            tournament_json: &str,
            sanctions_json: &str,
        ) -> Result<String, String> {
            js_str(super::tournament::update_standings_json(
                tournament_json,
                sanctions_json,
            ))
        }
    }
}

#[cfg(feature = "python")]
mod python {
    use super::shared::*;
    use pyo3::prelude::*;

    /// Err arm crosses into Python as a ValueError whose message is the
    /// EngineError wire JSON ({"code","params","message"}); the backend parses it.
    fn py_str(r: Result<String, super::EngineError>) -> PyResult<String> {
        r.map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_json()))
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

        fn check_permission(&self, capability: &str, request_json: &str) -> PyResult<String> {
            py_str(check_permission_json(capability, request_json))
        }

        fn can_change_country(&self, actor_json: &str, target_json: &str) -> PyResult<String> {
            py_str(can_change_country_json(actor_json, target_json))
        }

        fn unconditional_capabilities(&self, actor_json: &str) -> PyResult<String> {
            py_str(unconditional_capabilities_json(actor_json))
        }

        fn is_official(&self, actor_json: &str) -> PyResult<bool> {
            is_official_json(actor_json)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_json()))
        }

        /// VEKN legality gate for the online create route, which builds the
        /// Tournament in Python and never runs engine create_tournament.
        fn validate_rank_legality(
            &self,
            format: &str,
            rank: &str,
            proxies: bool,
            multideck: bool,
        ) -> PyResult<()> {
            crate::tournament::validate_rank_legality(format, rank, proxies, multideck)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_json()))
        }

        /// Date-ordering gate for the online create route (same reason as
        /// `validate_rank_legality`: that route never runs create_tournament).
        fn validate_finish_after_start(&self, start: &str, finish: &str) -> PyResult<()> {
            crate::tournament::validate_finish_after_start(start, finish)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_json()))
        }

        fn can_link_tournament_to_league(
            &self,
            actor_json: &str,
            actor_uid: &str,
            league_json: &str,
        ) -> PyResult<String> {
            py_str(can_link_tournament_to_league_json(
                actor_json,
                actor_uid,
                league_json,
            ))
        }

        fn can_take_tournament_offline(
            &self,
            actor_json: &str,
            actor_uid: &str,
            tournament_json: &str,
        ) -> PyResult<String> {
            py_str(can_take_tournament_offline_json(
                actor_json,
                actor_uid,
                tournament_json,
            ))
        }

        fn can_issue_sanction(
            &self,
            actor_json: &str,
            actor_uid: &str,
            level: &str,
            tournament_json: &str,
        ) -> PyResult<String> {
            py_str(can_issue_sanction_json(
                actor_json,
                actor_uid,
                level,
                tournament_json,
            ))
        }

        fn can_lift_sanction(
            &self,
            actor_json: &str,
            actor_uid: &str,
            ctx_json: &str,
        ) -> PyResult<String> {
            py_str(can_lift_sanction_json(actor_json, actor_uid, ctx_json))
        }

        fn can_delete_sanction(
            &self,
            actor_json: &str,
            actor_uid: &str,
            ctx_json: &str,
        ) -> PyResult<String> {
            py_str(can_delete_sanction_json(actor_json, actor_uid, ctx_json))
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

        /// "eligible" or the blocking reason: "open_rounds" | "no_results" | "few_players" | "no_final".
        fn ranking_eligibility(&self, tournament_json: &str) -> PyResult<String> {
            use pyo3::exceptions::PyValueError;
            let t = json::parse(tournament_json)
                .map_err(|e| PyValueError::new_err(super::EngineError::from(e).to_json()))?;
            Ok(super::ratings::ranking_eligibility(&t).to_string())
        }

        /// Field size for the rating coefficient and the win floors — not the
        /// played-player set, which callers still enumerate themselves.
        fn attested_player_count(&self, tournament_json: &str) -> PyResult<usize> {
            use pyo3::exceptions::PyValueError;
            let t = json::parse(tournament_json)
                .map_err(|e| PyValueError::new_err(super::EngineError::from(e).to_json()))?;
            Ok(super::ratings::attested_player_count(&t))
        }

        /// Compute a player's SA-adjusted (vp, gw) for rating/VEKN-push, so the
        /// backend does not re-implement SA scoring. Includes finals VP/GW.
        fn compute_rating_vp_gw(
            &self,
            tournament_json: &str,
            sanctions_json: &str,
            user_uid: &str,
        ) -> PyResult<(f64, f64)> {
            use pyo3::exceptions::PyValueError;
            let tournament = json::parse(tournament_json)
                .map_err(|e| PyValueError::new_err(super::EngineError::from(e).to_json()))?;
            let sanctions = json::parse(sanctions_json)
                .map_err(|e| PyValueError::new_err(super::EngineError::from(e).to_json()))?;
            Ok(super::tournament::compute_rating_vp_gw(
                &tournament,
                &sanctions,
                user_uid,
            ))
        }

        /// Recomputes standings from rounds + sanctions, for sanction mutations
        /// (issue/lift/delete) which aren't TournamentEvents and so bypass process_tournament_event.
        fn update_standings(
            &self,
            tournament_json: &str,
            sanctions_json: &str,
        ) -> PyResult<String> {
            py_str(super::tournament::update_standings_json(
                tournament_json,
                sanctions_json,
            ))
        }

        /// Judges-Guide penalty reference (categories, baselines, levels,
        /// escalation) — static data owned by engine/src/sanctions.rs.
        fn sanction_reference(&self) -> String {
            crate::sanctions::sanction_reference_json()
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

        fn create_tournament(&self, config_json: &str, actor_json: &str) -> PyResult<String> {
            py_str(create_tournament_json(config_json, actor_json))
        }

        fn compute_league_standings(&self, config_json: &str) -> PyResult<String> {
            py_str(compute_league_standings_json(config_json))
        }

        fn compute_final_standings(&self, config_json: &str) -> PyResult<String> {
            py_str(compute_final_standings_json(config_json))
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

        fn check_table_vps(&self, vps: Vec<f64>) -> PyResult<Option<String>> {
            Ok(super::tournament::check_table_vps(&vps).map(|e| format!("{:?}", e)))
        }

        fn compute_gw(&self, vps: Vec<f64>, adjustments: Vec<f64>) -> Vec<f64> {
            super::tournament::compute_gw(&vps, &adjustments)
        }

        /// Compute finals game wins: exactly one winner — highest adjusted VP,
        /// tiebroken by seed order (no prelim 2-VP threshold).
        fn compute_gw_finals(
            &self,
            vps: Vec<f64>,
            adjustments: Vec<f64>,
            seating_uids: Vec<String>,
            seed_order: Vec<String>,
        ) -> Vec<f64> {
            let uid_refs: Vec<&str> = seating_uids.iter().map(String::as_str).collect();
            super::tournament::compute_gw_finals(&vps, &adjustments, &uid_refs, &seed_order)
        }

        fn compute_tp(&self, table_size: usize, vps: Vec<f64>, adjustments: Vec<f64>) -> Vec<f64> {
            super::tournament::compute_tp(table_size, &vps, &adjustments)
        }
    }

    #[pymodule]
    fn archon_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add_class::<PyEngine>()?;
        Ok(())
    }
}
