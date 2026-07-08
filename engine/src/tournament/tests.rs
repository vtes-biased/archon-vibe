//! Tests for tournament engine.

use super::*;
use crate::error::EngineError;

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
) -> Result<String, EngineError> {
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
) -> Result<(String, JsonValue), EngineError> {
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
    assert!(result.unwrap_err().to_string().contains("VEKN ID"));

    // Also reject empty string
    let event2 = json::object! {
        type: "Register",
        user_uid: "player-1",
        vekn_id: "",
    };
    let result2 = run_event(&tournament, &event2, &actor);
    assert!(result2.is_err());
    assert!(result2.unwrap_err().to_string().contains("VEKN ID"));
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
    assert!(result.unwrap_err().to_string().contains("VEKN ID"));
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
    assert!(result.unwrap_err().to_string().contains("at least 4"));
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
fn test_start_round_computed_seating_is_deterministic() {
    // No submitted seating => the engine computes it. The seed is derived from
    // tournament uid + round, so running the same StartRound twice must yield
    // byte-identical tables (WASM/PyO3/offline/bot agree).
    let mut tournament = make_tournament();
    tournament["state"] = "Waiting".into();
    let mut players = json::array![];
    for i in 0..8 {
        players
            .push(json::object! {
                user_uid: format!("p{i}"),
                state: "Checked-in",
                payment_status: "Pending",
                toss: 0,
            })
            .unwrap();
    }
    tournament["players"] = players;

    let event = json::parse(r#"{"type": "StartRound"}"#).unwrap();
    let actor = make_organizer();

    let r1 = run_event(&tournament, &event, &actor).expect("StartRound 1");
    let r2 = run_event(&tournament, &event, &actor).expect("StartRound 2");
    let t1 = json::parse(&r1).unwrap();
    let t2 = json::parse(&r2).unwrap();
    assert_eq!(
        t1["rounds"][0].dump(),
        t2["rounds"][0].dump(),
        "computed seating must be reproducible for the same tournament+round"
    );
}

#[test]
fn test_standings_tie_order_is_deterministic() {
    // Four players finish fully tied (same gw/vp/tp/toss). Without the terminal
    // user_uid tiebreak they come out in nondeterministic HashMap order; assert
    // the order is stable across calls and sorted by user_uid ascending.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![json::array![json::object! {
        seating: [
            { player_uid: "pc", result: { gw: 0, vp: 1.0, tp: 24 } },
            { player_uid: "pa", result: { gw: 0, vp: 1.0, tp: 24 } },
            { player_uid: "pd", result: { gw: 0, vp: 1.0, tp: 24 } },
            { player_uid: "pb", result: { gw: 0, vp: 1.0, tp: 24 } },
        ],
    }]];
    tournament["players"] = json::array![
        { user_uid: "pa", toss: 0 },
        { user_uid: "pb", toss: 0 },
        { user_uid: "pc", toss: 0 },
        { user_uid: "pd", toss: 0 },
    ];
    let empty = json::array![];
    let s1 = super::standings::compute_preliminary_standings(&tournament, &empty);
    let s2 = super::standings::compute_preliminary_standings(&tournament, &empty);
    let order1: Vec<&str> = s1.iter().map(|s| s.user_uid.as_str()).collect();
    let order2: Vec<&str> = s2.iter().map(|s| s.user_uid.as_str()).collect();
    assert_eq!(order1, order2, "tie order must be stable across calls");
    assert_eq!(order1, vec!["pa", "pb", "pc", "pd"]);
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

    let event =
        json::parse(r#"{"type": "StartRound", "seating": [["p0","p1","p2","p3"]]}"#).unwrap();
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

// Self-organized rounds (#274): the player-authorized eligibility predicate. One test
// over the whole invariant — registration is the gate, the initiator must be seated, the
// abuse vectors (concurrent pod, non-participant, disabled) are rejected, and it works
// offline / with no per-player cap (open-rounds is the only prerequisite).
#[test]
fn test_self_organize_round_eligibility() {
    let mut t = make_tournament();
    t["state"] = "Waiting".into();
    t["online"] = true.into();
    t["self_organized_rounds"] = true.into();
    t["players"] = json::array![
        { user_uid: "p1", state: "Registered", payment_status: "Pending", toss: 0 },
        { user_uid: "p2", state: "Registered", payment_status: "Pending", toss: 0 },
        { user_uid: "p3", state: "Registered", payment_status: "Pending", toss: 0 },
        { user_uid: "p4", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p5", state: "Registered", payment_status: "Pending", toss: 0 },
        { user_uid: "p6", state: "Playing", payment_status: "Pending", toss: 0 },
    ];
    let p1 = make_player("p1");
    let pod =
        json::parse(r#"{"type":"SelfOrganizeRound","player_uids":["p1","p2","p3","p4"]}"#).unwrap();

    // Happy path: a registered initiator seats a 4-player pod. Engine assigns one table,
    // stamps provenance, seats only the chosen players, and leaves p5 available.
    let out = json::parse(&run_event(&t, &pod, &p1).expect("self-organize")).unwrap();
    assert_eq!(out["rounds"].len(), 1);
    assert_eq!(out["rounds"][0].len(), 1, "exactly one table");
    assert_eq!(out["rounds"][0][0]["organized_by"].as_str(), Some("p1"));
    assert_eq!(out["state"].as_str(), Some("Playing"));
    let st = |o: &JsonValue, uid: &str| {
        o["players"]
            .members()
            .find(|p| p["user_uid"].as_str() == Some(uid))
            .unwrap()["state"]
            .as_str()
            .unwrap()
            .to_string()
    };
    assert_eq!(st(&out, "p1"), "Playing");
    assert_eq!(st(&out, "p4"), "Playing");
    assert_eq!(
        st(&out, "p5"),
        "Registered",
        "unselected player stays available"
    );

    // Initiator must seat themselves.
    let no_self =
        json::parse(r#"{"type":"SelfOrganizeRound","player_uids":["p2","p3","p4","p5"]}"#).unwrap();
    assert!(matches!(
        run_event(&t, &no_self, &p1),
        Err(EngineError::SelfOrganizeNotSeated)
    ));

    // Concurrent-pod guard: a Playing player can't be pulled into a second pod.
    let busy =
        json::parse(r#"{"type":"SelfOrganizeRound","player_uids":["p1","p2","p3","p6"]}"#).unwrap();
    assert!(matches!(
        run_event(&t, &busy, &p1),
        Err(EngineError::SelfOrganizeIneligible { .. })
    ));

    // Registration is the gate: a non-participant can't be seated.
    let ghost =
        json::parse(r#"{"type":"SelfOrganizeRound","player_uids":["p1","p2","p3","ghost"]}"#)
            .unwrap();
    assert!(matches!(
        run_event(&t, &ghost, &p1),
        Err(EngineError::NotRegistered)
    ));

    // Disabled flag rejects the whole path.
    let mut off = t.clone();
    off["self_organized_rounds"] = false.into();
    assert!(matches!(
        run_event(&off, &pod, &p1),
        Err(EngineError::SelfOrganizeDisabled)
    ));

    // No online or per-player-cap prerequisite: an offline, uncapped tournament still
    // seats a self-organized pod (open-rounds + the flag are the only requirements).
    let mut offline = t.clone();
    offline["online"] = false.into();
    offline["max_rounds"] = 0.into();
    assert!(
        run_event(&offline, &pod, &p1).is_ok(),
        "self-organize allowed offline with no cap"
    );
}

// Cancelling a NON-last round (parallel rounds, #274) soft-cancels in place: the slot is
// preserved (index-stable for deck.round / SA round_number), the round drops out of the cap
// and standings, its players are released, and other in-progress rounds are untouched.
#[test]
fn test_cancel_round_soft_cancels_non_last() {
    let mut t = make_tournament();
    t["state"] = "Playing".into();
    t["online"] = true.into();
    t["max_rounds"] = 1.into();
    t["players"] = json::array![
        { user_uid: "p1", state: "Completed", payment_status: "Pending", toss: 0 },
        { user_uid: "p2", state: "Completed", payment_status: "Pending", toss: 0 },
        { user_uid: "p3", state: "Completed", payment_status: "Pending", toss: 0 },
        { user_uid: "p4", state: "Completed", payment_status: "Pending", toss: 0 },
        { user_uid: "q1", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q2", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q3", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q4", state: "Playing", payment_status: "Pending", toss: 0 },
    ];
    // Two parallel rounds: round 0 finished (p-pod, which capped them at max_rounds=1),
    // round 1 still in progress (q-pod).
    t["rounds"] = json::array![
        [ { seating: [
            { player_uid: "p1", result: { gw: 0, vp: 1.0, tp: 0 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 0 } },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 0 } },
            { player_uid: "p4", result: { gw: 0, vp: 1.0, tp: 0 } },
        ], state: "Finished" } ],
        [ { seating: [
            { player_uid: "q1", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "q2", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "q3", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "q4", result: { gw: 0, vp: 0.0, tp: 0 } },
        ], state: "In Progress" } ],
    ];

    let ev = json::object! { type: "CancelRound", round: 0 };
    let out = json::parse(&run_event(&t, &ev, &make_organizer()).expect("cancel")).unwrap();

    assert_eq!(out["rounds"].len(), 2, "slot preserved, not removed");
    assert_eq!(out["rounds"][0][0]["state"].as_str(), Some("Cancelled"));
    assert_eq!(
        out["rounds"][1][0]["state"].as_str(),
        Some("In Progress"),
        "the other in-progress round is untouched"
    );
    assert_eq!(
        out["state"].as_str(),
        Some("Playing"),
        "stay Playing — round 1 live"
    );

    let st = |o: &JsonValue, uid: &str| {
        o["players"]
            .members()
            .find(|p| p["user_uid"].as_str() == Some(uid))
            .unwrap()["state"]
            .as_str()
            .unwrap()
            .to_string()
    };
    // The cancelled round no longer counts toward the cap, so its capped players re-arm.
    assert_eq!(st(&out, "p1"), "Checked-in");
    // The live round's players keep playing.
    assert_eq!(st(&out, "q1"), "Playing");
    // A player seated only in the cancelled round drops out of standings entirely.
    assert!(
        !out["standings"]
            .members()
            .any(|s| s["user_uid"].as_str() == Some("p3")),
        "cancelled round contributes no standings"
    );
}

// RestoreRound un-voids a soft-cancelled non-last round (#295). The whole point of the
// feature: a round cancelled by mistake must come back with its retained scores re-derived.
// This is the inverse of test_cancel_round_soft_cancels_non_last — cancel round 0, then
// restore it, and assert the engine flips the table back to Finished (the table was complete
// + valid when cancelled), re-arms its capped players to Completed (round re-derived fully
// Finished, players back at their cap), and leaves the still-live round 1 untouched.
#[test]
fn test_restore_round_rederives_finished_from_retained_scores() {
    let mut t = make_tournament();
    t["state"] = "Playing".into();
    t["online"] = true.into();
    t["max_rounds"] = 1.into();
    t["players"] = json::array![
        { user_uid: "p1", state: "Completed", payment_status: "Pending", toss: 0 },
        { user_uid: "p2", state: "Completed", payment_status: "Pending", toss: 0 },
        { user_uid: "p3", state: "Completed", payment_status: "Pending", toss: 0 },
        { user_uid: "p4", state: "Completed", payment_status: "Pending", toss: 0 },
        { user_uid: "q1", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q2", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q3", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q4", state: "Playing", payment_status: "Pending", toss: 0 },
    ];
    // Same fixture as the cancel test: round 0 was a finished p-pod (single oust, sum == 4),
    // round 1 a live q-pod. Engine-valid VP vectors.
    t["rounds"] = json::array![
        [ { seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.0, tp: 0 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 0 } },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 0 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 0 } },
        ], state: "Finished" } ],
        [ { seating: [
            { player_uid: "q1", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "q2", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "q3", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "q4", result: { gw: 0, vp: 0.0, tp: 0 } },
        ], state: "In Progress" } ],
    ];

    // Soft-cancel round 0 through the real engine, then restore it through the real engine —
    // round-trip on the shipped artifact, not a hand-built Cancelled fixture.
    let cancelled = json::parse(
        &run_event(
            &t,
            &json::object! { type: "CancelRound", round: 0 },
            &make_organizer(),
        )
        .expect("cancel"),
    )
    .unwrap();
    assert_eq!(
        cancelled["rounds"][0][0]["state"].as_str(),
        Some("Cancelled"),
        "precondition: round 0 is soft-cancelled"
    );

    let out = json::parse(
        &run_event(
            &cancelled,
            &json::object! { type: "RestoreRound", round: 0 },
            &make_organizer(),
        )
        .expect("restore"),
    )
    .unwrap();

    // The retained scores were a complete, valid finished table, so re-derivation -> Finished.
    assert_eq!(
        out["rounds"][0][0]["state"].as_str(),
        Some("Finished"),
        "restored round re-derives to Finished from retained scores"
    );
    assert_eq!(out["rounds"].len(), 2, "slot still index-stable");
    assert_eq!(
        out["rounds"][1][0]["state"].as_str(),
        Some("In Progress"),
        "the live round is untouched by restore"
    );

    let st = |o: &JsonValue, uid: &str| {
        o["players"]
            .members()
            .find(|p| p["user_uid"].as_str() == Some(uid))
            .unwrap()["state"]
            .as_str()
            .unwrap()
            .to_string()
    };
    // p-pod players: now back at their cap (max_rounds=1, this round counts again) on a fully-
    // Finished round -> Completed, mirroring FinishRound. Cancel had released them to Checked-in.
    assert_eq!(st(&out, "p1"), "Completed");
    assert_eq!(st(&out, "p4"), "Completed");
    // The live round's players are unaffected.
    assert_eq!(st(&out, "q1"), "Playing");
    // And the restored round contributes standings again.
    assert!(
        out["standings"]
            .members()
            .any(|s| s["user_uid"].as_str() == Some("p3")),
        "restored round contributes standings again"
    );
}

// All-or-nothing (#295): a round restores exactly as it was saved, or not at all. If a player
// seated in the cancelled round can no longer be reinstated — dropped out (Finished) or
// disqualified, or (open rounds) already at their round cap via OTHER rounds — RestoreRound
// rejects the whole operation with a clear reason rather than silently leaving them out. (The
// count-before-flip ordering for the cap case is exercised by the success test above, where the
// restored round is itself what brings its players to cap; here a dropped player blocks restore.)
#[test]
fn test_restore_round_rejects_non_reinstatable_player() {
    let mut t = make_tournament();
    t["state"] = "Playing".into();
    t["online"] = true.into();
    // Two parallel rounds: round 0 cancelled (retained finished scores), round 1 live. One round-0
    // player (p4) has since dropped out (state Finished) -> restore must be rejected, not partial.
    t["players"] = json::array![
        { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p2", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p3", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p4", state: "Finished", payment_status: "Pending", toss: 0 },
        { user_uid: "q1", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q2", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q3", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q4", state: "Playing", payment_status: "Pending", toss: 0 },
    ];
    t["rounds"] = json::array![
        [ { seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.0, tp: 0 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 0 } },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 0 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 0 } },
        ], state: "Cancelled" } ],
        [ { seating: [
            { player_uid: "q1", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "q2", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "q3", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "q4", result: { gw: 0, vp: 0.0, tp: 0 } },
        ], state: "In Progress" } ],
    ];

    let result = run_event(
        &t,
        &json::object! { type: "RestoreRound", round: 0 },
        &make_organizer(),
    );
    assert!(
        result.is_err(),
        "restore must be rejected when a seated player has dropped out"
    );
    let msg = result.unwrap_err().to_string();
    assert!(
        msg.contains("restored"),
        "rejection explains why, got: {msg}"
    );
}

