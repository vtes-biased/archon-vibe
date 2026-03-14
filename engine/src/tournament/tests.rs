//! Tests for tournament engine.

#[cfg(test)]
mod tests {
    use super::super::*;

    fn make_tournament() -> JsonValue {
        json::object! {
            uid: "test-tournament",
            modified: "2025-01-01T00:00:00Z",
            name: "Test Tournament",
            state: "Planned",
            format: "Standard",
            rank: "",
            max_rounds: 3,
            organizers_uids: ["organizer-1"],
            players: [],
            rounds: [],
        }
    }

    fn make_organizer() -> JsonValue {
        json::object! {
            uid: "organizer-1",
            roles: ["Prince"],
            is_organizer: true,
        }
    }

    fn make_player(uid: &str) -> JsonValue {
        json::object! {
            uid: uid,
            roles: [],
            is_organizer: false,
        }
    }

    fn no_sanctions() -> String {
        "[]".to_string()
    }

    fn no_decks() -> String {
        "[]".to_string()
    }

    /// Helper to run a tournament event with empty sanctions and no decks
    fn run_event(
        tournament: &JsonValue,
        event: &JsonValue,
        actor: &JsonValue,
    ) -> Result<String, String> {
        let raw = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
            &no_sanctions(),
            &no_decks(),
        )?;
        let parsed = json::parse(&raw).unwrap();
        Ok(parsed["tournament"].dump())
    }

    /// Helper to run a tournament event with existing decks metadata
    fn run_event_with_decks(
        tournament: &JsonValue,
        event: &JsonValue,
        actor: &JsonValue,
        decks_json: &str,
    ) -> Result<(String, JsonValue), String> {
        let raw = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
            &no_sanctions(),
            decks_json,
        )?;
        let parsed = json::parse(&raw).unwrap();
        Ok((parsed["tournament"].dump(), parsed["deck_ops"].clone()))
    }

    #[test]
    fn test_open_registration() {
        let tournament = make_tournament();
        let event = json::object! { type: "OpenRegistration" };
        let actor = make_organizer();

        let result = run_event(&tournament, &event, &actor);

        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["state"].as_str(), Some("Registration"));
    }

    #[test]
    fn test_register_player() {
        let mut tournament = make_tournament();
        tournament["state"] = "Registration".into();

        let event = json::object! {
            type: "Register",
            user_uid: "player-1",
            vekn_id: "1000001",
        };
        let actor = make_player("player-1");

        let result = run_event(&tournament, &event, &actor);

        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["players"].len(), 1);
        assert_eq!(updated["players"][0]["user_uid"].as_str(), Some("player-1"));
    }

    #[test]
    fn test_register_without_vekn_id_rejected() {
        let mut tournament = make_tournament();
        tournament["state"] = "Registration".into();

        let event = json::object! {
            type: "Register",
            user_uid: "player-1",
        };
        let actor = make_player("player-1");
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("VEKN ID"));

        // Also reject empty string
        let event2 = json::object! {
            type: "Register",
            user_uid: "player-1",
            vekn_id: "",
        };
        let result2 = run_event(&tournament, &event2, &actor);
        assert!(result2.is_err());
        assert!(result2.unwrap_err().contains("VEKN ID"));
    }

    #[test]
    fn test_add_player_without_vekn_id_rejected() {
        let mut tournament = make_tournament();
        tournament["state"] = "Registration".into();

        let event = json::object! {
            type: "AddPlayer",
            user_uid: "player-1",
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("VEKN ID"));
    }

    #[test]
    fn test_add_player_with_vekn_id() {
        let mut tournament = make_tournament();
        tournament["state"] = "Registration".into();

        let event = json::object! {
            type: "AddPlayer",
            user_uid: "player-1",
            vekn_id: "1000042",
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["players"].len(), 1);
        assert_eq!(updated["players"][0]["user_uid"].as_str(), Some("player-1"));
    }

    #[test]
    fn test_check_in_all() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Registered", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Registered", payment_status: "Pending", toss: 0 },
        ];

        let event = json::object! { type: "CheckInAll" };
        let actor = make_organizer();

        let result = run_event(&tournament, &event, &actor);

        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["players"][0]["state"].as_str(), Some("Checked-in"));
        assert_eq!(updated["players"][1]["state"].as_str(), Some("Checked-in"));
    }

    #[test]
    fn test_start_round_insufficient_players() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];

        let event = json::object! { type: "StartRound" };
        let actor = make_organizer();

        let result = run_event(&tournament, &event, &actor);

        assert!(result.is_err());
        assert!(result.unwrap_err().contains("at least 4"));
    }

    #[test]
    fn test_start_round_with_submitted_seating() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p0", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p3", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p4", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p5", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p6", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p7", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];

        // Use json::parse to build the event (same path as real JSON input)
        let event = json::parse(
            r#"{"type": "StartRound", "seating": [["p0","p1","p2","p3"],["p4","p5","p6","p7"]]}"#,
        )
        .unwrap();
        let actor = make_organizer();

        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok(), "StartRound failed: {:?}", result.err());
        let updated = json::parse(&result.unwrap()).unwrap();
        let round = &updated["rounds"][0];
        let t0: Vec<&str> = (0..round[0]["seating"].len())
            .map(|i| round[0]["seating"][i]["player_uid"].as_str().unwrap())
            .collect();
        let t1: Vec<&str> = (0..round[1]["seating"].len())
            .map(|i| round[1]["seating"][i]["player_uid"].as_str().unwrap())
            .collect();
        assert_eq!(t0, vec!["p0", "p1", "p2", "p3"]);
        assert_eq!(t1, vec!["p4", "p5", "p6", "p7"]);
    }

    #[test]
    fn test_start_round_drops_registered_players() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p0", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p3", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p4", state: "Registered", payment_status: "Pending", toss: 0 },
            { user_uid: "p5", state: "Registered", payment_status: "Pending", toss: 0 },
        ];

        let event = json::parse(
            r#"{"type": "StartRound", "seating": [["p0","p1","p2","p3"]]}"#,
        )
        .unwrap();
        let actor = make_organizer();

        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok(), "StartRound failed: {:?}", result.err());
        let updated = json::parse(&result.unwrap()).unwrap();

        // Checked-in players should now be Playing
        assert_eq!(updated["players"][0]["state"].as_str(), Some("Playing"));
        assert_eq!(updated["players"][3]["state"].as_str(), Some("Playing"));
        // Registered players should be dropped to Finished
        assert_eq!(updated["players"][4]["state"].as_str(), Some("Finished"));
        assert_eq!(updated["players"][5]["state"].as_str(), Some("Finished"));
    }

    #[test]
    fn test_non_organizer_cannot_open_registration() {
        let tournament = make_tournament();
        let event = json::object! { type: "OpenRegistration" };
        let actor = make_player("random-player");

        let result = run_event(&tournament, &event, &actor);

        assert!(result.is_err());
        assert!(result.unwrap_err().contains("organizers"));
    }

    // --- Deck lifecycle tests ---

    fn tournament_with_player(state: &str) -> JsonValue {
        let mut t = make_tournament();
        t["state"] = state.into();
        t["players"] = json::array![
            { user_uid: "player-1", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];
        t
    }

    #[test]
    fn test_player_upsert_deck_before_playing() {
        let tournament = tournament_with_player("Waiting");
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "Test", author: "", comments: "", cards: {} },
            multideck: false,
        };
        let actor = make_player("player-1");
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, "[]").unwrap();
        assert_eq!(deck_ops.len(), 1);
        assert_eq!(deck_ops[0]["op"].as_str(), Some("upsert"));
        assert_eq!(deck_ops[0]["deck"]["public"].as_bool(), Some(false));
    }

    #[test]
    fn test_player_blocked_during_playing_with_existing_deck() {
        let tournament = tournament_with_player("Playing");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "New", author: "", comments: "", cards: {} },
            multideck: false,
        };
        let actor = make_player("player-1");
        let result = run_event_with_decks(&tournament, &event, &actor, decks);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("in progress"));
    }

    #[test]
    fn test_organizer_can_upsert_during_playing() {
        let tournament = tournament_with_player("Playing");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "New", author: "", comments: "", cards: {} },
            multideck: false,
        };
        let actor = make_organizer();
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, decks).unwrap();
        assert_eq!(deck_ops.len(), 1);
        assert_eq!(deck_ops[0]["op"].as_str(), Some("upsert"));
    }

    #[test]
    fn test_player_can_upload_missing_deck_after_finish() {
        let tournament = tournament_with_player("Finished");
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "Recovery", author: "", comments: "", cards: {} },
            multideck: false,
        };
        let actor = make_player("player-1");
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, "[]").unwrap();
        assert_eq!(deck_ops.len(), 1);
    }

    #[test]
    fn test_player_cannot_replace_deck_after_finish() {
        let tournament = tournament_with_player("Finished");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "New", author: "", comments: "", cards: {} },
            multideck: false,
        };
        let actor = make_player("player-1");
        let result = run_event_with_decks(&tournament, &event, &actor, decks);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("finished"));
    }

    #[test]
    fn test_player_blocked_upsert_during_playing() {
        let tournament = tournament_with_player("Playing");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "New", author: "", comments: "", cards: {} },
            multideck: false,
        };
        let actor = make_player("player-1");
        let result = run_event_with_decks(&tournament, &event, &actor, decks);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("in progress"));
    }

    #[test]
    fn test_checkin_missing_decklist_warning() {
        let mut tournament = tournament_with_player("Waiting");
        tournament["decklist_required"] = true.into();
        tournament["players"][0]["state"] = "Registered".into();

        let event = json::object! { type: "CheckIn", player_uid: "player-1" };
        let actor = make_organizer();
        // No decks passed — should flag missing_decklist
        let (raw, _) = run_event_with_decks(&tournament, &event, &actor, "[]").unwrap();
        let updated = json::parse(&raw).unwrap();
        assert_eq!(updated["players"][0]["state"].as_str(), Some("Checked-in"));
        assert_eq!(
            updated["players"][0]["missing_decklist"].as_bool(),
            Some(true)
        );
    }

    #[test]
    fn test_checkin_with_decklist_no_warning() {
        let mut tournament = tournament_with_player("Waiting");
        tournament["decklist_required"] = true.into();
        tournament["players"][0]["state"] = "Registered".into();

        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! { type: "CheckIn", player_uid: "player-1" };
        let actor = make_organizer();
        let (raw, _) = run_event_with_decks(&tournament, &event, &actor, decks).unwrap();
        let updated = json::parse(&raw).unwrap();
        assert_eq!(updated["players"][0]["state"].as_str(), Some("Checked-in"));
        assert!(updated["players"][0]["missing_decklist"].is_null());
    }

    // --- Payment tracking tests ---

    #[test]
    fn test_set_payment_status() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "SetPaymentStatus", player_uid: "p1", status: "Paid" };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(
            updated["players"][0]["payment_status"].as_str(),
            Some("Paid")
        );
    }

    #[test]
    fn test_set_payment_status_invalid() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "SetPaymentStatus", player_uid: "p1", status: "Invalid" };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Invalid payment status"));
    }

    #[test]
    fn test_mark_all_paid() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Checked-in", payment_status: "Paid", toss: 0 },
            { user_uid: "p3", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "MarkAllPaid" };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(
            updated["players"][0]["payment_status"].as_str(),
            Some("Paid")
        );
        assert_eq!(
            updated["players"][1]["payment_status"].as_str(),
            Some("Paid")
        );
        assert_eq!(
            updated["players"][2]["payment_status"].as_str(),
            Some("Paid")
        );
    }

    #[test]
    fn test_non_organizer_cannot_set_payment() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "SetPaymentStatus", player_uid: "p1", status: "Paid" };
        let actor = make_player("p1");
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("organizers"));
    }

    // ================================================================
    // Sanctions tests
    // ================================================================

    #[test]
    fn test_gw_with_sa_adjustment() {
        // Player with 2.5 VP normally gets GW, but with -1.0 SA adjustment (1.5 VP adjusted) loses it
        let vps = vec![2.5, 1.0, 0.5, 0.5, 0.5];
        let no_adj = vec![0.0; 5];
        let gw_normal = compute_gw(&vps, &no_adj);
        assert_eq!(gw_normal[0], 1.0); // normally gets GW

        let adj = vec![-1.0, 0.0, 0.0, 0.0, 0.0];
        let gw_adjusted = compute_gw(&vps, &adj);
        assert_eq!(gw_adjusted[0], 0.0); // loses GW: adjusted VP 1.5 < 2.0
    }

    #[test]
    fn test_gw_with_sa_still_above_threshold() {
        // Player with 3.0 VP and -1.0 SA -> adjusted 2.0 VP, still >= 2.0 AND still highest -> keeps GW
        let vps = vec![3.0, 1.0, 0.5, 0.5, 0.0];
        let adj = vec![-1.0, 0.0, 0.0, 0.0, 0.0];
        let gw = compute_gw(&vps, &adj);
        assert_eq!(gw[0], 1.0); // keeps GW: adjusted 2.0, still highest
    }

    #[test]
    fn test_gw_finals_clear_winner() {
        // Clear winner with highest VP -- gets the GW regardless of seed
        let vps = vec![3.0, 1.0, 0.5, 0.5, 0.0];
        let adj = vec![0.0; 5];
        let seats = vec!["p1", "p2", "p3", "p4", "p5"];
        let seed = vec!["p5", "p4", "p3", "p2", "p1"]
            .into_iter()
            .map(String::from)
            .collect::<Vec<_>>();
        let gw = compute_gw_finals(&vps, &adj, &seats, &seed);
        assert_eq!(gw, vec![1.0, 0.0, 0.0, 0.0, 0.0]);
    }

    #[test]
    fn test_gw_finals_all_zero_vp_uses_seed() {
        // All at 0 VP -- top seed wins the tiebreak
        let vps = vec![0.0, 0.0, 0.0, 0.0, 0.0];
        let adj = vec![0.0; 5];
        let seats = vec!["p3", "p1", "p5", "p2", "p4"];
        let seed = vec!["p1", "p2", "p3", "p4", "p5"]
            .into_iter()
            .map(String::from)
            .collect::<Vec<_>>();
        let gw = compute_gw_finals(&vps, &adj, &seats, &seed);
        // p1 is top seed (index 0 in seed_order), seated at position 1
        assert_eq!(gw, vec![0.0, 1.0, 0.0, 0.0, 0.0]);
    }

    #[test]
    fn test_gw_finals_tied_vp_seed_tiebreak() {
        // Two players tied at 2 VP -- lower seed position wins
        let vps = vec![2.0, 0.0, 2.0, 1.0, 0.0];
        let adj = vec![0.0; 5];
        let seats = vec!["p1", "p2", "p3", "p4", "p5"];
        // p3 has better seed (position 1) than p1 (position 2)
        let seed = vec!["p5", "p3", "p1", "p2", "p4"]
            .into_iter()
            .map(String::from)
            .collect::<Vec<_>>();
        let gw = compute_gw_finals(&vps, &adj, &seats, &seed);
        // p3 wins: same VP but better seed
        assert_eq!(gw, vec![0.0, 0.0, 1.0, 0.0, 0.0]);
    }

    #[test]
    fn test_gw_finals_no_2vp_threshold() {
        // Unlike prelim compute_gw, finals doesn't require 2 VP
        // Winner at 1.5 VP still gets GW
        let vps = vec![1.5, 1.0, 0.5, 0.5, 0.5];
        let adj = vec![0.0; 5];
        let seats = vec!["p1", "p2", "p3", "p4", "p5"];
        let seed = vec!["p1", "p2", "p3", "p4", "p5"]
            .into_iter()
            .map(String::from)
            .collect::<Vec<_>>();
        let gw = compute_gw_finals(&vps, &adj, &seats, &seed);
        assert_eq!(gw, vec![1.0, 0.0, 0.0, 0.0, 0.0]);
    }

    #[test]
    fn test_gw_finals_adjustment_changes_winner() {
        // p1 has most raw VP but SA penalty drops them below p2
        let vps = vec![3.0, 2.5, 0.5, 0.0, 0.0];
        let adj = vec![-1.0, 0.0, 0.0, 0.0, 0.0];
        let seats = vec!["p1", "p2", "p3", "p4", "p5"];
        let seed = vec!["p1", "p2", "p3", "p4", "p5"]
            .into_iter()
            .map(String::from)
            .collect::<Vec<_>>();
        let gw = compute_gw_finals(&vps, &adj, &seats, &seed);
        // p2 wins: p1 adjusted to 2.0, p2 at 2.5
        assert_eq!(gw, vec![0.0, 1.0, 0.0, 0.0, 0.0]);
    }

    #[test]
    fn test_gw_finals_empty() {
        let gw = compute_gw_finals(&[], &[], &[], &[]);
        assert!(gw.is_empty());
    }

    #[test]
    fn test_gw_finals_4_player_table() {
        // Finals can also be 4 players
        let vps = vec![2.0, 1.0, 1.0, 1.0];
        let adj = vec![0.0; 4];
        let seats = vec!["p1", "p2", "p3", "p4"];
        let seed = vec!["p1", "p2", "p3", "p4"]
            .into_iter()
            .map(String::from)
            .collect::<Vec<_>>();
        let gw = compute_gw_finals(&vps, &adj, &seats, &seed);
        assert_eq!(gw, vec![1.0, 0.0, 0.0, 0.0]);
    }

    #[test]
    fn test_dq_player_cannot_checkin() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Disqualified", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "CheckIn", player_uid: "p1" };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Disqualified"));
    }

    #[test]
    fn test_dq_sanction_blocks_checkin() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Registered", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "CheckIn", player_uid: "p1" };
        let actor = make_organizer();
        let sanctions = json::array![
            { user_uid: "p1", level: "disqualification", round_number: json::Null, lifted_at: json::Null, deleted_at: json::Null }
        ];
        let result = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
            &sanctions.dump(),
            &no_decks(),
        );
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("disqualification"));
    }

    #[test]
    fn test_suspension_blocks_checkin() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Registered", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "CheckIn", player_uid: "p1" };
        let actor = make_organizer();
        let sanctions = json::array![
            { user_uid: "p1", level: "suspension", round_number: json::Null, lifted_at: json::Null, deleted_at: json::Null }
        ];
        let result = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
            &sanctions.dump(),
            &no_decks(),
        );
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("suspended"));
    }

    #[test]
    fn test_checkinall_skips_dq_players() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Registered", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Disqualified", payment_status: "Pending", toss: 0 },
            { user_uid: "p3", state: "Registered", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "CheckInAll" };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["players"][0]["state"].as_str(), Some("Checked-in"));
        assert_eq!(
            updated["players"][1]["state"].as_str(),
            Some("Disqualified")
        ); // stays DQ'd
        assert_eq!(updated["players"][2]["state"].as_str(), Some("Checked-in"));
    }

    #[test]
    fn test_finish_tournament_preserves_dq() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Disqualified", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "FinishTournament" };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["players"][0]["state"].as_str(), Some("Finished"));
        assert_eq!(
            updated["players"][1]["state"].as_str(),
            Some("Disqualified")
        ); // preserved
    }

    #[test]
    fn test_reopen_tournament_preserves_dq() {
        let mut tournament = make_tournament();
        tournament["state"] = "Finished".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Finished", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Disqualified", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "ReopenTournament" };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["players"][0]["state"].as_str(), Some("Checked-in"));
        assert_eq!(
            updated["players"][1]["state"].as_str(),
            Some("Disqualified")
        ); // preserved
    }

    // --- AlterSeating tests ---

    /// Build a tournament in Playing state with one round of 2 tables of 4
    fn tournament_with_round() -> JsonValue {
        let mut t = make_tournament();
        t["state"] = "Playing".into();
        t["players"] = json::array![
            { user_uid: "p1", state: "Playing", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Playing", payment_status: "Pending", toss: 0 },
            { user_uid: "p3", state: "Playing", payment_status: "Pending", toss: 0 },
            { user_uid: "p4", state: "Playing", payment_status: "Pending", toss: 0 },
            { user_uid: "p5", state: "Playing", payment_status: "Pending", toss: 0 },
            { user_uid: "p6", state: "Playing", payment_status: "Pending", toss: 0 },
            { user_uid: "p7", state: "Playing", payment_status: "Pending", toss: 0 },
            { user_uid: "p8", state: "Playing", payment_status: "Pending", toss: 0 },
        ];
        t["rounds"] = json::array![
            [
                {
                    seating: [
                        { player_uid: "p1", result: { gw: 1, vp: 2.0, tp: 48 }, judge_uid: "" },
                        { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 24 }, judge_uid: "" },
                        { player_uid: "p3", result: { gw: 0, vp: 0.5, tp: 12 }, judge_uid: "" },
                        { player_uid: "p4", result: { gw: 0, vp: 0.5, tp: 12 }, judge_uid: "" },
                    ],
                    state: "Finished",
                    override: json::Null,
                },
                {
                    seating: [
                        { player_uid: "p5", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                        { player_uid: "p6", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                        { player_uid: "p7", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                        { player_uid: "p8", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                    ],
                    state: "In Progress",
                    override: json::Null,
                },
            ]
        ];
        t
    }

    #[test]
    fn test_alter_seating_swap_within_same_table_preserves_results() {
        let tournament = tournament_with_round();
        // Swap p1 and p2 within table 0, keep table 1 unchanged
        let event = json::object! {
            type: "AlterSeating",
            round: 0,
            seating: [["p2", "p1", "p3", "p4"], ["p5", "p6", "p7", "p8"]],
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();

        // p2 stays in table 0 -> result preserved
        assert_eq!(
            updated["rounds"][0][0]["seating"][0]["player_uid"].as_str(),
            Some("p2")
        );
        assert_eq!(
            updated["rounds"][0][0]["seating"][0]["result"]["vp"].as_f64(),
            Some(1.0)
        );
        // p1 stays in table 0 -> result preserved
        assert_eq!(
            updated["rounds"][0][0]["seating"][1]["result"]["vp"].as_f64(),
            Some(2.0)
        );
    }

    #[test]
    fn test_alter_seating_cross_table_swap_resets_results() {
        let tournament = tournament_with_round();
        // Move p1 (table 0, has results) to table 1, move p5 (table 1) to table 0
        let event = json::object! {
            type: "AlterSeating",
            round: 0,
            seating: [["p5", "p2", "p3", "p4"], ["p1", "p6", "p7", "p8"]],
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();

        // p5 moved from table 1 to table 0 -> result reset
        assert_eq!(
            updated["rounds"][0][0]["seating"][0]["result"]["vp"].as_f64(),
            Some(0.0)
        );
        // p2 stayed in table 0 -> result preserved
        assert_eq!(
            updated["rounds"][0][0]["seating"][1]["result"]["vp"].as_f64(),
            Some(1.0)
        );
        // p1 moved from table 0 to table 1 -> result reset
        assert_eq!(
            updated["rounds"][0][1]["seating"][0]["result"]["vp"].as_f64(),
            Some(0.0)
        );
        // Table 0 now has mixed zero/non-zero results; table 1 has all zeros -> "In Progress"
        assert_eq!(
            updated["rounds"][0][1]["state"].as_str(),
            Some("In Progress")
        );
    }

    #[test]
    fn test_alter_seating_wrong_table_count_fails() {
        let tournament = tournament_with_round();
        // Provide 3 tables instead of 2
        let event = json::object! {
            type: "AlterSeating",
            round: 0,
            seating: [["p1", "p2", "p3", "p4"], ["p5", "p6"], ["p7", "p8"]],
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Table count mismatch"));
    }

    #[test]
    fn test_alter_seating_unknown_player_fails() {
        let tournament = tournament_with_round();
        let event = json::object! {
            type: "AlterSeating",
            round: 0,
            seating: [["p1", "p2", "p3", "UNKNOWN"], ["p5", "p6", "p7", "p8"]],
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("not found"));
    }

    #[test]
    fn test_alter_seating_requires_organizer() {
        let tournament = tournament_with_round();
        let event = json::object! {
            type: "AlterSeating",
            round: 0,
            seating: [["p1", "p2", "p3", "p4"], ["p5", "p6", "p7", "p8"]],
        };
        let actor = make_player("p1");
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("organizers"));
    }

    #[test]
    fn test_alter_seating_invalid_state_fails() {
        let mut tournament = tournament_with_round();
        tournament["state"] = "Registration".into();
        let event = json::object! {
            type: "AlterSeating",
            round: 0,
            seating: [["p1", "p2", "p3", "p4"], ["p5", "p6", "p7", "p8"]],
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Cannot alter seating"));
    }

    #[test]
    fn test_update_config_basic() {
        let tournament = make_tournament();
        let event = json::object! {
            type: "UpdateConfig",
            config: {
                name: "New Name",
                format: "V5",
                max_rounds: 4,
            },
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["name"].as_str(), Some("New Name"));
        assert_eq!(updated["format"].as_str(), Some("V5"));
        assert_eq!(updated["max_rounds"].as_usize(), Some(4));
    }

    #[test]
    fn test_update_config_null_country() {
        let mut tournament = make_tournament();
        tournament["country"] = "France".into();
        let event = json::object! {
            type: "UpdateConfig",
            config: {
                country: json::Null,
            },
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert!(updated["country"].is_null());
    }

    #[test]
    fn test_update_config_invalid_format() {
        let tournament = make_tournament();
        let event = json::object! {
            type: "UpdateConfig",
            config: { format: "Invalid" },
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Invalid format"));
    }

    #[test]
    fn test_update_config_max_rounds_too_low() {
        let mut tournament = tournament_with_round();
        // Finish the round so it counts as completed
        tournament["rounds"][0][0]["state"] = "Finished".into();
        tournament["rounds"][0][1]["state"] = "Finished".into();
        let event = json::object! {
            type: "UpdateConfig",
            config: { max_rounds: 0 },
        };
        let actor = make_organizer();
        // max_rounds=0 means unlimited, should succeed
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
    }

    #[test]
    fn test_update_config_non_organizer_fails() {
        let tournament = make_tournament();
        let event = json::object! {
            type: "UpdateConfig",
            config: { name: "Hacked" },
        };
        let actor = make_player("player-1");
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("organizers"));
    }

    #[test]
    fn test_update_config_empty_name_fails() {
        let tournament = make_tournament();
        let event = json::object! {
            type: "UpdateConfig",
            config: { name: "" },
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("name cannot be empty"));
    }

    #[test]
    fn test_update_config_timer_fields() {
        let tournament = make_tournament();
        let event = json::object! {
            type: "UpdateConfig",
            config: {
                round_time: 7200,
                finals_time: 9000,
                time_extension_policy: "clock_stop",
            },
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["round_time"].as_i64(), Some(7200));
        assert_eq!(updated["finals_time"].as_i64(), Some(9000));
        assert_eq!(
            updated["time_extension_policy"].as_str(),
            Some("clock_stop")
        );
    }

    #[test]
    fn test_update_config_invalid_extension_policy() {
        let tournament = make_tournament();
        let event = json::object! {
            type: "UpdateConfig",
            config: { time_extension_policy: "invalid" },
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .contains("Invalid time_extension_policy"));
    }

    #[test]
    fn test_update_config_partial_update() {
        let mut tournament = make_tournament();
        tournament["venue"] = "Old Venue".into();
        let event = json::object! {
            type: "UpdateConfig",
            config: { description: "New desc" },
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["description"].as_str(), Some("New desc"));
        // venue should remain unchanged
        assert_eq!(updated["venue"].as_str(), Some("Old Venue"));
    }

    #[test]
    fn test_update_config_league_uid_unauthorized() {
        let tournament = make_tournament();
        let event = json::object! {
            type: "UpdateConfig",
            config: { league_uid: "league-123" },
        };
        // Organizer without league access
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Only league organizers"));
    }

    #[test]
    fn test_update_config_league_uid_authorized() {
        let tournament = make_tournament();
        let event = json::object! {
            type: "UpdateConfig",
            config: { league_uid: "league-123" },
        };
        let actor = json::object! {
            uid: "organizer-1",
            roles: ["Prince"],
            is_organizer: true,
            can_organize_league_uids: ["league-123"],
        };
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["league_uid"].as_str(), Some("league-123"));
    }

    #[test]
    fn test_update_config_league_uid_ic_bypass() {
        let tournament = make_tournament();
        let event = json::object! {
            type: "UpdateConfig",
            config: { league_uid: "league-123" },
        };
        let actor = json::object! {
            uid: "ic-1",
            roles: ["IC"],
            is_organizer: true,
        };
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
    }

    #[test]
    fn test_update_config_league_uid_unlink_allowed() {
        let mut tournament = make_tournament();
        tournament["league_uid"] = "league-123".into();
        let event = json::object! {
            type: "UpdateConfig",
            config: { league_uid: json::Null },
        };
        // Even without league access, unlinking is allowed
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert!(updated["league_uid"].is_null());
    }

    #[test]
    fn test_checkin_auto_registers_unregistered_player() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![];

        let event = json::object! { type: "CheckIn", player_uid: "player-1" };
        let actor = make_player("player-1");

        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["players"].len(), 1);
        assert_eq!(
            updated["players"][0]["user_uid"].as_str(),
            Some("player-1")
        );
        assert_eq!(
            updated["players"][0]["state"].as_str(),
            Some("Checked-in")
        );
    }

    #[test]
    fn test_checkin_auto_register_blocked_by_dq() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![];

        let event = json::object! { type: "CheckIn", player_uid: "player-1" };
        let actor = make_player("player-1");
        let sanctions = r#"[{"user_uid":"player-1","level":"disqualification","lifted_at":null,"deleted_at":null}]"#;

        let raw = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
            sanctions,
            &no_decks(),
        );
        assert!(raw.is_err());
        assert!(raw.unwrap_err().contains("disqualification"));
    }

    #[test]
    fn test_checkin_auto_register_blocked_by_suspension() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![];

        let event = json::object! { type: "CheckIn", player_uid: "player-1" };
        let actor = make_player("player-1");
        let sanctions = r#"[{"user_uid":"player-1","level":"suspension","lifted_at":null,"deleted_at":null}]"#;

        let raw = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
            sanctions,
            &no_decks(),
        );
        assert!(raw.is_err());
        assert!(raw.unwrap_err().contains("suspended"));
    }

    // ================================================================
    // DeleteDeck tests
    // ================================================================

    #[test]
    fn test_delete_deck_success() {
        let tournament = tournament_with_player("Waiting");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "DeleteDeck",
            player_uid: "player-1",
            deck_index: json::Null,
            multideck: false,
        };
        let actor = make_player("player-1");
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, decks).unwrap();
        assert_eq!(deck_ops.len(), 1);
        assert_eq!(deck_ops[0]["op"].as_str(), Some("delete"));
    }

    #[test]
    fn test_delete_deck_auth_failure() {
        let tournament = tournament_with_player("Waiting");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "DeleteDeck",
            player_uid: "player-1",
            deck_index: json::Null,
            multideck: false,
        };
        let actor = make_player("other-player");
        let result = run_event_with_decks(&tournament, &event, &actor, decks);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("organizers or the player"));
    }

    #[test]
    fn test_delete_deck_playing_blocked() {
        let tournament = tournament_with_player("Playing");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "DeleteDeck",
            player_uid: "player-1",
            deck_index: json::Null,
            multideck: false,
        };
        let actor = make_player("player-1");
        let result = run_event_with_decks(&tournament, &event, &actor, decks);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("in progress"));
    }

    #[test]
    fn test_delete_deck_finished_blocked() {
        let tournament = tournament_with_player("Finished");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "DeleteDeck",
            player_uid: "player-1",
            deck_index: json::Null,
            multideck: false,
        };
        let actor = make_player("player-1");
        let result = run_event_with_decks(&tournament, &event, &actor, decks);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("finished"));
    }

    #[test]
    fn test_delete_deck_organizer_always() {
        let tournament = tournament_with_player("Playing");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "DeleteDeck",
            player_uid: "player-1",
            deck_index: json::Null,
            multideck: false,
        };
        let actor = make_organizer();
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, decks).unwrap();
        assert_eq!(deck_ops.len(), 1);
        assert_eq!(deck_ops[0]["op"].as_str(), Some("delete"));
    }

    // ================================================================
    // Multideck tests
    // ================================================================

    fn multideck_tournament(state: &str, rounds_played: usize) -> JsonValue {
        let mut t = make_tournament();
        t["state"] = state.into();
        t["multideck"] = true.into();
        t["players"] = json::array![
            { user_uid: "player-1", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];
        // Add dummy rounds to simulate played rounds
        let mut rounds = json::JsonValue::new_array();
        for _ in 0..rounds_played {
            let table = json::object! {
                seating: [{ player_uid: "player-1", result: { vp: 0 } }],
                state: "Finished",
            };
            let mut round = json::JsonValue::new_array();
            let _ = round.push(table);
            let _ = rounds.push(round);
        }
        t["rounds"] = rounds;
        t
    }

    #[test]
    fn test_multideck_upsert_round_0() {
        let tournament = multideck_tournament("Waiting", 0);
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "Round 1 Deck", author: "", comments: "", cards: {} },
            multideck: true,
        };
        let actor = make_player("player-1");
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, "[]").unwrap();
        assert_eq!(deck_ops.len(), 1);
        assert_eq!(deck_ops[0]["op"].as_str(), Some("upsert"));
        assert_eq!(deck_ops[0]["multideck"].as_bool(), Some(true));
    }

    #[test]
    fn test_multideck_upsert_round_1_playing() {
        // 1 round played, player has 1 deck -> new deck goes at index 1 (unlocked)
        let tournament = multideck_tournament("Playing", 1);
        let decks = r#"[{"user_uid": "player-1", "round": 0, "uid": "d0"}]"#;
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "Round 2 Deck", author: "", comments: "", cards: {} },
            multideck: true,
        };
        let actor = make_player("player-1");
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, decks).unwrap();
        assert_eq!(deck_ops.len(), 1);
        assert_eq!(deck_ops[0]["op"].as_str(), Some("upsert"));
    }

    #[test]
    fn test_multideck_upsert_locked_round_blocked() {
        // 1 round played, player has 0 decks -> new deck at index 0 (locked, round 0 already played)
        let tournament = multideck_tournament("Playing", 1);
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "Late Deck", author: "", comments: "", cards: {} },
            multideck: true,
        };
        let actor = make_player("player-1");
        let result = run_event_with_decks(&tournament, &event, &actor, "[]");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("already started"));
    }

    #[test]
    fn test_multideck_delete_unlocked() {
        // 1 round played, player has 2 decks -> delete index 1 (unlocked)
        let tournament = multideck_tournament("Playing", 1);
        let decks = r#"[{"user_uid": "player-1", "round": 0, "uid": "d0"}, {"user_uid": "player-1", "round": 1, "uid": "d1"}]"#;
        let event = json::object! {
            type: "DeleteDeck",
            player_uid: "player-1",
            deck_index: 1,
            multideck: true,
        };
        let actor = make_player("player-1");
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, decks).unwrap();
        assert_eq!(deck_ops.len(), 1);
        assert_eq!(deck_ops[0]["op"].as_str(), Some("delete"));
    }

    #[test]
    fn test_multideck_delete_locked_blocked() {
        // 1 round played, delete index 0 (locked) -> blocked
        let tournament = multideck_tournament("Playing", 1);
        let decks = r#"[{"user_uid": "player-1", "round": 0, "uid": "d0"}]"#;
        let event = json::object! {
            type: "DeleteDeck",
            player_uid: "player-1",
            deck_index: 0,
            multideck: true,
        };
        let actor = make_player("player-1");
        let result = run_event_with_decks(&tournament, &event, &actor, decks);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("already started"));
    }

    #[test]
    fn test_multideck_delete_requires_index() {
        // Multideck delete without deck_index during Playing -> error
        let tournament = multideck_tournament("Playing", 1);
        let decks = r#"[{"user_uid": "player-1", "round": 0, "uid": "d0"}]"#;
        let event = json::object! {
            type: "DeleteDeck",
            player_uid: "player-1",
            deck_index: json::Null,
            multideck: true,
        };
        let actor = make_player("player-1");
        let result = run_event_with_decks(&tournament, &event, &actor, decks);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("deck_index required"));
    }

    #[test]
    fn test_multideck_lifecycle() {
        // Upload deck at round 0, start round -> round 0 deck locked
        let mut tournament = multideck_tournament("Waiting", 0);
        // Add enough players for StartRound
        tournament["players"] = json::array![
            { user_uid: "p0", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p3", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];

        // Upload deck for p0 at round 0
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "p0",
            deck: { name: "Round 1 Deck", author: "", comments: "", cards: {} },
            multideck: true,
        };
        let actor = make_player("p0");
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, "[]").unwrap();
        assert_eq!(deck_ops.len(), 1);

        // Start round
        let start_event = json::parse(
            r#"{"type": "StartRound", "seating": [["p0","p1","p2","p3"]]}"#,
        ).unwrap();
        let org = make_organizer();
        let result = run_event(&tournament, &start_event, &org).unwrap();
        let updated = json::parse(&result).unwrap();
        assert_eq!(updated["state"].as_str(), Some("Playing"));
        assert_eq!(updated["rounds"].len(), 1);

        // Now try to delete p0's round 0 deck -> should be locked
        let delete_event = json::object! {
            type: "DeleteDeck",
            player_uid: "p0",
            deck_index: 0,
            multideck: true,
        };
        let actor_p0 = make_player("p0");
        let decks = r#"[{"user_uid": "p0", "round": 0, "uid": "d0"}]"#;
        let delete_result = run_event_with_decks(&updated, &delete_event, &actor_p0, decks);
        assert!(delete_result.is_err());
        assert!(delete_result.unwrap_err().contains("already started"));
    }
}
