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
    // No submitted seating: the engine computes it from tournament uid + round,
    // so two StartRound calls on the same input must be byte-identical.
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
    // Four players finish fully tied (same gw/vp/tp/toss); without the terminal
    // user_uid tiebreak the order is HashMap-nondeterministic across calls.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![json::array![json::object! {
        seating: [
            { player_uid: "pc", result: { gw: 0, vp: 0.5, tp: 36 } },
            { player_uid: "pa", result: { gw: 0, vp: 0.5, tp: 36 } },
            { player_uid: "pd", result: { gw: 0, vp: 0.5, tp: 36 } },
            { player_uid: "pb", result: { gw: 0, vp: 0.5, tp: 36 } },
        ],
        state: "Finished",
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

    assert_eq!(updated["players"][0]["state"].as_str(), Some("Playing"));
    assert_eq!(updated["players"][3]["state"].as_str(), Some("Playing"));
    assert_eq!(updated["players"][4]["state"].as_str(), Some("Finished"));
    assert_eq!(updated["players"][5]["state"].as_str(), Some("Finished"));
}

#[test]
fn test_start_round_no_show_drop_scoped_to_standard_round_one() {
    // Rounds 2+ leave Registered players untouched (a legitimate waiting
    // state after ResetCheckIn); open-rounds tournaments never auto-drop.
    let org = make_organizer();

    // Round 2 of a standard tournament: p5 stays Registered.
    let mut t = tournament_with_round();
    t["state"] = "Waiting".into();
    t["rounds"][0][1]["state"] = "Finished".into();
    t["players"] = json::array![
        { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p2", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p3", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p4", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p5", state: "Registered", payment_status: "Pending", toss: 0 },
    ];
    let event =
        json::parse(r#"{"type": "StartRound", "seating": [["p1","p2","p3","p4"]]}"#).unwrap();
    let updated = json::parse(&run_event(&t, &event, &org).unwrap()).unwrap();
    assert_eq!(updated["players"][4]["state"].as_str(), Some("Registered"));

    // Open-rounds round 1: Registered is a normal pool state — no drop.
    let mut t = make_tournament();
    t["state"] = "Waiting".into();
    t["open_rounds"] = true.into();
    t["players"] = json::array![
        { user_uid: "p0", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p2", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p3", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p4", state: "Registered", payment_status: "Pending", toss: 0 },
    ];
    let event =
        json::parse(r#"{"type": "StartRound", "seating": [["p0","p1","p2","p3"]]}"#).unwrap();
    let updated = json::parse(&run_event(&t, &event, &org).unwrap()).unwrap();
    assert_eq!(updated["players"][4]["state"].as_str(), Some("Registered"));
}

#[test]
fn test_seat_player_accepts_checked_in_late_arrival() {
    // A latecomer checked in mid-round is Checked-in, not Registered, and must
    // still be seatable.
    let mut t = tournament_with_round();
    t["players"]
        .push(json::object! { user_uid: "p9", state: "Checked-in", payment_status: "Pending", toss: 0 })
        .unwrap();
    let org = make_organizer();

    let event = json::object! { type: "SeatPlayer", player_uid: "p9", table: 1, seat: 4 };
    let updated = json::parse(&run_event(&t, &event, &org).unwrap()).unwrap();
    assert_eq!(updated["rounds"][0][1]["seating"].len(), 5);
    assert_eq!(updated["players"][8]["state"].as_str(), Some("Playing"));
}

#[test]
fn test_seat_player_reinstates_zero_round_no_show() {
    // A round-1 no-show (Finished, zero rounds played) who walks in mid-round is
    // seated straight onto a live table; one who actually PLAYED stays ineligible.
    let mut t = tournament_with_round();
    t["players"]
        .push(
            json::object! { user_uid: "p9", state: "Finished", payment_status: "Pending", toss: 0 },
        )
        .unwrap();
    let org = make_organizer();

    let event = json::object! { type: "SeatPlayer", player_uid: "p9", table: 1, seat: 4 };
    let updated = json::parse(&run_event(&t, &event, &org).unwrap()).unwrap();
    assert_eq!(updated["rounds"][0][1]["seating"].len(), 5);
    assert_eq!(updated["players"][8]["state"].as_str(), Some("Playing"));

    // p1 is seated in round 0 (one round played) — Finished + rounds > 0 rejects.
    let mut t2 = tournament_with_round();
    t2["players"][0]["state"] = "Finished".into();
    let event = json::object! { type: "SeatPlayer", player_uid: "p1", table: 1, seat: 4 };
    let result = run_event(&t2, &event, &org);
    assert!(result.is_err());
    assert!(result.unwrap_err().to_string().contains("Registered"));
}

// Self-organized rounds: registration is the gate, the initiator must be seated,
// abuse vectors (concurrent pod, non-participant, disabled) are rejected.
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

    let no_self =
        json::parse(r#"{"type":"SelfOrganizeRound","player_uids":["p2","p3","p4","p5"]}"#).unwrap();
    assert!(matches!(
        run_event(&t, &no_self, &p1),
        Err(EngineError::SelfOrganizeNotSeated)
    ));

    let busy =
        json::parse(r#"{"type":"SelfOrganizeRound","player_uids":["p1","p2","p3","p6"]}"#).unwrap();
    assert!(matches!(
        run_event(&t, &busy, &p1),
        Err(EngineError::SelfOrganizeIneligible { .. })
    ));

    let ghost =
        json::parse(r#"{"type":"SelfOrganizeRound","player_uids":["p1","p2","p3","ghost"]}"#)
            .unwrap();
    assert!(matches!(
        run_event(&t, &ghost, &p1),
        Err(EngineError::NotRegistered)
    ));

    let mut off = t.clone();
    off["self_organized_rounds"] = false.into();
    assert!(matches!(
        run_event(&off, &pod, &p1),
        Err(EngineError::SelfOrganizeDisabled)
    ));

    let mut offline = t.clone();
    offline["online"] = false.into();
    offline["max_rounds"] = 0.into();
    assert!(
        run_event(&offline, &pod, &p1).is_ok(),
        "self-organize allowed offline with no cap"
    );
}

// Cancelling a non-last round soft-cancels: the slot is preserved (index-stable
// for deck.round / SA round_number), players are released, other rounds are untouched.
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
    t["rounds"] = json::array![
        [ { seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.0, tp: 60 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 36 } },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 12 } },
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
    assert_eq!(st(&out, "p1"), "Checked-in");
    assert_eq!(st(&out, "q1"), "Playing");
    assert!(
        !out["standings"]
            .members()
            .any(|s| s["user_uid"].as_str() == Some("p3")),
        "cancelled round contributes no standings"
    );
}

// Cancelling every round of a parallel-round event first-to-last must end at zero rounds,
// like the last-first order does: the hard-remove takes the trailing soft-cancelled slots
// with it, so the organizer is not left with cancelled rounds cancel can no longer reach.
#[test]
fn test_cancel_last_round_sweeps_trailing_cancelled_rounds() {
    let mut t = make_tournament();
    t["state"] = "Playing".into();
    t["online"] = true.into();
    t["players"] = json::array![
        { user_uid: "p1", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "p2", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "p3", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "p4", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q1", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q2", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q3", state: "Playing", payment_status: "Pending", toss: 0 },
        { user_uid: "q4", state: "Playing", payment_status: "Pending", toss: 0 },
    ];
    t["rounds"] = json::array![
        [ { seating: [
            { player_uid: "p1", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "p2", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "p3", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 0 } },
        ], state: "In Progress" } ],
        [ { seating: [
            { player_uid: "q1", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "q2", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "q3", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "q4", result: { gw: 0, vp: 0.0, tp: 0 } },
        ], state: "In Progress" } ],
    ];

    let org = make_organizer();
    let cancelled = json::parse(
        &run_event(&t, &json::object! { type: "CancelRound", round: 0 }, &org).expect("cancel 0"),
    )
    .unwrap();
    assert_eq!(cancelled["rounds"].len(), 2, "precondition: slot preserved");
    assert_eq!(
        cancelled["rounds"][0][0]["state"].as_str(),
        Some("Cancelled")
    );

    let out = json::parse(
        &run_event(
            &cancelled,
            &json::object! { type: "CancelRound", round: 1 },
            &org,
        )
        .expect("cancel 1"),
    )
    .unwrap();
    assert_eq!(out["rounds"].len(), 0, "both rounds gone, not one");
    assert_eq!(out["state"].as_str(), Some("Waiting"));
    assert!(
        out["standings"].is_empty(),
        "the deleted rounds take their standings with them"
    );
}

// A round nobody has played must score nothing — neither a standings row nor a TP on
// the seats, which any consumer reading raw results would pick up.
#[test]
fn test_unfinished_round_contributes_no_standings() {
    let mut t = make_tournament();
    t["state"] = "Playing".into();
    t["players"] = json::array![
        { user_uid: "p1", state: "Playing", toss: 0 },
        { user_uid: "p2", state: "Playing", toss: 0 },
        { user_uid: "p3", state: "Playing", toss: 0 },
        { user_uid: "p4", state: "Playing", toss: 0 },
        { user_uid: "q1", state: "Playing", toss: 0 },
        { user_uid: "q2", state: "Playing", toss: 0 },
        { user_uid: "q3", state: "Playing", toss: 0 },
        { user_uid: "q4", state: "Playing", toss: 0 },
        { user_uid: "q5", state: "Playing", toss: 0 },
    ];
    t["rounds"] = json::array![[
        { seating: [
            { player_uid: "p1", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "p2", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "p3", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 0 } },
        ], state: "In Progress" },
        { seating: [
            { player_uid: "q1", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "q2", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "q3", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "q4", result: { gw: 0, vp: 0.0, tp: 0 } },
            { player_uid: "q5", result: { gw: 0, vp: 0.0, tp: 0 } },
        ], state: "In Progress" },
    ]];

    let out = json::parse(
        &run_event(
            &t,
            &json::object! { type: "SwapSeats", round: 0, table1: 0, seat1: 0, table2: 0, seat2: 1 },
            &make_organizer(),
        )
        .expect("swap"),
    )
    .unwrap();

    assert!(
        out["standings"].is_empty(),
        "no standings row: {}",
        out["standings"].dump()
    );
    let tps: Vec<f64> = out["rounds"][0]
        .members()
        .flat_map(|t| t["seating"].members())
        .map(|s| s["result"]["tp"].as_f64().unwrap_or(-1.0))
        .collect();
    assert!(
        tps.iter().all(|&tp| tp == 0.0),
        "no TP on the seats either, or a raw-result reader shows 36 each: {tps:?}"
    );
}

// RestoreRound un-voids a soft-cancelled non-last round: it must re-flip the table
// back to Finished from retained scores, re-arm capped players, and leave the still-live round untouched.
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

    // Cancel then restore through the real engine — round-trip on the shipped
    // artifact, not a hand-built Cancelled fixture.
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
    assert_eq!(st(&out, "p1"), "Completed");
    assert_eq!(st(&out, "p4"), "Completed");
    assert_eq!(st(&out, "q1"), "Playing");
    assert!(
        out["standings"]
            .members()
            .any(|s| s["user_uid"].as_str() == Some("p3")),
        "restored round contributes standings again"
    );
}

// All-or-nothing: if a player seated in the cancelled round can no longer be
// reinstated, RestoreRound rejects the whole operation rather than silently leaving them out.
#[test]
fn test_restore_round_rejects_non_reinstatable_player() {
    let mut t = make_tournament();
    t["state"] = "Playing".into();
    t["online"] = true.into();
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

#[test]
fn test_gw_with_sa_adjustment() {
    let vps = vec![2.5, 1.0, 0.5, 0.5, 0.5];
    let no_adj = vec![0.0; 5];
    let gw_normal = compute_gw(&vps, &no_adj);
    assert_eq!(gw_normal[0], 1.0);

    let adj = vec![-1.0, 0.0, 0.0, 0.0, 0.0];
    let gw_adjusted = compute_gw(&vps, &adj);
    assert_eq!(gw_adjusted[0], 0.0);
}

#[test]
fn test_gw_with_sa_still_above_threshold() {
    let vps = vec![3.0, 1.0, 0.5, 0.5, 0.0];
    let adj = vec![-1.0, 0.0, 0.0, 0.0, 0.0];
    let gw = compute_gw(&vps, &adj);
    assert_eq!(gw[0], 1.0);
}

#[test]
fn test_tp_with_sa_reranks_table() {
    // JG v2 §1.1.3 Example 2: A sweeps (5VP); B/C/D/E at 0VP, E gets SA -> adjusted -1.
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
    // p1 has 2 raw VP, p2 has 0; both carry an SA on round 0, so gw is 0 for everyone
    // (p1's adjusted 1.0 < 2.0). Standings VP: p1 -> 2-1 = 1.0, p2 -> 0-1 = -1.0.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![json::array![json::object! {
        seating: [
            { player_uid: "p1", result: { gw: 0, vp: 2.0, tp: 54 } },
            { player_uid: "p2", result: { gw: 0, vp: 0.0, tp: 18 } },
            { player_uid: "p3", result: { gw: 0, vp: 0.0, tp: 18 } },
            { player_uid: "p4", result: { gw: 0, vp: 2.0, tp: 54 } },
        ],
        state: "Finished",
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
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 36 } },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 12 } },
        ],
        state: "Finished",
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
    // p2 is a proxy: unlike DQ, gw/vp/tp are NOT zeroed, yet it sorts last and earns
    // no rating. Guards the shared DQ/proxy path from a refactor that conflates the two.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![json::array![json::object! {
        seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.0, tp: 60 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 36 } },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 12 } },
        ],
        state: "Finished",
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
        (0.0, 1.0, 36.0),
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
    // p1: round0 2.5VP (table-high -> GW), round1 0VP with an SA (-1, so no GW),
    // finals 3VP/1GW (winner). VP = 2.5 + 0 + 3 - 1 = 4.5; GW = 1 + 0 + 1.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![
        json::array![json::object! {
            seating: [
                { player_uid: "p1", result: { gw: 1, vp: 2.5, tp: 60 } },
                { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 48 } },
                { player_uid: "p3", result: { gw: 0, vp: 0.0, tp: 18 } },
                { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 18 } },
                { player_uid: "p5", result: { gw: 0, vp: 0.5, tp: 36 } },
            ],
            state: "Finished",
        }],
        json::array![json::object! {
            seating: [
                { player_uid: "p1", result: { gw: 0, vp: 0.0, tp: 12 } },
                { player_uid: "p2", result: { gw: 0, vp: 2.0, tp: 60 } },
                { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 } },
                { player_uid: "p4", result: { gw: 0, vp: 1.0, tp: 36 } },
                { player_uid: "p5", result: { gw: 0, vp: 1.0, tp: 36 } },
            ],
            state: "Finished",
        }],
    ];
    tournament["finals"] = json::object! {
        seating: [
            { player_uid: "p1", result: { gw: 1, vp: 3.0, tp: 60 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 42 } },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 42 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 18 } },
            { player_uid: "p5", result: { gw: 0, vp: 0.0, tp: 18 } },
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
    // An SA referencing a nonexistent round must not double-penalize the synced VP.
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
    // No-final VEKN import: rounds/finals absent, but the sheet flags its top five
    // as an import does, so a final was played and the win GW (+1) is credited.
    let mut tournament = make_tournament();
    tournament["winner"] = "p1".into();
    tournament["standings"] = json::array![
        json::object! { user_uid: "p1", gw: 1.0, vp: 3.0, tp: 90, finalist: true },
        json::object! { user_uid: "p2", gw: 0.0, vp: 2.0, tp: 60, finalist: true },
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

    tournament["standings"] = json::array![
        json::object! { user_uid: "p1", gw: 1.0, vp: 3.0, tp: 90 },
        json::object! { user_uid: "p2", gw: 0.0, vp: 2.0, tp: 60 },
    ];
    assert_eq!(
        super::compute_rating_vp_gw(&tournament, &empty, "p1"),
        (3.0, 1.0),
        "a crowned top seat evidences no final, so no tournament-win GW"
    );
}