#[test]
fn test_non_organizer_cannot_open_registration() {
    let tournament = make_tournament();
    let event = json::object! { type: "OpenRegistration" };
    let actor = make_player("random-player");

    let result = run_event(&tournament, &event, &actor);

    assert!(result.is_err());
    assert!(result.unwrap_err().to_string().contains("organizers"));
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
    assert!(result.unwrap_err().to_string().contains("in progress"));
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
    assert!(result.unwrap_err().to_string().contains("finished"));
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
    assert!(result.unwrap_err().to_string().contains("in progress"));
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
    assert!(result
        .unwrap_err()
        .to_string()
        .contains("Invalid payment status"));
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
    assert!(result.unwrap_err().to_string().contains("organizers"));
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
fn test_tp_with_sa_reranks_table() {
    // JG v2 1.1.3 Example 2: A sweeps a 5-player table (5VP); B/C/D/E at 0VP.
    // E gets SA -> adjusted -1, dropping below the other 0VP players.
    // A=60 (1st), B/C/D tie 2nd-4th = (48+36+24)/3 = 36 each, E=12 (5th).
    let vps = vec![5.0, 0.0, 0.0, 0.0, 0.0];
    let adj = vec![0.0, 0.0, 0.0, 0.0, -1.0];
    let tps = compute_tp(5, &vps, &adj);
    assert_eq!(tps, vec![60.0, 36.0, 36.0, 36.0, 12.0]);

    // Without the penalty all four 0VP players tie 2nd-5th = (48+36+24+12)/4 = 30.
    let flat = compute_tp(5, &vps, &[0.0; 5]);
    assert_eq!(flat, vec![60.0, 30.0, 30.0, 30.0, 30.0]);
}

#[test]
fn test_standings_vp_under_sa_goes_negative() {
    // A 4-player table (VPs sum to 4). p1 has 2 raw VP, p2 has 0; both carry an SA
    // on round 0. gw is 0 for everyone (p1's adjusted 1.0 < 2.0, so no GW — the
    // engine would store exactly this). Standings VP: p1 -> 2-1 = 1.0, p2 -> 0-1 = -1.0.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![json::array![json::object! {
        seating: [
            { player_uid: "p1", result: { gw: 0, vp: 2.0, tp: 48 } },
            { player_uid: "p2", result: { gw: 0, vp: 0.0, tp: 12 } },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 } },
            { player_uid: "p4", result: { gw: 0, vp: 1.0, tp: 24 } },
        ],
    }]];
    tournament["players"] = json::array![
        { user_uid: "p1", toss: 0 },
        { user_uid: "p2", toss: 0 },
        { user_uid: "p3", toss: 0 },
        { user_uid: "p4", toss: 0 },
    ];
    let sanctions = json::array![
        { user_uid: "p1", level: "standings_adjustment", round_number: 0, lifted_at: json::Null, deleted_at: json::Null },
        { user_uid: "p2", level: "standings_adjustment", round_number: 0, lifted_at: json::Null, deleted_at: json::Null },
    ];
    let standings = super::standings::compute_preliminary_standings(&tournament, &sanctions);
    let vp_of = |uid: &str| {
        standings
            .iter()
            .find(|s| s.user_uid == uid)
            .unwrap_or_else(|| panic!("{uid} missing"))
            .vp
    };
    assert_eq!(vp_of("p1"), 1.0, "raw 2 VP minus full 1.0 SA");
    assert_eq!(
        vp_of("p2"),
        -1.0,
        "raw 0 VP minus full 1.0 SA goes negative"
    );
}

#[test]
fn test_dq_player_zeroed_and_sorted_last_opponents_unaffected() {
    // p2 is disqualified. Their own gw/vp/tp are zeroed and they sort last, but
    // their seat is left intact so p1 still earns the table GW and keeps its VP.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![json::array![json::object! {
        seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.0, tp: 60 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 48 } },
            { player_uid: "p3", result: { gw: 0, vp: 0.5, tp: 36 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.5, tp: 24 } },
        ],
    }]];
    tournament["players"] = json::array![
        { user_uid: "p1", toss: 0 },
        { user_uid: "p2", toss: 0, state: "Disqualified" },
        { user_uid: "p3", toss: 0 },
        { user_uid: "p4", toss: 0 },
    ];
    let empty = json::array![];
    let standings = super::standings::compute_preliminary_standings(&tournament, &empty);
    let p2 = standings.iter().find(|s| s.user_uid == "p2").unwrap();
    assert_eq!(
        (p2.gw, p2.vp, p2.tp),
        (0.0, 0.0, 0.0),
        "DQ'd player forfeits score"
    );
    assert!(p2.disqualified);
    assert_eq!(
        standings.last().unwrap().user_uid,
        "p2",
        "DQ'd player sorts last"
    );

    let p1 = standings.iter().find(|s| s.user_uid == "p1").unwrap();
    assert_eq!(
        (p1.gw, p1.vp),
        (1.0, 2.0),
        "opponent keeps GW + VP earned vs the DQ'd seat"
    );

    // Rating VP/GW: zero for the DQ'd player, unchanged for the opponent.
    assert_eq!(
        super::compute_rating_vp_gw(&tournament, &empty, "p2"),
        (0.0, 0.0)
    );
    assert_eq!(
        super::compute_rating_vp_gw(&tournament, &empty, "p1"),
        (2.0, 1.0)
    );

    // An active DQ *sanction* alone (no player state) is also honored.
    let sanctions = json::array![
        { user_uid: "p1", level: "disqualification", round_number: 0, lifted_at: json::Null, deleted_at: json::Null },
    ];
    assert_eq!(
        super::compute_rating_vp_gw(&tournament, &sanctions, "p1"),
        (0.0, 0.0)
    );
}

#[test]
fn test_proxy_kept_not_zeroed_sorted_last_opponents_and_rating_unaffected() {
    // p2 is a proxy (non_competing: a non-competing official stood in). The KEY
    // divergence from DQ: p2 keeps its own gw/vp/tp (NOT zeroed) yet sorts last
    // and earns no rating. Opponents keep what they scored against the seat.
    // Guards the shared DQ/proxy path against a refactor that starts zeroing the
    // proxy score or stops excluding it from rank/rating.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![json::array![json::object! {
        seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.0, tp: 60 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 48 } },
            { player_uid: "p3", result: { gw: 0, vp: 0.5, tp: 36 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.5, tp: 24 } },
        ],
    }]];
    tournament["players"] = json::array![
        { user_uid: "p1", toss: 0 },
        { user_uid: "p2", toss: 0, non_competing: true },
        { user_uid: "p3", toss: 0 },
        { user_uid: "p4", toss: 0 },
    ];
    let empty = json::array![];
    let standings = super::standings::compute_preliminary_standings(&tournament, &empty);
    let p2 = standings.iter().find(|s| s.user_uid == "p2").unwrap();
    assert!(p2.non_competing);
    assert_eq!(
        (p2.gw, p2.vp, p2.tp),
        (0.0, 1.0, 48.0),
        "proxy KEEPS its score (unlike DQ which zeroes)"
    );
    assert_eq!(
        standings.last().unwrap().user_uid,
        "p2",
        "proxy sorts last despite a non-zero score"
    );

    let p1 = standings.iter().find(|s| s.user_uid == "p1").unwrap();
    assert_eq!(
        (p1.gw, p1.vp),
        (1.0, 2.0),
        "opponent keeps GW + VP earned vs the proxy seat"
    );

    // Rating: proxy earns nothing; opponent unchanged.
    assert_eq!(
        super::compute_rating_vp_gw(&tournament, &empty, "p2"),
        (0.0, 0.0),
        "proxy earns no rating"
    );
    assert_eq!(
        super::compute_rating_vp_gw(&tournament, &empty, "p1"),
        (2.0, 1.0)
    );
}

#[test]
fn test_rating_vp_gw_includes_finals_and_full_sa() {
    // Rating recomputes prelim GW from raw VPs + sanctions and adds the stored
    // finals GW. p1: round0 2.5VP (table-high -> GW), round1 0VP with an SA (-1, so
    // no GW), finals 3VP/1GW (winner). VP = 2.5 + 0 + 3 - 1 = 4.5; GW = 1 + 0 + 1.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![
        json::array![json::object! {
            seating: [
                { player_uid: "p1", result: { gw: 1, vp: 2.5, tp: 60 } },
                { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 48 } },
                { player_uid: "p3", result: { gw: 0, vp: 0.5, tp: 36 } },
                { player_uid: "p4", result: { gw: 0, vp: 0.5, tp: 24 } },
                { player_uid: "p5", result: { gw: 0, vp: 0.5, tp: 12 } },
            ],
        }],
        json::array![json::object! {
            seating: [
                { player_uid: "p1", result: { gw: 0, vp: 0.0, tp: 12 } },
                { player_uid: "p2", result: { gw: 0, vp: 2.0, tp: 60 } },
                { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 } },
                { player_uid: "p4", result: { gw: 0, vp: 1.0, tp: 36 } },
                { player_uid: "p5", result: { gw: 0, vp: 1.0, tp: 36 } },
            ],
        }],
    ];
    tournament["finals"] = json::object! {
        seating: [
            { player_uid: "p1", result: { gw: 1, vp: 3.0, tp: 60 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 48 } },
            { player_uid: "p3", result: { gw: 0, vp: 0.5, tp: 36 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.5, tp: 24 } },
            { player_uid: "p5", result: { gw: 0, vp: 0.0, tp: 12 } },
        ],
    };
    let sanctions = json::array![
        { user_uid: "p1", level: "standings_adjustment", round_number: 1, lifted_at: json::Null, deleted_at: json::Null },
    ];
    let (vp, gw) = super::compute_rating_vp_gw(&tournament, &sanctions, "p1");
    assert_eq!(vp, 4.5, "prelim + finals VP minus full 1.0 SA");
    assert_eq!(gw, 2.0, "round0 GW (recomputed) + finals GW (stored)");
}

#[test]
fn test_rating_vp_gw_reads_standings_when_no_rounds() {
    // VEKN-synced tournament: no rounds/finals -> read the player's standings row.
    // An SA referencing a (nonexistent) round must not double-penalize the synced VP.
    let mut tournament = make_tournament();
    tournament["standings"] =
        json::array![json::object! { user_uid: "p1", gw: 1.0, vp: 4.0, tp: 120 },];
    let sanctions = json::array![
        { user_uid: "p1", level: "standings_adjustment", round_number: 0, lifted_at: json::Null, deleted_at: json::Null },
    ];
    let (vp, gw) = super::compute_rating_vp_gw(&tournament, &sanctions, "p1");
    assert_eq!(vp, 4.0, "synced standings VP used as-is");
    assert_eq!(gw, 1.0);
}

#[test]
fn test_rating_vp_gw_credits_no_final_winner() {
    // NO-final VEKN import: rounds AND finals both absent, but `winner` is set, so
    // the tournament-win GW (+1) is credited from the winner field (no finals table
    // recorded it). Matches vekn.net rtp (a no-final winner with prelim gw1 rates as
    // gw2). A non-winner in the same import gets no bonus. The inert side
    // (winner=="", native today) is pinned by the test above — keep this pair in
    // sync. Guards the #340 rating gate: import totals must stay unchanged once the
    // winner's +1 moved out of the folded standings and into this rule.
    let mut tournament = make_tournament();
    tournament["winner"] = "p1".into();
    tournament["standings"] = json::array![
        json::object! { user_uid: "p1", gw: 1.0, vp: 3.0, tp: 90 },
        json::object! { user_uid: "p2", gw: 0.0, vp: 2.0, tp: 60 },
    ];
    let empty = json::array![];
    assert_eq!(
        super::compute_rating_vp_gw(&tournament, &empty, "p1"),
        (3.0, 2.0),
        "no-final winner: prelim GW 1 + tournament-win GW 1; VP unchanged"
    );
    assert_eq!(
        super::compute_rating_vp_gw(&tournament, &empty, "p2"),
        (2.0, 0.0),
        "non-winner in a no-final import gets no tournament-win bonus"
    );
}