#[test]
fn test_standings_vp_sa_ignores_lifted_redirects_unplayed_round() {
    // A lifted SA must not penalize. An active SA whose stored round p1 never played
    // (round 1; only round 0 exists) redirects to round 0 (JG v2 §1.1.3: never a future round).
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![json::array![json::object! {
        seating: [
            { player_uid: "p1", result: { gw: 0, vp: 1.5, tp: 60 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 42 } },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 42 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 12 } },
            { player_uid: "p5", result: { gw: 0, vp: 0.5, tp: 24 } },
        ],
        state: "Finished",
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
    // p1 plays round 0 only. An SA stored on round 1 (never played) must redirect to
    // round 0: raw 2.5 VP would take the GW, but the redirected -1 drops it to 1.5.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![
        json::array![json::object! {
            seating: [
                { player_uid: "p1", result: { gw: 1, vp: 2.5, tp: 60 } },
                { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 48 } },
                { player_uid: "p3", result: { gw: 0, vp: 0.0, tp: 18 } },
                { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 18 } },
                { player_uid: "p5", result: { gw: 0, vp: 0.5, tp: 36 } },
            ],
            state: "Finished",
        }],
        json::array![json::object! {
            seating: [
                { player_uid: "p2", result: { gw: 0, vp: 0.0, tp: 12 } },
                { player_uid: "p3", result: { gw: 1, vp: 2.0, tp: 60 } },
                { player_uid: "p4", result: { gw: 0, vp: 1.0, tp: 36 } },
                { player_uid: "p5", result: { gw: 0, vp: 1.0, tp: 36 } },
            ],
            state: "Finished",
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
fn test_rating_vp_gw_finals_sa_lands_on_finals() {
    // A finals-round SA (round_number == rounds_len sentinel) sticks on the finals: prelim
    // GW is kept (no penalty there) while -1 VP hits the rating total. VP = 2.5+3.0-1.0 = 4.5; GW = 1+1 = 2.0.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![json::array![json::object! {
        seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.5, tp: 60 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 48 } },
            { player_uid: "p3", result: { gw: 0, vp: 0.0, tp: 18 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 18 } },
            { player_uid: "p5", result: { gw: 0, vp: 0.5, tp: 36 } },
        ],
        state: "Finished",
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
    assert_eq!(vp, 4.5, "prelim 2.5 + finals 3.0 - 1.0 finals SA");
    assert_eq!(
        gw, 2.0,
        "prelim GW kept (SA no longer redirected there) + finals GW (stored)"
    );
}