#[test]
fn test_standings_vp_sa_ignores_lifted_redirects_unplayed_round() {
    // A lifted SA must not penalize. An active SA whose stored round p1 never
    // played (round 1 here — only round 0 exists) is NOT deferred (JG v2 §1.1.3:
    // never a future round): it redirects to p1's most-recently-seated round
    // (round 0) and applies. Net: -1 (the lifted one is ignored), so 1.5 -> 0.5.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![json::array![json::object! {
        seating: [
            { player_uid: "p1", result: { gw: 0, vp: 1.5, tp: 36 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.5, tp: 36 } },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.5, tp: 12 } },
            { player_uid: "p5", result: { gw: 0, vp: 0.5, tp: 12 } },
        ],
    }]];
    tournament["players"] = json::array![
        { user_uid: "p1", toss: 0 },
        { user_uid: "p2", toss: 0 },
        { user_uid: "p3", toss: 0 },
        { user_uid: "p4", toss: 0 },
        { user_uid: "p5", toss: 0 },
    ];
    let sanctions = json::array![
        { user_uid: "p1", level: "standings_adjustment", round_number: 0, lifted_at: "2025-01-01T00:00:00Z", deleted_at: json::Null },
        { user_uid: "p1", level: "standings_adjustment", round_number: 1, lifted_at: json::Null, deleted_at: json::Null },
    ];
    let standings = super::standings::compute_preliminary_standings(&tournament, &sanctions);
    let p1 = standings.iter().find(|s| s.user_uid == "p1").unwrap();
    assert_eq!(
        p1.vp, 0.5,
        "lifted SA ignored; unplayed-round SA redirects to round 0 (-1)"
    );
}

#[test]
fn test_standings_sa_redirects_to_most_recent_seated_round() {
    // p1 plays round 0 only (not seated in round 1). An SA stored on round 1 — a
    // round p1 never played — must redirect to p1's most-recently-seated round
    // (round 0), and BOTH consumers must agree there. Round 0: p1's raw 2.5 VP
    // would take the GW (>=2, strictly highest); the redirected -1 drops adjusted
    // VP to 1.5, removing the GW. If the SA had instead deferred or landed on the
    // unplayed round 1, p1 would keep 2.5 VP and the GW.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![
        json::array![json::object! {
            seating: [
                { player_uid: "p1", result: { gw: 1, vp: 2.5, tp: 60 } },
                { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 48 } },
                { player_uid: "p3", result: { gw: 0, vp: 0.5, tp: 24 } },
                { player_uid: "p4", result: { gw: 0, vp: 0.5, tp: 24 } },
                { player_uid: "p5", result: { gw: 0, vp: 0.5, tp: 24 } },
            ],
        }],
        json::array![json::object! {
            seating: [
                { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 24 } },
                { player_uid: "p3", result: { gw: 1, vp: 2.0, tp: 60 } },
                { player_uid: "p4", result: { gw: 0, vp: 1.0, tp: 24 } },
                { player_uid: "p5", result: { gw: 0, vp: 0.0, tp: 12 } },
            ],
        }],
    ];
    tournament["players"] = json::array![
        { user_uid: "p1", toss: 0 },
        { user_uid: "p2", toss: 0 },
        { user_uid: "p3", toss: 0 },
        { user_uid: "p4", toss: 0 },
        { user_uid: "p5", toss: 0 },
    ];
    let sanctions = json::array![
        { user_uid: "p1", level: "standings_adjustment", round_number: 1, lifted_at: json::Null, deleted_at: json::Null },
    ];
    let standings = super::standings::compute_preliminary_standings(&tournament, &sanctions);
    let p1 = standings.iter().find(|s| s.user_uid == "p1").unwrap();
    assert_eq!(p1.vp, 1.5, "raw 2.5 - SA redirected onto round 0");
    assert_eq!(
        p1.gw, 0.0,
        "redirected -1 lands on round 0: adjusted 1.5 (<2) removes the GW"
    );
}

#[test]
fn test_rating_vp_gw_sa_never_lands_on_finals() {
    // An SA can never penalize the finals table. p1 plays one prelim round and the
    // finals; the SA's stored round_number points at the finals slot (index 1 ==
    // rounds_len), but the resolver only scans prelim rounds, so it redirects to
    // p1's last prelim round (round 0). Finals VP/GW are read from the stored seat,
    // untouched. VP = prelim 2.0 + finals 3.0 - 1.0 SA = 4.0; GW = 0 (round 0
    // recomputed: adjusted 1.0 < 2) + 1 (finals, stored) = 1.0.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![json::array![json::object! {
        seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.0, tp: 60 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 36 } },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.5, tp: 24 } },
            { player_uid: "p5", result: { gw: 0, vp: 0.5, tp: 12 } },
        ],
    }]];
    tournament["finals"] = json::object! {
        seating: [
            { player_uid: "p1", result: { gw: 1, vp: 3.0, tp: 60 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 48 } },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 24 } },
            { player_uid: "p5", result: { gw: 0, vp: 0.0, tp: 12 } },
        ],
    };
    let sanctions = json::array![
        { user_uid: "p1", level: "standings_adjustment", round_number: 1, lifted_at: json::Null, deleted_at: json::Null },
    ];
    let (vp, gw) = super::compute_rating_vp_gw(&tournament, &sanctions, "p1");
    assert_eq!(
        vp, 4.0,
        "prelim 2.0 + finals 3.0 - 1.0 SA (redirected to prelim)"
    );
    assert_eq!(
        gw, 1.0,
        "round 0 GW removed by SA; finals GW (stored) intact"
    );
}

#[test]
fn test_standings_recompute_picks_up_late_sa() {
    // The round was scored BEFORE the SA: p1's seat still stores the as-scored gw=1
    // and tp=60. An SA is then issued on that round for p1, dropping adjusted VP to
    // 1.5 (< 2.0). Standings must recompute from raw VP + the SA — p1 loses the GW
    // and the table re-ranks TP — despite the stale stored seat values.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![json::array![json::object! {
        seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.5, tp: 60 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 48 } },
            { player_uid: "p3", result: { gw: 0, vp: 0.5, tp: 24 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.5, tp: 24 } },
            { player_uid: "p5", result: { gw: 0, vp: 0.5, tp: 24 } },
        ],
    }]];
    tournament["players"] = json::array![
        { user_uid: "p1", toss: 0 },
        { user_uid: "p2", toss: 0 },
        { user_uid: "p3", toss: 0 },
        { user_uid: "p4", toss: 0 },
        { user_uid: "p5", toss: 0 },
    ];
    let sanctions = json::array![
        { user_uid: "p1", level: "standings_adjustment", round_number: 0, lifted_at: json::Null, deleted_at: json::Null },
    ];
    let standings = super::standings::compute_preliminary_standings(&tournament, &sanctions);
    let get = |uid: &str| {
        standings
            .iter()
            .find(|s| s.user_uid == uid)
            .unwrap_or_else(|| panic!("{uid} missing"))
    };
    // Adjusted VPs: p1=1.5, p2=1.0, p3=p4=p5=0.5.
    assert_eq!(
        get("p1").gw,
        0.0,
        "late SA -> adjusted 1.5 (<2): GW removed"
    );
    assert_eq!(get("p1").vp, 1.5, "raw 2.5 - full 1.0 SA");
    assert_eq!(
        get("p1").tp,
        60.0,
        "p1 still ranks 1st on adjusted VP -> 60 TP"
    );
    assert_eq!(get("p2").tp, 48.0, "p2 2nd -> 48 TP");
    // p3/p4/p5 tie 3rd-5th on adjusted 0.5 -> (36+24+12)/3 = 24 each.
    assert_eq!(get("p3").tp, 24.0);
}

// An SA whose stored round gets soft-cancelled must penalize VP and the GW/TP cascade on the
// SAME surviving round — never diverge. The bug (#472): `resolve_sa_effective_rounds` counted a
// seat in a Cancelled table, so the SA parked on the cancelled round; `sa_vp_penalty` (applied
// unconditionally) still took VP -1, but the GW/TP loop `continue`s past Cancelled tables, so the
// cascade never got the -1 — VP was penalized while the game win was silently kept, corrupting the
// standings/ratings pushed to VEKN. Fix: `seated_in` skips Cancelled, redirecting the SA to the
// player's most-recent non-cancelled round (here round 1, the in-progress "current game" of JG v2
// §1.1.3), so both consumers land there. Reach Cancelled through the real engine (CancelRound a
// non-last round, which soft-cancels in place and keeps the round-0 seating that tagged the SA),
// not a hand-built fixture. `gw` is the pre/post witness: pre-fix the SA sat on the cancelled
// round 0, leaving round 1 unadjusted → p1's raw 2.5 keeps the GW (>= 2.0, JG threshold); post-fix
// the -1 lands on round 1 → adjusted 1.5 (< 2.0) removes it. `vp` is 1.5 either way (documents the
// VP side; it is `gw` that flips), so this asserts the two now AGREE on the surviving round.
#[test]
fn test_sa_on_soft_cancelled_round_penalizes_vp_and_gw_together() {
    let mut t = make_tournament();
    t["state"] = "Playing".into();
    // Sequential rounds, same field: round 0 finished (later soft-cancelled), round 1 the live
    // "current game". p1..p5 are seated in both, so the SA tagged on round 0 has a surviving
    // non-cancelled round to redirect onto. Distinct toss for deterministic ranking.
    t["players"] = json::array![
        { user_uid: "p1", state: "Playing", payment_status: "Pending", toss: 5 },
        { user_uid: "p2", state: "Playing", payment_status: "Pending", toss: 4 },
        { user_uid: "p3", state: "Playing", payment_status: "Pending", toss: 3 },
        { user_uid: "p4", state: "Playing", payment_status: "Pending", toss: 2 },
        { user_uid: "p5", state: "Playing", payment_status: "Pending", toss: 1 },
    ];
    // Both tables single-oust, VP sum == 5 (engine-valid). p1 raw 2.5 takes the GW at 0 adjustment.
    t["rounds"] = json::array![
        [ { seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.5, tp: 60 }, judge_uid: "" },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 48 }, judge_uid: "" },
            { player_uid: "p3", result: { gw: 0, vp: 0.5, tp: 24 }, judge_uid: "" },
            { player_uid: "p4", result: { gw: 0, vp: 0.5, tp: 24 }, judge_uid: "" },
            { player_uid: "p5", result: { gw: 0, vp: 0.5, tp: 24 }, judge_uid: "" },
        ], state: "Finished", override: json::Null } ],
        [ { seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.5, tp: 60 }, judge_uid: "" },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 48 }, judge_uid: "" },
            { player_uid: "p3", result: { gw: 0, vp: 0.5, tp: 24 }, judge_uid: "" },
            { player_uid: "p4", result: { gw: 0, vp: 0.5, tp: 24 }, judge_uid: "" },
            { player_uid: "p5", result: { gw: 0, vp: 0.5, tp: 24 }, judge_uid: "" },
        ], state: "In Progress", override: json::Null } ],
    ];

    // Soft-cancel round 0 through the real engine: round 1 stays live so the tournament stays
    // Playing, round 0's tables flip to Cancelled with their seating intact.
    let cancelled = json::parse(
        &run_event(
            &t,
            &json::object! { type: "CancelRound", round: 0 },
            &make_organizer(),
        )
        .expect("cancel"),
    )
    .unwrap();
    assert_eq!(
        cancelled["rounds"][0][0]["state"].as_str(),
        Some("Cancelled"),
        "precondition: round 0 soft-cancelled, seating preserved"
    );
    assert_eq!(cancelled["state"].as_str(), Some("Playing"));

    // SA recorded against round 0 — the round that just got cancelled.
    let sanctions = json::array![
        { user_uid: "p1", level: "standings_adjustment", round_number: 0, lifted_at: json::Null, deleted_at: json::Null },
    ];
    let standings = super::standings::compute_preliminary_standings(&cancelled, &sanctions);
    let p1 = standings.iter().find(|s| s.user_uid == "p1").unwrap();
    assert_eq!(
        p1.vp, 1.5,
        "round 1 raw 2.5 - 1.0 SA (round 0 cancelled, contributes nothing)"
    );
    assert_eq!(
        p1.gw, 0.0,
        "SA redirected onto surviving round 1: adjusted 1.5 (< 2.0) removes the GW, agreeing with the VP penalty (pre-fix it parked on cancelled round 0 and p1 wrongly kept the GW)"
    );
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
    assert_eq!(result.unwrap_err(), EngineError::PlayerDisqualified);
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
    assert_eq!(result.unwrap_err(), EngineError::PlayerDisqualified);
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
    assert!(result.unwrap_err().to_string().contains("suspended"));
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
       // winner cleared to "" (not null): backend types it `str`, a null 500s the action
    assert_eq!(updated["winner"].as_str(), Some(""));
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

// Open rounds: max_rounds is a PER-PLAYER cap. After a player plays that many rounds they
// retire to `Completed` (still finals-eligible) and may no longer check in for another round.
#[test]
fn test_open_rounds_caps_player_and_blocks_recheckin() {
    let mut t = tournament_with_round();
    t["max_rounds"] = 1.into();
    // One round per player; a single finished table lets FinishRound complete the round.
    t["players"] = json::array![
        { user_uid: "p1", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "p2", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "p3", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "p4", state: "Playing", payment_status: "Pending", toss: 0 },
    ];
    t["rounds"] = json::array![[t["rounds"][0][0].clone()]];

    let org = make_organizer();
    let finished =
        json::parse(&run_event(&t, &json::object! { type: "FinishRound" }, &org).unwrap()).unwrap();
    assert_eq!(finished["state"].as_str(), Some("Waiting"));
    // Every player has now played their cap → Completed, not re-armed as Checked-in.
    for i in 0..4 {
        assert_eq!(finished["players"][i]["state"].as_str(), Some("Completed"));
    }
    // Re-checking in a capped player is refused with the per-player-cap error.
    let err = run_event(
        &finished,
        &json::object! { type: "CheckIn", player_uid: "p1" },
        &org,
    )
    .unwrap_err();
    assert!(matches!(err, EngineError::PlayerReachedMaxRounds));
}

// Open rounds: CheckInAll must not re-arm a player who already reached their cap, even when they
// sit in a re-armable state (e.g. Registered after a reopen) rather than Completed.
#[test]
fn test_check_in_all_skips_capped_players() {
    let mut t = make_tournament();
    t["max_rounds"] = 1.into();
    t["state"] = "Waiting".into();
    // p1 already played its one allowed round (seated in round 0) but sits in Registered; p2 has
    // played nothing. CheckInAll must re-arm p2 but leave the capped p1 alone.
    t["players"] = json::array![
        { user_uid: "p1", state: "Registered", payment_status: "Pending", toss: 0 },
        { user_uid: "p2", state: "Registered", payment_status: "Pending", toss: 0 },
    ];
    t["rounds"] = json::array![
        [ { seating: [
            { player_uid: "p1", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
        ], state: "Finished", override: json::Null } ],
    ];

    let updated = json::parse(
        &run_event(&t, &json::object! { type: "CheckInAll" }, &make_organizer()).unwrap(),
    )
    .unwrap();
    let state_of = |uid: &str| {
        updated["players"]
            .members()
            .find(|p| p["user_uid"].as_str() == Some(uid))
            .and_then(|p| p["state"].as_str())
            .unwrap()
            .to_string()
    };
    assert_eq!(
        state_of("p1"),
        "Registered",
        "capped player not re-armed by CheckInAll"
    );
    assert_eq!(state_of("p2"), "Checked-in", "uncapped player checked in");
}

// Open rounds: CheckIn reinstates a drop-out (Finished) to the right active state by cap — under
// cap → Checked-in (can still play), at cap → Completed (finals-eligible, not a new round).
#[test]
fn test_check_in_reinstates_dropout_by_cap() {
    let mut t = make_tournament();
    t["max_rounds"] = 2.into();
    t["state"] = "Waiting".into();
    // p1 played both rounds (at cap), p2 played one (under cap); both then dropped out (Finished).
    t["players"] = json::array![
        { user_uid: "p1", state: "Finished", payment_status: "Pending", toss: 0 },
        { user_uid: "p2", state: "Finished", payment_status: "Pending", toss: 0 },
    ];
    t["rounds"] = json::array![
        [ { seating: [
            { player_uid: "p1", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
            { player_uid: "p2", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
        ], state: "Finished", override: json::Null } ],
        [ { seating: [
            { player_uid: "p1", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
        ], state: "Finished", override: json::Null } ],
    ];

    let org = make_organizer();
    let r1 = json::parse(
        &run_event(
            &t,
            &json::object! { type: "CheckIn", player_uid: "p1" },
            &org,
        )
        .unwrap(),
    )
    .unwrap();
    let r2 = json::parse(
        &run_event(
            &r1,
            &json::object! { type: "CheckIn", player_uid: "p2" },
            &org,
        )
        .unwrap(),
    )
    .unwrap();
    let state_of = |t: &JsonValue, uid: &str| {
        t["players"]
            .members()
            .find(|p| p["user_uid"].as_str() == Some(uid))
            .and_then(|p| p["state"].as_str())
            .unwrap()
            .to_string()
    };
    assert_eq!(
        state_of(&r2, "p1"),
        "Completed",
        "capped drop-out reinstated to Completed"
    );
    assert_eq!(
        state_of(&r2, "p2"),
        "Checked-in",
        "under-cap drop-out reinstated to Checked-in"
    );
}

// #272 / open rounds: StartFinals selects the top-5 *eligible* players. A capped player
// resting in `Completed` is still a finalist; a withdrawn player in `Finished` is excluded
// from the cutoff and the next-ranked qualifier is promoted into the finals. Asserting the
// wrong set here means the wrong person plays the final (a result pushed to VEKN/league).
#[test]
fn test_start_finals_includes_completed_excludes_withdrawn() {
    let mut t = make_tournament();
    t["state"] = "Waiting".into();
    // Two single-table rounds (>=2 rounds gate). Each table is [2,1,1,1,0] in seating
    // (predator-prey) order — a valid oust sequence summing to the 5-seat table size.
    // Distinct toss values keep the cutoff free of unbroken ties.
    t["players"] = json::array![
        { user_uid: "p1", state: "Completed",  payment_status: "Pending", toss: 5 },
        { user_uid: "p2", state: "Playing",    payment_status: "Pending", toss: 4 },
        { user_uid: "p3", state: "Playing",    payment_status: "Pending", toss: 3 },
        { user_uid: "p4", state: "Finished",   payment_status: "Pending", toss: 2 },
        { user_uid: "p5", state: "Playing",    payment_status: "Pending", toss: 1 },
        { user_uid: "p6", state: "Playing",    payment_status: "Pending", toss: 0 },
    ];
    t["rounds"] = json::array![
        [ { seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.0, tp: 60 }, judge_uid: "" },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p4", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p5", result: { gw: 0, vp: 0.0, tp: 12 }, judge_uid: "" },
        ], state: "Finished", override: json::Null } ],
        [ { seating: [
            { player_uid: "p2", result: { gw: 1, vp: 2.0, tp: 60 }, judge_uid: "" },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p4", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p6", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p1", result: { gw: 0, vp: 0.0, tp: 12 }, judge_uid: "" },
        ], state: "Finished", override: json::Null } ],
    ];

    let updated = json::parse(
        &run_event(
            &t,
            &json::object! { type: "StartFinals" },
            &make_organizer(),
        )
        .unwrap(),
    )
    .unwrap();

    // By score the natural top 5 would be {p2, p1, p3, p4, p6}. p4 withdrew (Finished) so it
    // is excluded and p5 is promoted; p1 is capped (Completed) but still a finalist.
    let finalists: std::collections::HashSet<&str> = updated["players"]
        .members()
        .filter(|p| p["finalist"].as_bool() == Some(true))
        .filter_map(|p| p["user_uid"].as_str())
        .collect();
    assert_eq!(
        finalists,
        ["p1", "p2", "p3", "p5", "p6"].into_iter().collect(),
        "Completed player p1 included; withdrawn p4 excluded and p5 promoted"
    );
    // The withdrawn player must not be flagged or pulled into the finals seating.
    let seated: std::collections::HashSet<&str> = updated["finals"]["seating"]
        .members()
        .filter_map(|s| s["player_uid"].as_str())
        .collect();
    assert!(
        !seated.contains("p4"),
        "withdrawn p4 must not be seated in finals"
    );
    assert_eq!(seated.len(), 5);
}