#[test]
fn test_finals_sa_rescores_finals_and_rederives_winner() {
    // Finals scored BEFORE the SA crowned p1 on raw VP; an SA then lands on the finals
    // sentinel round, dropping p1 below p2 — update_standings must rewrite the stored finals GW and re-derive the winner.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![json::array![json::object! {
        seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.5, tp: 60 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 48 } },
            { player_uid: "p3", result: { gw: 0, vp: 0.0, tp: 18 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 18 } },
            { player_uid: "p5", result: { gw: 0, vp: 0.5, tp: 36 } },
        ],
        state: "Finished",
    }]];
    tournament["finals"] = json::object! {
        state: "Finished",
        seed_order: ["p1", "p2", "p3", "p4", "p5"],
        seating: [
            { player_uid: "p1", result: { gw: 0, vp: 2.0, tp: 54 } },
            { player_uid: "p2", result: { gw: 0, vp: 2.0, tp: 54 } },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 18 } },
            { player_uid: "p5", result: { gw: 0, vp: 0.0, tp: 18 } },
        ],
    };
    tournament["winner"] = "p1".into();
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
    super::standings::update_standings(&mut tournament, &sanctions);
    assert_eq!(
        tournament["winner"].as_str(),
        Some("p2"),
        "adjusted finals VP re-derives the winner"
    );
    assert_eq!(
        tournament["finals"]["seating"][0]["result"]["gw"].as_f64(),
        Some(0.0),
        "p1's stored finals GW rewritten"
    );
    assert_eq!(
        tournament["finals"]["seating"][1]["result"]["gw"].as_f64(),
        Some(1.0),
        "p2 holds the refreshed finals GW"
    );
    let p1 = tournament["standings"]
        .members()
        .find(|s| s["user_uid"].as_str() == Some("p1"))
        .unwrap();
    assert_eq!(
        p1["vp"].as_f64(),
        Some(2.5),
        "prelim standings VP untouched by a finals-round SA"
    );
}

#[test]
fn test_standings_recompute_picks_up_late_sa() {
    // The round was scored BEFORE the SA (stale seat still stores gw=1, tp=60). Standings
    // must recompute from raw VP + the SA — p1 loses the GW and the table re-ranks TP.
    let mut tournament = make_tournament();
    tournament["rounds"] = json::array![json::array![json::object! {
        seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.5, tp: 60 } },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 48 } },
            { player_uid: "p3", result: { gw: 0, vp: 0.0, tp: 18 } },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 18 } },
            { player_uid: "p5", result: { gw: 0, vp: 0.5, tp: 36 } },
        ],
        state: "Finished",
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
    // Adjusted VPs: p1=1.5, p2=1.0, p5=0.5, p3=p4=0.
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
    // p3/p4 tie 4th-5th on adjusted 0 -> (24+12)/2 = 18 each.
    assert_eq!(get("p3").tp, 18.0);
}