// #362: the finals/toss two-round minimum must count *played* rounds, not `rounds.len()`. A
// fully soft-cancelled round did not happen, so one real round + one cancelled round must NOT
// satisfy the minimum — otherwise an organizer starts (and VEKN/ratings silently receive) a
// finals decided on a single round. Asserted at the StartFinals gate, the shared
// `count_played_rounds` carrier: SetToss/RandomToss route through the same helper, so this one
// test guards all three. Reach the state through the real engine (CancelRound a non-last round,
// land in Waiting), not a hand-built Cancelled fixture. Pre-fix the gate tested rounds.len() (2)
// and this returned Ok, illegitimately seating a 5-player final; post-fix it counts 1 and refuses.
#[test]
fn test_start_finals_rejects_when_only_one_round_survived_cancellation() {
    let mut t = make_tournament();
    t["state"] = "Playing".into();
    // Two parallel pods: round 0 (q-pod) still in progress — the one we cancel; round 1 (p-pod)
    // a finished, valid single-oust 5-seat table (VP sum == table size).
    t["players"] = json::array![
        { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 5 },
        { user_uid: "p2", state: "Checked-in", payment_status: "Pending", toss: 4 },
        { user_uid: "p3", state: "Checked-in", payment_status: "Pending", toss: 3 },
        { user_uid: "p4", state: "Checked-in", payment_status: "Pending", toss: 2 },
        { user_uid: "p5", state: "Checked-in", payment_status: "Pending", toss: 1 },
        { user_uid: "q1", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q2", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q3", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q4", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q5", state: "Playing", payment_status: "Pending", toss: 0 },
    ];
    t["rounds"] = json::array![
        [ { seating: [
            { player_uid: "q1", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
            { player_uid: "q2", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
            { player_uid: "q3", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
            { player_uid: "q4", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
            { player_uid: "q5", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
        ], state: "In Progress", override: json::Null } ],
        [ { seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.0, tp: 60 }, judge_uid: "" },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p4", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p5", result: { gw: 0, vp: 0.0, tp: 12 }, judge_uid: "" },
        ], state: "Finished", override: json::Null } ],
    ];

    let org = make_organizer();
    // Soft-cancel the non-last round through the real engine; with the other round Finished the
    // tournament lands in Waiting (finals-reachable) with exactly one *played* round remaining.
    let cancelled = json::parse(
        &run_event(&t, &json::object! { type: "CancelRound", round: 0 }, &org).expect("cancel"),
    )
    .unwrap();
    assert_eq!(cancelled["state"].as_str(), Some("Waiting"));
    assert_eq!(cancelled["rounds"][0][0]["state"].as_str(), Some("Cancelled"));
    assert_eq!(cancelled["rounds"][1][0]["state"].as_str(), Some("Finished"));

    // The gate counts played rounds (1), not rounds.len() (2), and refuses the finals.
    let err = run_event(&cancelled, &json::object! { type: "StartFinals" }, &org).unwrap_err();
    assert!(matches!(err, EngineError::FinalsMinRounds));
}

// Open rounds: CancelFinals reverts a seated finals back to Waiting so a no-show finalist can be
// dropped and the field re-seated. Capped finalists must return to Completed (not Checked-in) so
// they aren't re-armed for another preliminary round.
#[test]
fn test_cancel_finals_reverts_finalists_by_cap() {
    let mut t = make_tournament();
    t["max_rounds"] = 2.into(); // p1..p4 play both rounds (at cap); p5/p6 play one (under cap)
    t["state"] = "Waiting".into();
    t["players"] = json::array![
        { user_uid: "p1", state: "Completed",  payment_status: "Pending", toss: 5, finalist: false },
        { user_uid: "p2", state: "Completed",  payment_status: "Pending", toss: 4, finalist: false },
        { user_uid: "p3", state: "Completed",  payment_status: "Pending", toss: 3, finalist: false },
        { user_uid: "p4", state: "Finished",   payment_status: "Pending", toss: 2, finalist: false },
        { user_uid: "p5", state: "Checked-in", payment_status: "Pending", toss: 1, finalist: false },
        { user_uid: "p6", state: "Checked-in", payment_status: "Pending", toss: 0, finalist: false },
    ];
    t["rounds"] = json::array![
        [ { seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.0, tp: 60 }, judge_uid: "" },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p4", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p5", result: { gw: 0, vp: 0.0, tp: 12 }, judge_uid: "" },
        ], state: "Finished", override: json::Null } ],
        [ { seating: [
            { player_uid: "p2", result: { gw: 1, vp: 2.0, tp: 60 }, judge_uid: "" },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p4", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p6", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p1", result: { gw: 0, vp: 0.0, tp: 12 }, judge_uid: "" },
        ], state: "Finished", override: json::Null } ],
    ];

    let org = make_organizer();
    let seated =
        json::parse(&run_event(&t, &json::object! { type: "StartFinals" }, &org).unwrap()).unwrap();
    assert_eq!(seated["state"].as_str(), Some("Playing"));
    assert!(!seated["finals"].is_null());

    let reverted =
        json::parse(&run_event(&seated, &json::object! { type: "CancelFinals" }, &org).unwrap())
            .unwrap();
    assert_eq!(reverted["state"].as_str(), Some("Waiting"));
    assert!(reverted["finals"].is_null(), "finals object cleared");

    let state_of = |uid: &str| {
        reverted["players"]
            .members()
            .find(|p| p["user_uid"].as_str() == Some(uid))
            .and_then(|p| p["state"].as_str())
            .unwrap()
            .to_string()
    };
    let finalist_of = |uid: &str| {
        reverted["players"]
            .members()
            .find(|p| p["user_uid"].as_str() == Some(uid))
            .map(|p| p["finalist"].as_bool().unwrap_or(false))
            .unwrap()
    };
    for uid in ["p1", "p2", "p3", "p5", "p6"] {
        assert!(!finalist_of(uid), "{uid} finalist flag cleared");
    }
    // Capped finalists (played both rounds) → Completed; under-cap (one round) → Checked-in.
    assert_eq!(state_of("p1"), "Completed");
    assert_eq!(state_of("p2"), "Completed");
    assert_eq!(state_of("p3"), "Completed");
    assert_eq!(state_of("p5"), "Checked-in");
    assert_eq!(state_of("p6"), "Checked-in");
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
fn test_alter_seating_fewer_tables_fails() {
    let tournament = tournament_with_round();
    // Payload tables match existing tables by position: fewer than existing is rejected
    let event = json::object! {
        type: "AlterSeating",
        round: 0,
        seating: [["p1", "p2", "p3", "p4"]],
    };
    let actor = make_organizer();
    let result = run_event(&tournament, &event, &actor);
    assert!(result.is_err());
    assert!(result
        .unwrap_err()
        .to_string()
        .contains("Table count mismatch"));
}

#[test]
fn test_alter_seating_undersized_table_fails() {
    let tournament = tournament_with_round();
    let event = json::object! {
        type: "AlterSeating",
        round: 0,
        seating: [["p1", "p2", "p3", "p4"], ["p5", "p6"], ["p7", "p8"]],
    };
    let actor = make_organizer();
    let result = run_event(&tournament, &event, &actor);
    assert!(result.is_err());
    assert!(result
        .unwrap_err()
        .to_string()
        .contains("Invalid table size"));
}

#[test]
fn test_alter_seating_added_table_and_empty_drop() {
    let tournament = tournament_with_round();
    // Table 0 emptied (dropped on save), table 1 keeps p5-p8, appended table 2 gets p1-p4
    let event = json::object! {
        type: "AlterSeating",
        round: 0,
        seating: [[], ["p5", "p6", "p7", "p8"], ["p1", "p2", "p3", "p4"]],
    };
    let actor = make_organizer();
    let result = run_event(&tournament, &event, &actor);
    let updated = json::parse(&result.unwrap()).unwrap();

    // Empty table dropped: 2 tables remain
    assert_eq!(updated["rounds"][0].len(), 2);
    // Table 1 (unchanged players, same position) keeps its results
    assert_eq!(
        updated["rounds"][0][0]["seating"][0]["player_uid"].as_str(),
        Some("p5")
    );
    // p1-p4 moved to a new table: results reset, state In Progress
    assert_eq!(
        updated["rounds"][0][1]["seating"][0]["player_uid"].as_str(),
        Some("p1")
    );
    assert_eq!(
        updated["rounds"][0][1]["seating"][0]["result"]["vp"].as_f64(),
        Some(0.0)
    );
    assert_eq!(
        updated["rounds"][0][1]["state"].as_str(),
        Some("In Progress")
    );
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
    assert!(result.unwrap_err().to_string().contains("not found"));
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
    assert!(result.unwrap_err().to_string().contains("organizers"));
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
    assert!(result
        .unwrap_err()
        .to_string()
        .contains("Cannot alter seating"));
}

// SwapSeats is reachable in Finished state (require_state_or_finished), where no later
// FinishRound/finals refreshes standings. Because it swaps player_uids but leaves each
// seat's result in place, a swap silently *exchanges* two scored players' standings — and
// those stored standings feed ratings, the vekn.net push, and exports. Regression guard for
// #359: after the swap, the stored standings must credit each player with the score at the
// seat they now occupy (gw + vp move with them), not the pre-swap arrangement.
#[test]
fn test_swap_seats_in_finished_refreshes_standings() {
    let mut t = make_tournament();
    t["state"] = "Finished".into();
    t["players"] = json::array![
        { user_uid: "p1", state: "Finished", payment_status: "Pending", toss: 0 },
        { user_uid: "p2", state: "Finished", payment_status: "Pending", toss: 0 },
        { user_uid: "p3", state: "Finished", payment_status: "Pending", toss: 0 },
        { user_uid: "p4", state: "Finished", payment_status: "Pending", toss: 0 },
    ];
    // One finished table, engine-valid VP vector (single oust, sum == 4). p1 is the clear
    // game winner (vp 2.0 -> gw 1.0 via compute_gw); p4 has nothing (vp 0.0 -> gw 0.0).
    t["rounds"] = json::array![
        [ { seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.0, tp: 0 }, judge_uid: "" },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 0 }, judge_uid: "" },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 0 }, judge_uid: "" },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
        ], state: "Finished", override: json::Null } ],
    ];
    // Pre-swap standings, as they stood when the tournament finished. The bug is that these go
    // *stale* on a swap (not that they go missing) — pre-seeding them makes the pre-fix path
    // pass them through untouched, so the test pins staleness, not absence.
    t["standings"] = json::array![
        { user_uid: "p1", gw: 1.0, vp: 2.0, tp: 0.0, toss: 0, finalist: false, disqualified: false, non_competing: false },
        { user_uid: "p2", gw: 0.0, vp: 1.0, tp: 0.0, toss: 0, finalist: false, disqualified: false, non_competing: false },
        { user_uid: "p3", gw: 0.0, vp: 1.0, tp: 0.0, toss: 0, finalist: false, disqualified: false, non_competing: false },
        { user_uid: "p4", gw: 0.0, vp: 0.0, tp: 0.0, toss: 0, finalist: false, disqualified: false, non_competing: false },
    ];

    // Swap the game winner (seat 0) with the last-place player (seat 3) on the scored table.
    let event = json::object! {
        type: "SwapSeats", round: 0, table1: 0, seat1: 0, table2: 0, seat2: 3,
    };
    let out = json::parse(&run_event(&t, &event, &make_organizer()).expect("swap")).unwrap();

    let standing = |uid: &str| {
        out["standings"]
            .members()
            .find(|s| s["user_uid"].as_str() == Some(uid))
            .unwrap_or_else(|| panic!("no standing for {uid}"))
            .clone()
    };
    // The score (and the game win) moved to the seat's new occupant: p4 now holds p1's result,
    // p1 now holds p4's. Pre-fix, standings were left untouched -> p4 would still read vp 0.0.
    assert_eq!(standing("p4")["vp"].as_f64(), Some(2.0));
    assert_eq!(standing("p4")["gw"].as_f64(), Some(1.0));
    assert_eq!(standing("p1")["vp"].as_f64(), Some(0.0));
    assert_eq!(standing("p1")["gw"].as_f64(), Some(0.0));
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
    assert!(result.unwrap_err().to_string().contains("Invalid format"));
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
    assert!(result.unwrap_err().to_string().contains("organizers"));
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
    assert!(result
        .unwrap_err()
        .to_string()
        .contains("name cannot be empty"));
}

#[test]
fn test_update_config_timer_fields() {
    let tournament = make_tournament();
    let event = json::object! {
        type: "UpdateConfig",
        config: {
            round_time: 7200,
            finals_time: 9000,
        },
    };
    let actor = make_organizer();
    let result = run_event(&tournament, &event, &actor);
    assert!(result.is_ok());
    let updated = json::parse(&result.unwrap()).unwrap();
    assert_eq!(updated["round_time"].as_i64(), Some(7200));
    assert_eq!(updated["finals_time"].as_i64(), Some(9000));
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
    assert!(result
        .unwrap_err()
        .to_string()
        .contains("Only league organizers"));
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

    let event = json::object! { type: "CheckIn", player_uid: "player-1", vekn_id: "1234567" };
    let actor = make_player("player-1");

    let result = run_event(&tournament, &event, &actor);
    assert!(result.is_ok());
    let updated = json::parse(&result.unwrap()).unwrap();
    assert_eq!(updated["players"].len(), 1);
    assert_eq!(updated["players"][0]["user_uid"].as_str(), Some("player-1"));
    assert_eq!(updated["players"][0]["state"].as_str(), Some("Checked-in"));
}

#[test]
fn test_checkin_auto_register_blocked_by_dq() {
    let mut tournament = make_tournament();
    tournament["state"] = "Waiting".into();
    tournament["players"] = json::array![];

    let event = json::object! { type: "CheckIn", player_uid: "player-1", vekn_id: "1234567" };
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
    assert_eq!(raw.unwrap_err(), EngineError::PlayerDisqualified);
}

#[test]
fn test_checkin_auto_register_blocked_by_suspension() {
    let mut tournament = make_tournament();
    tournament["state"] = "Waiting".into();
    tournament["players"] = json::array![];

    let event = json::object! { type: "CheckIn", player_uid: "player-1", vekn_id: "1234567" };
    let actor = make_player("player-1");
    let sanctions =
        r#"[{"user_uid":"player-1","level":"suspension","lifted_at":null,"deleted_at":null}]"#;

    let raw = process_tournament_event(
        &tournament.dump(),
        &event.dump(),
        &actor.dump(),
        sanctions,
        &no_decks(),
    );
    assert!(raw.is_err());
    assert!(raw.unwrap_err().to_string().contains("suspended"));
}