// An SA whose stored round gets soft-cancelled must penalize VP and the GW/TP cascade on the
// SAME surviving round (`seated_in` skips Cancelled); `gw` is the witness, `vp` stays 1.5 either way.
#[test]
fn test_sa_on_soft_cancelled_round_penalizes_vp_and_gw_together() {
    let mut t = make_tournament();
    t["state"] = "Playing".into();
    // Round 0 finished (later soft-cancelled), round 1 finished; p1..p5 seated in both so the
    // SA tagged on round 0 has a surviving round to redirect onto. Distinct toss for deterministic ranking.
    // Cancelling round 0 leaves every surviving table finished, so the tournament lands in Waiting.
    t["players"] = json::array![
        { user_uid: "p1", state: "Playing", payment_status: "Pending", toss: 5 },
        { user_uid: "p2", state: "Playing", payment_status: "Pending", toss: 4 },
        { user_uid: "p3", state: "Playing", payment_status: "Pending", toss: 3 },
        { user_uid: "p4", state: "Playing", payment_status: "Pending", toss: 2 },
        { user_uid: "p5", state: "Playing", payment_status: "Pending", toss: 1 },
    ];
    t["rounds"] = json::array![
        [ { seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.5, tp: 60 }, judge_uid: "" },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 48 }, judge_uid: "" },
            { player_uid: "p3", result: { gw: 0, vp: 0.0, tp: 18 }, judge_uid: "" },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 18 }, judge_uid: "" },
            { player_uid: "p5", result: { gw: 0, vp: 0.5, tp: 36 }, judge_uid: "" },
        ], state: "Finished", override: json::Null } ],
        [ { seating: [
            { player_uid: "p1", result: { gw: 1, vp: 2.5, tp: 60 }, judge_uid: "" },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 48 }, judge_uid: "" },
            { player_uid: "p3", result: { gw: 0, vp: 0.0, tp: 18 }, judge_uid: "" },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 18 }, judge_uid: "" },
            { player_uid: "p5", result: { gw: 0, vp: 0.5, tp: 36 }, judge_uid: "" },
        ], state: "Finished", override: json::Null } ],
    ];

    // Soft-cancel round 0 through the real engine: its tables flip to Cancelled with
    // their seating intact.
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
    assert_eq!(cancelled["rounds"].len(), 2, "the slot survives the cancel");

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
fn test_expired_suspension_does_not_block_checkin() {
    // The engine honors expires_at (via actor.now): a suspension expired at/before now
    // is auto-lifted so CheckIn passes, while one expiring in the future still rejects.
    let mut tournament = make_tournament();
    tournament["state"] = "Waiting".into();
    tournament["players"] = json::array![
        { user_uid: "p1", state: "Registered", payment_status: "Pending", toss: 0 },
    ];
    let event = json::object! { type: "CheckIn", player_uid: "p1" };
    let mut actor = make_organizer();
    actor["now"] = "2026-07-08T00:00:00+00:00".into();

    let expired = json::array![
        { user_uid: "p1", level: "suspension", expires_at: "2026-06-01T00:00:00+00:00", lifted_at: json::Null, deleted_at: json::Null }
    ];
    let ok = process_tournament_event(
        &tournament.dump(),
        &event.dump(),
        &actor.dump(),
        &expired.dump(),
        &no_decks(),
    );
    assert!(ok.is_ok(), "expired suspension must not block check-in");

    let active = json::array![
        { user_uid: "p1", level: "suspension", expires_at: "2026-08-01T00:00:00+00:00", lifted_at: json::Null, deleted_at: json::Null }
    ];
    let err = process_tournament_event(
        &tournament.dump(),
        &event.dump(),
        &actor.dump(),
        &active.dump(),
        &no_decks(),
    );
    assert!(
        err.is_err() && err.unwrap_err().to_string().contains("suspended"),
        "unexpired suspension must still block check-in"
    );
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
fn test_reopen_tournament_without_finals() {
    // No final to return to: back to check-in, and the winner an archival import
    // set without one survives.
    let mut tournament = make_tournament();
    tournament["state"] = "Finished".into();
    tournament["winner"] = "p1".into();
    tournament["players"] = json::array![
        { user_uid: "p1", state: "Finished", payment_status: "Pending", toss: 0 },
        { user_uid: "p2", state: "Disqualified", payment_status: "Pending", toss: 0 },
    ];
    let event = json::object! { type: "ReopenTournament" };
    let actor = make_organizer();
    let result = run_event(&tournament, &event, &actor);
    assert!(result.is_ok());
    let updated = json::parse(&result.unwrap()).unwrap();
    assert_eq!(updated["state"].as_str(), Some("Waiting"));
    assert_eq!(updated["players"][0]["state"].as_str(), Some("Checked-in"));
    assert_eq!(
        updated["players"][1]["state"].as_str(),
        Some("Disqualified")
    ); // preserved
    assert_eq!(updated["winner"].as_str(), Some("p1"));
}

/// A tournament finished on a played final: p1-p5 the finalists, p6 at the
/// three-round cap, p7 and p8 one round in.
fn finished_with_finals() -> JsonValue {
    let mut t = make_tournament();
    t["state"] = "Finished".into();
    t["winner"] = "p1".into();
    t["decklists_mode"] = "Winner".into();
    t["players"] = json::array![
        { user_uid: "p1", state: "Finished", payment_status: "Pending", toss: 0, finalist: true },
        { user_uid: "p2", state: "Finished", payment_status: "Pending", toss: 0, finalist: true },
        { user_uid: "p3", state: "Finished", payment_status: "Pending", toss: 0, finalist: true },
        { user_uid: "p4", state: "Finished", payment_status: "Pending", toss: 0, finalist: true },
        { user_uid: "p5", state: "Finished", payment_status: "Pending", toss: 0, finalist: true },
        { user_uid: "p6", state: "Finished", payment_status: "Pending", toss: 0, finalist: false },
        { user_uid: "p7", state: "Finished", payment_status: "Pending", toss: 0, finalist: false },
        { user_uid: "p8", state: "Finished", payment_status: "Pending", toss: 0, finalist: false },
    ];
    let table = |a: &str, b: &str, c: &str, d: &str| {
        json::object! {
            seating: [
                { player_uid: a, result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                { player_uid: b, result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                { player_uid: c, result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                { player_uid: d, result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
            ],
            state: "Finished",
            override: json::Null,
        }
    };
    t["rounds"] = json::array![
        [table("p1", "p2", "p3", "p4"), table("p5", "p6", "p7", "p8")],
        [table("p1", "p2", "p5", "p6")],
        [table("p1", "p2", "p5", "p6")],
    ];
    t["finals"] = json::object! {
        seating: [
            { player_uid: "p1", result: { gw: 1, vp: 3.0, tp: 60 }, judge_uid: "" },
            { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 12 }, judge_uid: "" },
            { player_uid: "p5", result: { gw: 0, vp: 0.0, tp: 12 }, judge_uid: "" },
        ],
        state: "Finished",
        override: json::Null,
        seed_order: ["p1", "p2", "p3", "p4", "p5"],
    };
    t
}

#[test]
fn test_reopen_tournament_keeps_the_final() {
    let tournament = finished_with_finals();
    let decks = json::array![
        { uid: "d1", user_uid: "p1", tournament_uid: "test-tournament", round: 3, public: true },
    ];
    let event = json::object! { type: "ReopenTournament" };
    let (updated_json, deck_ops) =
        run_event_with_decks(&tournament, &event, &make_organizer(), &decks.dump()).unwrap();
    let updated = json::parse(&updated_json).unwrap();

    assert_eq!(updated["state"].as_str(), Some("Playing"));
    assert_eq!(updated["winner"].as_str(), Some("p1"));
    assert_eq!(updated["finals"]["seating"].len(), 5);
    assert_eq!(updated["finals"]["state"].as_str(), Some("Finished"));
    for uid in ["p1", "p2", "p3", "p4", "p5"] {
        assert_eq!(player_state(&updated, uid), "Playing");
    }
    assert!(updated["players"][0]["finalist"].as_bool().unwrap_or(false));
    assert_eq!(player_state(&updated, "p6"), "Completed"); // at the max_rounds cap
    assert_eq!(player_state(&updated, "p7"), "Checked-in");

    // The finals stamp survives — only CancelFinals releases it.
    assert!(!deck_ops
        .members()
        .any(|op| op["op"].as_str() == Some("set_round")));
    let publics: Vec<bool> = deck_ops
        .members()
        .filter(|op| op["op"].as_str() == Some("set_public"))
        .map(|op| op["public"].as_bool().unwrap_or(true))
        .collect();
    assert_eq!(publics, vec![false]);
}

#[test]
fn test_finish_finals_publishes_the_winner_deck() {
    // Publication is derived from the Finished state, so it must come back when the
    // organizer re-finishes a final they reopened to correct.
    let mut tournament = finished_with_finals();
    tournament["state"] = "Playing".into();
    let decks = json::array![
        { uid: "d1", user_uid: "p1", tournament_uid: "test-tournament", round: 3, public: false },
        { uid: "d2", user_uid: "p2", tournament_uid: "test-tournament", round: 3, public: false },
    ];
    let event = json::object! { type: "FinishFinals" };
    let (updated_json, deck_ops) =
        run_event_with_decks(&tournament, &event, &make_organizer(), &decks.dump()).unwrap();
    let updated = json::parse(&updated_json).unwrap();

    assert_eq!(updated["state"].as_str(), Some("Finished"));
    assert_eq!(updated["winner"].as_str(), Some("p1"));
    let published: Vec<&str> = deck_ops
        .members()
        .filter(|op| op["op"].as_str() == Some("set_public"))
        .filter(|op| op["public"].as_bool().unwrap_or(false))
        .filter_map(|op| op["deck_uid"].as_str())
        .collect();
    assert_eq!(published, vec!["d1"]); // decklists_mode Winner
}

/// Build a tournament in Playing state with one round of 2 tables of 4
fn player_state(tournament: &JsonValue, uid: &str) -> String {
    tournament["players"]
        .members()
        .find(|p| p["user_uid"].as_str() == Some(uid))
        .and_then(|p| p["state"].as_str())
        .unwrap_or("")
        .to_string()
}

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
                    { player_uid: "p1", result: { gw: 1, vp: 2.0, tp: 60 }, judge_uid: "" },
                    { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
                    { player_uid: "p3", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
                    { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 12 }, judge_uid: "" },
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
fn test_seat_player_earlier_live_round() {
    // Two rounds in flight (parallel/open play): an EARLIER round that is
    // still live can take a substitute; a finished earlier round cannot.
    let mut t = tournament_with_round();
    t["players"]
        .push(json::object! { user_uid: "p9", state: "Registered", payment_status: "Pending", toss: 0 })
        .unwrap();
    t["rounds"]
        .push(json::array![{
            seating: [
                { player_uid: "p1", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                { player_uid: "p2", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                { player_uid: "p3", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                { player_uid: "p4", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
            ],
            state: "In Progress",
            override: json::Null,
        }])
        .unwrap();
    let org = make_organizer();

    // Round 0 still has an In Progress table → explicit round: 0 seat works.
    let event = json::object! { type: "SeatPlayer", player_uid: "p9", table: 1, seat: 4, round: 0 };
    let updated = json::parse(&run_event(&t, &event, &org).unwrap()).unwrap();
    assert_eq!(updated["rounds"][0][1]["seating"].len(), 5);
    assert_eq!(updated["players"][8]["state"].as_str(), Some("Playing"));

    // Once every table of that earlier round is finished, it is closed.
    let mut done = updated.clone();
    done["rounds"][0][1]["state"] = "Finished".into();
    done["players"]
        .push(json::object! { user_uid: "p10", state: "Registered", payment_status: "Pending", toss: 0 })
        .unwrap();
    let event =
        json::object! { type: "SeatPlayer", player_uid: "p10", table: 0, seat: 4, round: 0 };
    let result = run_event(&done, &event, &org);
    assert!(result.is_err());
    assert!(result.unwrap_err().to_string().contains("live round"));
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

// StartFinals selects the top-5 *eligible* players: a capped player resting in `Completed`
// is still a finalist; a withdrawn player in `Finished` is excluded and the next-ranked qualifier is promoted.
#[test]
fn test_start_finals_includes_completed_excludes_withdrawn() {
    let mut t = make_tournament();
    t["state"] = "Waiting".into();
    // Two single-table rounds (>=2 rounds gate); each table is [2,1,1,1,0], a valid oust
    // sequence. Distinct toss values keep the cutoff free of unbroken ties.
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

// RandomToss must leave the finals seed order total (§3.1: any of the top five
// rankings), so StartFinals always follows it. Two withdrawals push the qualifying
// five past the raw top five, and one tied group is already half-tossed by hand.
#[test]
fn test_random_toss_orders_the_qualifying_five() {
    let mut t = make_tournament();
    t["state"] = "Waiting".into();
    // Raw standings: p2(gw1 vp3) p1(gw1 vp2) p3(vp2) {p4,p6,p7}(vp1) {p5,p8}(vp0).
    t["players"] = json::array![
        { user_uid: "p1", state: "Finished", payment_status: "Pending", toss: 0 },
        { user_uid: "p2", state: "Finished", payment_status: "Pending", toss: 0 },
        { user_uid: "p3", state: "Playing",  payment_status: "Pending", toss: 0 },
        { user_uid: "p4", state: "Playing",  payment_status: "Pending", toss: 1 },
        { user_uid: "p5", state: "Playing",  payment_status: "Pending", toss: 0 },
        { user_uid: "p6", state: "Playing",  payment_status: "Pending", toss: 0 },
        { user_uid: "p7", state: "Playing",  payment_status: "Pending", toss: 0 },
        { user_uid: "p8", state: "Playing",  payment_status: "Pending", toss: 0 },
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
            { player_uid: "p6", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p7", result: { gw: 0, vp: 1.0, tp: 36 }, judge_uid: "" },
            { player_uid: "p8", result: { gw: 0, vp: 0.0, tp: 12 }, judge_uid: "" },
        ], state: "Finished", override: json::Null } ],
    ];
    let org = make_organizer();

    let tossed =
        json::parse(&run_event(&t, &json::object! { type: "RandomToss" }, &org).unwrap()).unwrap();

    // p1 and p2 withdrew, so the qualifying five are p3, {p4,p6,p7} and one of the
    // {p5,p8} pair — a group the raw top-five zone never reached.
    let toss_of = |uid: &str| {
        tossed["players"]
            .members()
            .find(|p| p["user_uid"].as_str() == Some(uid))
            .unwrap()["toss"]
            .as_u32()
            .unwrap()
    };
    for group in [["p4", "p6", "p7"].as_slice(), ["p5", "p8"].as_slice()] {
        let tosses: std::collections::HashSet<u32> = group.iter().map(|u| toss_of(u)).collect();
        assert_eq!(
            tosses.len(),
            group.len(),
            "{group:?} must come out of the toss distinctly ordered, got {tosses:?}"
        );
        assert!(!tosses.contains(&0), "{group:?} left an untossed member");
    }

    let started =
        json::parse(&run_event(&tossed, &json::object! { type: "StartFinals" }, &org).unwrap())
            .unwrap();
    let seated: std::collections::HashSet<&str> = started["finals"]["seating"]
        .members()
        .filter_map(|s| s["player_uid"].as_str())
        .collect();
    assert_eq!(seated.len(), 5);
    assert!(["p3", "p4", "p6", "p7"].iter().all(|u| seated.contains(u)));
    assert!(
        seated.contains("p5") ^ seated.contains("p8"),
        "the toss must seat exactly one of the tied pair, got {seated:?}"
    );
}

// The finals/toss two-round minimum must count *played* rounds via `count_played_rounds`, not
// `rounds.len()` — a cancelled round must not satisfy it. SetToss/RandomToss share the same helper, so this one test guards all three.
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
    assert_eq!(
        cancelled["rounds"][0][0]["state"].as_str(),
        Some("Cancelled")
    );
    assert_eq!(
        cancelled["rounds"][1][0]["state"].as_str(),
        Some("Finished")
    );

    // The gate counts played rounds (1), not rounds.len() (2), and refuses the finals.
    let err = run_event(&cancelled, &json::object! { type: "StartFinals" }, &org).unwrap_err();
    assert!(matches!(err, EngineError::FinalsMinRounds));
}

// CancelFinals reverts a seated finals back to Waiting so a no-show finalist can be dropped and
// the field re-seated. Capped finalists must return to Completed (not Checked-in), not re-armed.
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
    assert!(result.unwrap_err().to_string().contains("Player not found"));
}

#[test]
fn test_alter_seating_adds_and_removes_in_one_save() {
    let mut tournament = tournament_with_round();
    tournament["players"]
        .push(json::object! { user_uid: "p9", state: "Registered", payment_status: "Pending", toss: 0 })
        .unwrap();
    // p1 out of table 0, p9 (never in this round) in — one payload, one event.
    let event = json::object! {
        type: "AlterSeating",
        round: 0,
        seating: [["p9", "p2", "p3", "p4"], ["p5", "p6", "p7", "p8"]],
    };
    let actor = make_organizer();
    let updated = json::parse(&run_event(&tournament, &event, &actor).unwrap()).unwrap();

    assert_eq!(
        updated["rounds"][0][0]["seating"][0]["player_uid"].as_str(),
        Some("p9")
    );
    assert_eq!(
        updated["rounds"][0][0]["seating"][0]["result"]["vp"].as_f64(),
        Some(0.0)
    );
    assert_eq!(
        updated["rounds"][0][0]["seating"][1]["result"]["vp"].as_f64(),
        Some(1.0)
    );
    assert_eq!(player_state(&updated, "p9"), "Playing");
    assert_eq!(player_state(&updated, "p1"), "Registered");
}

#[test]
fn test_alter_seating_seating_a_disqualified_player_keeps_them_disqualified() {
    let mut tournament = tournament_with_round();
    tournament["players"]
        .push(json::object! { user_uid: "p9", state: "Disqualified", payment_status: "Pending", toss: 0 })
        .unwrap();
    let event = json::object! {
        type: "AlterSeating",
        round: 0,
        seating: [["p9", "p2", "p3", "p4"], ["p5", "p6", "p7", "p8"]],
    };
    let actor = make_organizer();
    let updated = json::parse(&run_event(&tournament, &event, &actor).unwrap()).unwrap();

    assert_eq!(
        updated["rounds"][0][0]["seating"][0]["player_uid"].as_str(),
        Some("p9")
    );
    assert_eq!(player_state(&updated, "p9"), "Disqualified");
}

#[test]
fn test_alter_seating_unseating_a_dropped_player_keeps_them_finished() {
    let mut tournament = tournament_with_round();
    // Dropping out never vacates a seat, so p1 is seated while Finished.
    tournament["players"][0]["state"] = "Finished".into();
    let event = json::object! {
        type: "AlterSeating",
        round: 0,
        seating: [[], ["p5", "p6", "p7", "p8"]],
    };
    let actor = make_organizer();
    let updated = json::parse(&run_event(&tournament, &event, &actor).unwrap()).unwrap();

    assert_eq!(player_state(&updated, "p1"), "Finished");
    assert_eq!(player_state(&updated, "p2"), "Registered");
}

#[test]
fn test_alter_seating_unseating_keeps_a_parallel_round_player_playing() {
    let mut tournament = tournament_with_round();
    // Online parallel play: p1 is also seated in a still-live round 1.
    for uid in ["p9", "p10", "p11"] {
        tournament["players"]
            .push(json::object! { user_uid: uid, state: "Playing", payment_status: "Pending", toss: 0 })
            .unwrap();
    }
    tournament["rounds"]
        .push(json::array![{
            seating: [
                { player_uid: "p1", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                { player_uid: "p9", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                { player_uid: "p10", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                { player_uid: "p11", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
            ],
            state: "In Progress",
            override: json::Null,
        }])
        .unwrap();
    let event = json::object! {
        type: "AlterSeating",
        round: 0,
        seating: [[], ["p5", "p6", "p7", "p8"]],
    };
    let actor = make_organizer();
    let updated = json::parse(&run_event(&tournament, &event, &actor).unwrap()).unwrap();

    assert_eq!(player_state(&updated, "p1"), "Playing");
    assert_eq!(player_state(&updated, "p2"), "Registered");
}

#[test]
fn test_alter_seating_on_a_finished_round_touches_no_player_state() {
    let mut tournament = tournament_with_round();
    tournament["rounds"][0][1]["state"] = "Finished".into();
    tournament["players"]
        .push(json::object! { user_uid: "p9", state: "Registered", payment_status: "Pending", toss: 0 })
        .unwrap();
    // Correcting the record of a round that is over: no player state is correct
    // for it, so none is written.
    let event = json::object! {
        type: "AlterSeating",
        round: 0,
        seating: [["p9", "p2", "p3", "p4"], ["p5", "p6", "p7", "p8"]],
    };
    let actor = make_organizer();
    let updated = json::parse(&run_event(&tournament, &event, &actor).unwrap()).unwrap();

    assert_eq!(
        updated["rounds"][0][0]["seating"][0]["player_uid"].as_str(),
        Some("p9")
    );
    assert_eq!(player_state(&updated, "p9"), "Registered");
    assert_eq!(player_state(&updated, "p1"), "Playing");
}

#[test]
fn test_unseat_player_keeps_a_dropped_player_finished() {
    let mut tournament = tournament_with_round();
    tournament["players"][4]["state"] = "Finished".into();
    let event = json::object! { type: "UnseatPlayer", player_uid: "p5", round: 0 };
    let actor = make_organizer();
    let updated = json::parse(&run_event(&tournament, &event, &actor).unwrap()).unwrap();

    assert_eq!(player_state(&updated, "p5"), "Finished");
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

// SwapSeats swaps player_uids but leaves each seat's result in place, so in Finished state
// (where no later FinishRound refreshes standings) the stored standings must follow the swap.
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
    // Pre-swap standings, as they stood when the tournament finished — pre-seeding them pins
    // staleness (values passed through untouched), not absence.
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
fn test_update_config_rank_forbids_proxies() {
    // Setting a championship rank while proxies are on (or vice versa) is
    // VEKN-illegal — the gate must see the MERGED config, not just the patch.
    let mut tournament = make_tournament();
    tournament["proxies"] = true.into();
    let event = json::object! {
        type: "UpdateConfig",
        config: { rank: "National Championship" },
    };
    let actor = make_organizer();
    let result = run_event(&tournament, &event, &actor);
    assert!(result.is_err());
    assert!(result.unwrap_err().to_string().contains("Proxies"));
}

#[test]
fn test_update_config_v5_forbids_championship_rank() {
    // No V5 championship type on vekn.net — reject from either side of the merged
    // view; Limited championships stay legal.
    let actor = make_organizer();
    let ranked = |cfg: json::JsonValue| json::object! { type: "UpdateConfig", config: cfg };

    let mut v5 = make_tournament();
    v5["format"] = "V5".into();
    let err = run_event(
        &v5,
        &ranked(json::object! { rank: "National Championship" }),
        &actor,
    )
    .unwrap_err();
    assert_eq!(err.code(), "tournament.format_forbids_rank");

    let mut nc = make_tournament();
    nc["rank"] = "Continental Championship".into();
    let err = run_event(&nc, &ranked(json::object! { format: "V5" }), &actor).unwrap_err();
    assert_eq!(err.code(), "tournament.format_forbids_rank");

    let mut limited = make_tournament();
    limited["format"] = "Limited".into();
    assert!(run_event(
        &limited,
        &ranked(json::object! { rank: "National Championship" }),
        &actor
    )
    .is_ok());
}

#[test]
fn test_update_config_finish_before_start() {
    // A finish-only patch must be ordered against the STORED start, and the two sides carry
    // different precisions (form posts minutes, store keeps seconds), so only a real inversion fails.
    let mut tournament = make_tournament();
    tournament["start"] = "2026-06-01T10:00:00".into();
    let actor = make_organizer();
    let patch = |finish: &str| {
        json::object! { type: "UpdateConfig", config: { finish: finish } }
    };

    let err = run_event(&tournament, &patch("2026-06-01T09:00"), &actor).unwrap_err();
    assert_eq!(err.code(), "tournament.finish_before_start");
    assert!(run_event(&tournament, &patch("2026-06-01T10:00"), &actor).is_ok());
    assert!(run_event(&tournament, &patch("2026-06-01T18:00"), &actor).is_ok());
}

#[test]
fn test_update_config_vekn_frozen_identity() {
    // After VEKN publication rank/format/start are frozen; same-value writes
    // and non-identity fields stay editable.
    let mut tournament = make_tournament();
    tournament["external_ids"] = json::object! { vekn: "12345" };
    let event = json::object! {
        type: "UpdateConfig",
        config: { format: "V5" },
    };
    let actor = make_organizer();
    let result = run_event(&tournament, &event, &actor);
    assert!(result.is_err());
    assert!(result
        .unwrap_err()
        .to_string()
        .contains("published to VEKN"));

    // Same value + venue edit passes
    let format = tournament["format"]
        .as_str()
        .unwrap_or("Standard")
        .to_string();
    let event = json::object! {
        type: "UpdateConfig",
        config: { format: format, venue: "New Venue" },
    };
    let result = run_event(&tournament, &event, &actor);
    assert!(result.is_ok());
    let updated = json::parse(&result.unwrap()).unwrap();
    assert_eq!(updated["venue"].as_str(), Some("New Venue"));
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

#[test]
fn test_checkin_refreshes_display_name_of_rostered_player() {
    // The walk-in arm always stamped it; a player already on the roster — what
    // the bot actually hits — kept the name they registered under.
    let tournament = tournament_with_player("Waiting");
    let event = json::object! {
        type: "CheckIn", player_uid: "player-1", display_name: "GuildNick"
    };
    let actor = make_organizer();

    let updated = json::parse(&run_event(&tournament, &event, &actor).unwrap()).unwrap();
    assert_eq!(
        updated["players"][0]["display_name"].as_str(),
        Some("GuildNick")
    );
}

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

fn multideck_tournament(state: &str, rounds_played: usize) -> JsonValue {
    let mut t = make_tournament();
    t["state"] = state.into();
    t["multideck"] = true.into();
    t["players"] = json::array![
        { user_uid: "player-1", state: "Checked-in", payment_status: "Pending", toss: 0 },
    ];
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
    // A played deck already stamped: the upload is the next pending one.
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
fn test_multideck_player_upload_lands_pending() {
    // A player writes their pending deck and never a round: the round the deck
    // is played in is stamped at seating, so a named one is dropped.
    let tournament = multideck_tournament("Playing", 1);
    let event = json::object! {
        type: "UpsertDeck",
        player_uid: "player-1",
        deck: { name: "Late Deck", author: "", comments: "", cards: {}, round: 0 },
        multideck: true,
    };
    let actor = make_player("player-1");
    let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, "[]").unwrap();
    assert_eq!(deck_ops.len(), 1);
    assert_eq!(deck_ops[0]["op"].as_str(), Some("upsert"));
    assert!(deck_ops[0]["deck"]["round"].is_null());
}

#[test]
fn test_multideck_delete_pending() {
    // The pending deck (no round) is the only one a player may drop.
    let tournament = multideck_tournament("Playing", 1);
    let decks = r#"[{"user_uid": "player-1", "round": 0, "uid": "d0"}, {"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
    let event = json::object! {
        type: "DeleteDeck",
        player_uid: "player-1",
        deck_index: json::Null,
        multideck: true,
    };
    let actor = make_player("player-1");
    let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, decks).unwrap();
    assert_eq!(deck_ops.len(), 1);
    assert_eq!(deck_ops[0]["op"].as_str(), Some("delete"));
    assert!(deck_ops[0]["deck_index"].is_null());
}

#[test]
fn test_multideck_delete_locked_blocked() {
    // Round 0 was played, so its deck is stamped and cannot be dropped.
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
fn test_multideck_delete_stamped_blocked() {
    // A stamped deck is a deck that was played: immutable whatever the state.
    let tournament = multideck_tournament("Waiting", 1);
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
fn test_multideck_lifecycle() {
    // Upload deck at round 0, start round -> round 0 deck locked
    let mut tournament = multideck_tournament("Waiting", 0);
    tournament["players"] = json::array![
        { user_uid: "p0", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p2", state: "Checked-in", payment_status: "Pending", toss: 0 },
        { user_uid: "p3", state: "Checked-in", payment_status: "Pending", toss: 0 },
    ];

    let event = json::object! {
        type: "UpsertDeck",
        player_uid: "p0",
        deck: { name: "Round 1 Deck", author: "", comments: "", cards: {} },
        multideck: true,
    };
    let actor = make_player("p0");
    let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, "[]").unwrap();
    assert_eq!(deck_ops.len(), 1);

    let start_event =
        json::parse(r#"{"type": "StartRound", "seating": [["p0","p1","p2","p3"]]}"#).unwrap();
    let org = make_organizer();
    let result = run_event(&tournament, &start_event, &org).unwrap();
    let updated = json::parse(&result).unwrap();
    assert_eq!(updated["state"].as_str(), Some("Playing"));
    assert_eq!(updated["rounds"].len(), 1);

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

#[test]
fn test_seated_organizer_score_does_not_lock_tablemates() {
    // No judge stamp when seated, or the judge locks their own tablemates out.
    let mut t = tournament_with_round();
    t["players"][4]["user_uid"] = "organizer-1".into();
    t["rounds"][0][1]["seating"][0]["player_uid"] = "organizer-1".into();

    let event = json::object! {
        type: "SetScore",
        round: 0,
        table: 1,
        scores: [ { player_uid: "organizer-1", vp: 2.0 } ],
    };
    let scored = json::parse(&run_event(&t, &event, &make_organizer()).unwrap()).unwrap();
    assert_eq!(
        scored["rounds"][0][1]["seating"][0]["judge_uid"].as_str(),
        Some("")
    );

    // The invariant: a tablemate can still score afterwards.
    let follow_up = json::object! {
        type: "SetScore",
        round: 0,
        table: 1,
        scores: [ { player_uid: "p6", vp: 1.0 } ],
    };
    assert!(run_event(&scored, &follow_up, &make_player("p6")).is_ok());
}

#[test]
fn test_dropped_player_reinstated_during_play() {
    let t = tournament_with_round();
    let drop = json::object! { type: "DropOut", player_uid: "p5" };
    let dropped = json::parse(&run_event(&t, &drop, &make_player("p5")).unwrap()).unwrap();
    assert_eq!(dropped["players"][4]["state"].as_str(), Some("Finished"));

    let back = json::object! { type: "CheckIn", player_uid: "p5" };
    let back_in = json::parse(&run_event(&dropped, &back, &make_organizer()).unwrap()).unwrap();
    // The seat was never vacated, so they resume Playing rather than await one.
    assert_eq!(back_in["players"][4]["state"].as_str(), Some("Playing"));
}

#[test]
fn test_late_arrival_checked_in_mid_round() {
    // Real tournaments take walk-ins after a round starts — seated at a short
    // table if play hasn't begun, next round otherwise. Both must reach the door.
    let mut t = tournament_with_round();
    t["players"][0]["state"] = "Registered".into();

    let known = json::object! { type: "CheckIn", player_uid: "p1" };
    let after = json::parse(&run_event(&t, &known, &make_organizer()).unwrap()).unwrap();
    assert_eq!(after["players"][0]["state"].as_str(), Some("Checked-in"));

    // Never registered at all: checking in enrols them.
    let walk_in = json::object! { type: "CheckIn", player_uid: "p99", vekn_id: "12345" };
    let after = json::parse(&run_event(&after, &walk_in, &make_organizer()).unwrap()).unwrap();
    let added = after["players"]
        .members()
        .find(|p| p["user_uid"].as_str() == Some("p99"))
        .expect("walk-in was not enrolled");
    assert_eq!(added["state"].as_str(), Some("Checked-in"));
}

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
fn test_preview_scores_match_setscore_including_sa_cascade() {
    // `preview_scores_json` and `SetScore` are two separate copies of the GW/TP cascade;
    // drive both on the same table + VPs, with an active SA, and assert equality.
    let t = waiting_after_round();
    // Table 0 seat order is p1,p2,p3,p4; p2 sweeps to the table win (VPs [0,2,1,1]).
    let sanctions = json::array![
        { user_uid: "p2", level: "standings_adjustment", round_number: 0, lifted_at: json::Null, deleted_at: json::Null },
    ];

    // Persisted path: SetScore through the real engine, with the SA in effect.
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
    let scored = json::parse(
        &process_tournament_event(
            &t.dump(),
            &event.dump(),
            &make_organizer().dump(),
            &sanctions.dump(),
            &no_decks(),
        )
        .unwrap(),
    )
    .unwrap();
    let seating = &scored["tournament"]["rounds"][0][0]["seating"];
    let stored_gw: Vec<f64> = seating
        .members()
        .map(|s| s["result"]["gw"].as_f64().unwrap())
        .collect();
    let stored_tp: Vec<f64> = seating
        .members()
        .map(|s| s["result"]["tp"].as_f64().unwrap())
        .collect();

    // Preview path: same table, same VPs, same sanctions, on the pre-score state
    // (the live-preview scenario — scores not yet persisted).
    let preview_cfg = json::object! {
        tournament: t.clone(),
        sanctions: sanctions.clone(),
        round: 0,
        table: 0,
        vps: [0.0, 2.0, 1.0, 1.0],
    };
    let preview = json::parse(&preview_scores_json(&preview_cfg.dump()).unwrap()).unwrap();
    let preview_gw: Vec<f64> = preview["gw"]
        .members()
        .map(|v| v.as_f64().unwrap())
        .collect();
    let preview_tp: Vec<f64> = preview["tp"]
        .members()
        .map(|v| v.as_f64().unwrap())
        .collect();

    assert_eq!(preview_gw, stored_gw, "preview GW must match persisted GW");
    assert_eq!(preview_tp, stored_tp, "preview TP must match persisted TP");

    // The SA must be load-bearing: it strips p2's would-be GW, so the equality above
    // exercises the cascade, not a no-op. No-SA control: p2 (adjusted 2.0) wins.
    assert_eq!(stored_gw[1], 0.0, "SA drops p2 below the 2VP GW threshold");
    let no_sa_cfg = json::object! {
        tournament: t.clone(),
        sanctions: json::array![],
        round: 0,
        table: 0,
        vps: [0.0, 2.0, 1.0, 1.0],
    };
    let no_sa = json::parse(&preview_scores_json(&no_sa_cfg.dump()).unwrap()).unwrap();
    assert_eq!(
        no_sa["gw"][1].as_f64(),
        Some(1.0),
        "without the SA p2 wins the table GW"
    );
}

#[test]
fn test_organizer_corrects_earlier_round_during_parallel_round_refreshes_standings() {
    // Online parallel rounds: round 0 finished, round 1 still in progress, tournament stays
    // Playing. Correcting a VP in the finished round 0 must still refresh stored standings.
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
    // Mid-round: table 0 scored, table 1 unscored, no stored standings (FinishRound
    // never ran). Pools must be computed from the live round results.
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
    assert_eq!(winners, vec!["p4", "p5", "p6", "p7", "p8"]);

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

#[test]
fn test_report_promos_post_finish_replaces_whole_list() {
    // ReportPromos is deliberately state-gate-free: re-submitting corrects an already-filed
    // report by replacing the whole list — not merging — and this pins the submitter default for stock source too.
    let mut tournament = make_tournament();
    tournament["state"] = "Finished".into();
    // An already-filed report the organizer is now correcting.
    tournament["promos_distributed"] =
        json::array![json::object! { promo_uid: "stale-promo", qty: 9 },];

    let event = json::object! {
        type: "ReportPromos",
        promos: [
            { promo_uid: "promo-a", qty: 3 },
            { promo_uid: "promo-b", qty: 1 },
        ],
        // stock_source_uid omitted -> defaults to the acting organizer.
    };
    let updated = json::parse(&run_event(&tournament, &event, &make_organizer()).unwrap()).unwrap();

    let rows = &updated["promos_distributed"];
    assert_eq!(rows.len(), 2, "the stale row must be replaced, not merged");
    assert_eq!(rows[0]["promo_uid"].as_str(), Some("promo-a"));
    assert_eq!(rows[0]["qty"].as_usize(), Some(3));
    assert_eq!(rows[1]["promo_uid"].as_str(), Some("promo-b"));
    assert_eq!(rows[1]["qty"].as_usize(), Some(1));
    assert_eq!(
        updated["promo_stock_source_uid"].as_str(),
        Some("organizer-1"),
        "omitted stock source defaults to the submitting organizer"
    );
}

/// A table where a card moved a VP (Life Boon merges two half-VPs into one integer)
/// is complete, not half-entered — must read RedirectedVp, not IncompleteTotal.
#[test]
fn redirected_vp_reads_as_blocked_not_unfinished() {
    let plain = [1.5, 0.0, 0.5, 0.5, 0.5];
    let boon = [2.0, 0.0, 0.5, 0.5, 0.0];
    assert_eq!(
        plain.iter().sum::<f64>(),
        boon.iter().sum::<f64>(),
        "moving a VP must not move the total"
    );
    assert_eq!(check_table_vps(&plain), None);
    assert_eq!(check_table_vps(&boon), Some(VpError::RedirectedVp));

    // Nothing entered, or barely: still just unfinished.
    assert_eq!(check_table_vps(&[0.0; 5]), Some(VpError::IncompleteTotal));
    assert_eq!(
        check_table_vps(&[1.0, 0.0, 0.0, 0.0, 0.0]),
        Some(VpError::IncompleteTotal)
    );

    assert_eq!(check_table_vps(&[5.0, 0.0, 0.0, 0.0, 0.0]), None, "sweep");
    assert_eq!(check_table_vps(&[0.5; 4]), None, "timeout, nobody ousted");
    assert_eq!(
        check_table_vps(&[3.0, 0.0, 2.5, 0.0, 0.0]),
        Some(VpError::ExcessiveTotal)
    );
}

/// A withdrawal scores half a VP (§3.7.2) and *leaves*, so the ring closes behind it
/// and a half can sit beside the full point of whoever was left standing. The oust
/// pass cannot close a ring, so it used to refuse these sheets outright.
#[test]
fn check_table_vps_accepts_withdrawal_endings() {
    // 1 ousts 2, then 3 and 4 both withdraw, leaving 1 last standing.
    assert_eq!(check_table_vps(&[2.0, 0.0, 0.5, 0.5]), None);
    // 1 ousts 2 and 3, 4 withdraws, 1 last standing.
    assert_eq!(check_table_vps(&[3.0, 0.0, 0.0, 0.5]), None);
    // 1 ousts 2 and 3 then withdraws itself, leaving 4 last standing.
    assert_eq!(check_table_vps(&[2.5, 0.0, 0.0, 1.0]), None);
    // Five seats: 1 sweeps three, 5 withdraws, 1 last standing.
    assert_eq!(check_table_vps(&[4.0, 0.0, 0.0, 0.0, 0.5]), None);
    // 1 ousts 2, 4 ousts 1, 3 withdraws, 4 last standing.
    assert_eq!(check_table_vps(&[1.0, 0.0, 0.5, 2.0]), None);

    // Still refused: three ousts leave nobody to survive against, so the fourth point
    // is the game win, not a survivor's half.
    assert!(check_table_vps(&[3.5, 0.0, 0.0, 0.0]).is_some());
    // Three seats on a full point needs three ousts, which would leave nobody to take
    // the fourth seat's survivor half.
    assert!(check_table_vps(&[1.0, 1.0, 1.0, 0.5]).is_some());
}

/// The gate is the data shape, not the mode: every legacy import is rounds-less
/// while carrying a real scored result sheet, and a correction must never
/// overwrite one.
#[test]
fn test_set_archival_results() {
    let mut tournament = make_tournament();
    tournament["state"] = "Finished".into();
    tournament["standings"] = json::array![];
    let ic = json::object! { uid: "ic-1", roles: ["IC"], is_organizer: true };
    let event = json::object! {
        type: "SetArchivalResults",
        winner: "player-1",
        players: ["player-2", "player-1"],
        reported_player_count: 42,
    };

    assert_eq!(
        run_event(&tournament, &event, &make_organizer()).unwrap_err(),
        EngineError::ArchivalResultsForbidden
    );

    let updated = json::parse(&run_event(&tournament, &event, &ic).unwrap()).unwrap();
    assert_eq!(updated["winner"], "player-1");
    assert_eq!(updated["reported_player_count"], 42);
    // Winner first, and the only finalist.
    assert_eq!(updated["standings"][0]["user_uid"], "player-1");
    assert_eq!(updated["standings"][0]["finalist"], true);
    assert_eq!(updated["standings"][1]["finalist"], false);
    assert_eq!(updated["players"].len(), 2);
    assert_eq!(crate::ratings::attested_player_count(&updated), 42);
    assert_eq!(crate::ratings::ranking_eligibility(&updated), "no_results");

    let mut scored = tournament.clone();
    scored["standings"] = json::array![json::object! { user_uid: "someone", vp: 3.0 }];
    assert_eq!(
        run_event(&scored, &event, &ic).unwrap_err(),
        EngineError::ArchivalResultsHasPlay
    );

    let mut linked = tournament.clone();
    linked["external_ids"] = json::object! { vekn: "12794" };
    assert_eq!(
        run_event(&linked, &event, &ic).unwrap_err(),
        EngineError::ArchivalResultsVeknLinked
    );

    let short = json::object! {
        type: "SetArchivalResults",
        winner: "player-1",
        players: ["player-2", "player-1"],
        reported_player_count: 1,
    };
    assert_eq!(
        run_event(&tournament, &short, &ic).unwrap_err(),
        EngineError::ArchivalResultsCountBelowRoster {
            reported: 1,
            listed: 2
        }
    );
}

#[test]
fn test_registration_past_cap_waitlists_and_bars_check_in() {
    let mut tournament = make_tournament();
    tournament["state"] = "Registration".into();
    tournament["max_players"] = 1.into();
    tournament["players"] = json::array![
        { user_uid: "p0", state: "Registered", payment_status: "Pending", toss: 0 },
    ];

    let register =
        |uid: &str| json::object! { type: "Register", user_uid: uid, vekn_id: "1000001" };
    let after_one =
        run_event(&tournament, &register("p1"), &make_player("p1")).expect("register accepted");
    let mut tournament = json::parse(&after_one).unwrap();
    assert!(tournament["players"][1]["waitlisted"].as_bool().unwrap());

    // The cap counts unwaitlisted seats, so the queue grows instead of the roster.
    let after_two =
        run_event(&tournament, &register("p2"), &make_player("p2")).expect("register accepted");
    tournament = json::parse(&after_two).unwrap();
    assert!(tournament["players"][2]["waitlisted"].as_bool().unwrap());

    tournament["state"] = "Waiting".into();
    let check_in = json::object! { type: "CheckIn", player_uid: "p1", vekn_id: "1000001" };
    assert!(matches!(
        run_event(&tournament, &check_in, &make_organizer()),
        Err(EngineError::PlayerWaitlisted)
    ));

    let promote = json::object! { type: "SetWaitlisted", player_uid: "p1", waitlisted: false };
    let promoted = run_event(&tournament, &promote, &make_organizer()).expect("promotion accepted");
    let tournament = json::parse(&promoted).unwrap();
    let checked_in =
        run_event(&tournament, &check_in, &make_organizer()).expect("check-in accepted");
    let tournament = json::parse(&checked_in).unwrap();
    assert_eq!(
        tournament["players"][1]["state"].as_str(),
        Some("Checked-in")
    );
}

#[test]
fn test_waitlisted_player_skipped_by_check_in_all_and_spared_by_no_show_sweep() {
    let mut tournament = make_tournament();
    tournament["state"] = "Waiting".into();
    tournament["players"] = json::array![
        { user_uid: "p0", state: "Registered", payment_status: "Pending", toss: 0 },
        { user_uid: "p1", state: "Registered", payment_status: "Pending", toss: 0 },
        { user_uid: "p2", state: "Registered", payment_status: "Pending", toss: 0 },
        { user_uid: "p3", state: "Registered", payment_status: "Pending", toss: 0 },
        { user_uid: "p4", state: "Registered", payment_status: "Pending", toss: 0, waitlisted: true },
    ];

    let all_in = json::object! { type: "CheckInAll" };
    let after = run_event(&tournament, &all_in, &make_organizer()).expect("check-in all accepted");
    let tournament = json::parse(&after).unwrap();
    assert_eq!(
        tournament["players"][0]["state"].as_str(),
        Some("Checked-in")
    );
    assert_eq!(
        tournament["players"][4]["state"].as_str(),
        Some("Registered")
    );

    let start =
        json::parse(r#"{"type": "StartRound", "seating": [["p0","p1","p2","p3"]]}"#).unwrap();
    let after = run_event(&tournament, &start, &make_organizer()).expect("round started");
    let tournament = json::parse(&after).unwrap();
    assert_eq!(
        tournament["players"][4]["state"].as_str(),
        Some("Registered")
    );
    assert!(tournament["players"][4]["waitlisted"].as_bool().unwrap());
}