#[test]
fn test_checkin_auto_register_requires_vekn_id() {
    let mut tournament = make_tournament();
    tournament["state"] = "Waiting".into();
    tournament["players"] = json::array![];

    // No vekn_id → should fail
    let event = json::object! { type: "CheckIn", player_uid: "player-1" };
    let actor = make_player("player-1");

    let result = run_event(&tournament, &event, &actor);
    assert!(result.is_err());
    assert_eq!(result.unwrap_err(), EngineError::VeknIdRequired);
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
    assert!(result
        .unwrap_err()
        .to_string()
        .contains("organizers or the player"));
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
    assert!(result.unwrap_err().to_string().contains("in progress"));
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
    assert!(result.unwrap_err().to_string().contains("finished"));
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
    assert!(result.unwrap_err().to_string().contains("already started"));
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
    assert!(result.unwrap_err().to_string().contains("already started"));
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
    assert!(result
        .unwrap_err()
        .to_string()
        .contains("deck_index required"));
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
    let start_event =
        json::parse(r#"{"type": "StartRound", "seating": [["p0","p1","p2","p3"]]}"#).unwrap();
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
    assert!(delete_result
        .unwrap_err()
        .to_string()
        .contains("already started"));
}

// --- Judge-locked score tests ---

#[test]
fn test_player_blocked_from_scoring_after_organizer_sets_score() {
    let mut t = tournament_with_round();
    // Set judge_uid on table 1 seat to simulate organizer having scored
    t["rounds"][0][1]["seating"][0]["judge_uid"] = "organizer-1".into();
    t["rounds"][0][1]["state"] = "In Progress".into();

    let event = json::object! {
        type: "SetScore",
        round: 0,
        table: 1,
        scores: [
            { player_uid: "p5", vp: 1.0 },
        ],
    };
    let player = make_player("p5");
    let result = run_event(&t, &event, &player);
    assert!(result.is_err());
    assert!(result.unwrap_err().to_string().contains("set by organiser"));
}

#[test]
fn test_organizer_can_rescore_judge_locked_table() {
    let mut t = tournament_with_round();
    t["rounds"][0][1]["seating"][0]["judge_uid"] = "organizer-1".into();
    t["rounds"][0][1]["state"] = "In Progress".into();

    let event = json::object! {
        type: "SetScore",
        round: 0,
        table: 1,
        scores: [
            { player_uid: "p5", vp: 2.0 },
        ],
    };
    let organizer = make_organizer();
    let result = run_event(&t, &event, &organizer);
    assert!(result.is_ok());
}

// --- Out-of-round score correction (organizer edits past round while Waiting) ---

/// One finished round, tournament back to Waiting between rounds. Both tables carry
/// a valid completed result (VPs ceil-sum to table size, valid oust order: p1/p5 win).
fn waiting_after_round() -> JsonValue {
    let mut t = tournament_with_round();
    t["state"] = "Waiting".into();
    let vps = [2.0, 1.0, 1.0, 0.0];
    for tbl in 0..2 {
        for (s, &vp) in vps.iter().enumerate() {
            t["rounds"][0][tbl]["seating"][s]["result"]["vp"] = vp.into();
        }
        t["rounds"][0][tbl]["state"] = "Finished".into();
    }
    t
}

#[test]
fn test_organizer_corrects_vp_in_waiting_refreshes_standings() {
    // Between rounds an organizer fixes a data-entry error in a past round. This was
    // blocked before (SetScore required Playing) and left stored standings stale.
    let t = waiting_after_round();

    // Make p2 the table winner with a valid oust sequence (p1,p2,p3,p4 = 0,2,1,1).
    let event = json::object! {
        type: "SetScore",
        round: 0,
        table: 0,
        scores: [
            { player_uid: "p1", vp: 0.0 },
            { player_uid: "p2", vp: 2.0 },
            { player_uid: "p3", vp: 1.0 },
            { player_uid: "p4", vp: 1.0 },
        ],
    };
    let updated = json::parse(&run_event(&t, &event, &make_organizer()).unwrap()).unwrap();

    // Seat result applied...
    assert_eq!(
        updated["rounds"][0][0]["seating"][1]["result"]["vp"].as_f64(),
        Some(2.0)
    );
    assert_eq!(updated["rounds"][0][0]["state"].as_str(), Some("Finished"));
    // ...and stored standings recomputed (was empty) to carry the corrected VP/GW.
    let p2 = updated["standings"]
        .members()
        .find(|s| s["user_uid"] == "p2")
        .expect("p2 in standings");
    assert_eq!(p2["vp"].as_f64(), Some(2.0));
    assert_eq!(p2["gw"].as_f64(), Some(1.0));
}

#[test]
fn test_player_cannot_score_while_waiting() {
    // A player may only score during their live round, not between rounds.
    let t = waiting_after_round();
    let event = json::object! {
        type: "SetScore",
        round: 0,
        table: 0,
        scores: [ { player_uid: "p1", vp: 1.0 } ],
    };
    let err = run_event(&t, &event, &make_player("p1")).unwrap_err();
    assert!(err.to_string().contains("Playing state"));
}

#[test]
fn test_organizer_corrects_earlier_round_during_parallel_round_refreshes_standings() {
    // Online parallel rounds: round 0 finished, round 1 still in progress, tournament
    // stays Playing. Correcting a VP in the already-finished round 0 must refresh stored
    // standings — pre-fix, SetScore in Playing skipped update_standings, so a correction
    // to a past round left ratings/VEKN-push reading stale totals.
    let mut t = waiting_after_round();
    t["state"] = "Playing".into();
    t["online"] = true.into();
    // A second, in-progress round (same four players at one table).
    t["rounds"]
        .push(json::array![[
            { player_uid: "p1", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
            { player_uid: "p2", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
            { player_uid: "p3", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
        ]])
        .unwrap();
    // Stale stored standings that the recompute must overwrite.
    t["standings"] = json::array![
        { user_uid: "p2", gw: 0.0, vp: 99.0, tp: 0, toss: 0, finalist: false },
    ];

    // Move round 0 table 0's win from p1 to p2 (valid oust order: p1,p2,p3,p4 = 0,2,1,1).
    let event = json::object! {
        type: "SetScore",
        round: 0,
        table: 0,
        scores: [
            { player_uid: "p1", vp: 0.0 },
            { player_uid: "p2", vp: 2.0 },
            { player_uid: "p3", vp: 1.0 },
            { player_uid: "p4", vp: 1.0 },
        ],
    };
    let updated = json::parse(&run_event(&t, &event, &make_organizer()).unwrap()).unwrap();

    // Edit landed on the finished round, tournament stays Playing for the live round...
    assert_eq!(
        updated["rounds"][0][0]["seating"][1]["result"]["vp"].as_f64(),
        Some(2.0)
    );
    assert_eq!(updated["state"].as_str(), Some("Playing"));
    // ...and the stale standings were recomputed (p2 = 2.0 from round 0, 0.0 in round 1).
    let p2 = updated["standings"]
        .members()
        .find(|s| s["user_uid"] == "p2")
        .expect("p2 in standings");
    assert_eq!(p2["vp"].as_f64(), Some(2.0));
}

// --- Raffle pool tests ---

#[test]
fn test_raffle_before_first_round_draws_checked_in_players() {
    // Pre-round-1 (Waiting / check-in): no rounds exist yet, but the raffle base
    // must still be the checked-in players — registered-but-not-checked-in are out.
    let mut t = make_tournament();
    t["state"] = "Waiting".into();
    t["players"] = json::array![
        { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p2", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p3", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p4", state: "Registered", payment_status: "Pending", toss: 0 },
    ];
    let event = json::object! {
        type: "RaffleDraw",
        label: "door prize",
        pool: "AllPlayers",
        exclude_drawn: false,
        count: 4,
        seed: 7,
    };
    let updated = json::parse(&run_event(&t, &event, &make_organizer()).unwrap()).unwrap();
    let mut winners: Vec<&str> = updated["raffles"][0]["winners"]
        .members()
        .filter_map(|w| w.as_str())
        .collect();
    winners.sort();
    assert_eq!(winners, vec!["p1", "p2", "p3"]);
}

#[test]
fn test_raffle_pools_count_scores_from_round_in_progress() {
    // Mid-round: table 0 scored (p1 has the GW, p1-p4 have VPs), table 1 unscored,
    // and no stored standings (FinishRound never ran). Pools must be computed from
    // the live round results, not the stale stored standings.
    let t = tournament_with_round();
    let org = make_organizer();

    let event = json::object! {
        type: "RaffleDraw",
        label: "no vp",
        pool: "NoVictoryPoint",
        exclude_drawn: false,
        count: 8,
        seed: 42,
    };
    let updated = json::parse(&run_event(&t, &event, &org).unwrap()).unwrap();
    let mut winners: Vec<&str> = updated["raffles"][0]["winners"]
        .members()
        .filter_map(|w| w.as_str())
        .collect();
    winners.sort();
    assert_eq!(winners, vec!["p5", "p6", "p7", "p8"]);

    let event = json::object! {
        type: "RaffleDraw",
        label: "no gw",
        pool: "NoGameWin",
        exclude_drawn: false,
        count: 8,
        seed: 42,
    };
    let updated = json::parse(&run_event(&updated, &event, &org).unwrap()).unwrap();
    let winners: Vec<&str> = updated["raffles"][1]["winners"]
        .members()
        .filter_map(|w| w.as_str())
        .collect();
    assert_eq!(winners.len(), 7);
    assert!(!winners.contains(&"p1"));
}
