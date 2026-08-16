use super::measure::{build_mapping, measure_round};
use super::stagger::is_valid_table_count;
use super::*;
use std::collections::HashMap;

fn make_players(count: usize) -> Vec<String> {
    (1..=count).map(|i| format!("P{}", i)).collect()
}

#[test]
fn test_build_round_8_players() {
    let players = make_players(8);
    let round = build_round(&players);
    assert_eq!(round.len(), 2);
    assert_eq!(round[0].len(), 4);
    assert_eq!(round[1].len(), 4);
}

#[test]
fn test_build_round_9_players() {
    let players = make_players(9);
    let round = build_round(&players);
    assert_eq!(round.len(), 2);
    assert_eq!(round[0].len(), 5);
    assert_eq!(round[1].len(), 4);
}

#[test]
fn test_build_round_10_players() {
    let players = make_players(10);
    let round = build_round(&players);
    assert_eq!(round.len(), 2);
    assert_eq!(round[0].len(), 5);
    assert_eq!(round[1].len(), 5);
}

#[test]
fn test_build_round_20_players() {
    let players = make_players(20);
    let round = build_round(&players);
    assert_eq!(round.len(), 4);
    for table in &round {
        assert_eq!(table.len(), 5);
    }
}

#[test]
fn test_measure_4_player_table() {
    let round = vec![vec![
        "A".to_string(),
        "B".to_string(),
        "C".to_string(),
        "D".to_string(),
    ]];
    let mapping = build_mapping(std::slice::from_ref(&round));
    let m = measure_round(&mapping, &round);

    let a = mapping["A"];
    assert_eq!(m.get(a, a, 0), 1); // played
    assert_eq!(m.get(a, a, 1), 4); // vps available
    assert_eq!(m.get(a, a, 2), 1); // transfers (seat 1)
    assert_eq!(m.get(a, a, 3), 1); // seat 1

    let b = mapping["B"];
    assert_eq!(m.get(a, b, 0), 1); // opponent
    assert_eq!(m.get(a, b, 1), 1); // B is A's prey
}

#[test]
fn test_compute_seating_small() {
    let players = make_players(8);
    let result = compute_seating(&players, 3, None, 42);
    assert!(result.is_ok());

    let (rounds, score) = result.unwrap();
    assert_eq!(rounds.len(), 3);

    for round in &rounds {
        let total: usize = round.iter().map(|t| t.len()).sum();
        assert_eq!(total, 8);
    }

    assert_eq!(score.rules[0], 0.0, "R1 should be 0");
}

#[test]
fn test_compute_seating_is_deterministic() {
    let players = make_players(13);
    let a = compute_seating(&players, 3, None, 12345).unwrap().0;
    let b = compute_seating(&players, 3, None, 12345).unwrap().0;
    assert_eq!(a, b, "same seed must reproduce identical seating");

    // Awkward counts (6/7/11) are rejected — production filters them through
    // select_players_for_round before seating.
    assert!(compute_seating(&make_players(7), 3, None, 999).is_err());

    let s0 = seed_for_round("tournament-xyz", 0);
    assert_eq!(s0, seed_for_round("tournament-xyz", 0));
    assert_ne!(s0, seed_for_round("tournament-xyz", 1));
    assert_ne!(s0, seed_for_round("tournament-abc", 0));
}

#[test]
fn test_compute_seating_medium() {
    let players = make_players(20);
    let result = compute_seating(&players, 3, None, 42);
    assert!(result.is_ok());

    let (rounds, score) = result.unwrap();
    assert_eq!(rounds.len(), 3);

    for round in &rounds {
        let total: usize = round.iter().map(|t| t.len()).sum();
        assert_eq!(total, 20);
    }

    assert_eq!(score.rules[0], 0.0, "R1 should be 0");
    assert_eq!(score.rules[1], 0.0, "R2 should be 0");
}

#[test]
fn test_compute_seating_with_previous_rounds() {
    let players = make_players(8);

    let (initial_rounds, _) = compute_seating(&players, 2, None, 42).unwrap();

    let result = compute_seating(&players, 3, Some(&initial_rounds), 42);
    assert!(result.is_ok());

    let (rounds, _) = result.unwrap();
    assert_eq!(rounds.len(), 3);

    assert_eq!(rounds[0], initial_rounds[0]);
    assert_eq!(rounds[1], initial_rounds[1]);
}

#[test]
fn test_error_on_few_players() {
    let players = make_players(3);
    let result = compute_seating(&players, 3, None, 42);
    assert!(result.is_err());
}

#[test]
fn test_error_on_zero_rounds() {
    let players = make_players(8);
    let result = compute_seating(&players, 0, None, 42);
    assert!(result.is_err());
}

#[test]
fn test_seating_50_players() {
    let players = make_players(50);
    let result = compute_seating(&players, 3, None, 42);
    assert!(result.is_ok());

    let (rounds, score) = result.unwrap();
    assert_eq!(rounds.len(), 3);

    for round in &rounds {
        let total: usize = round.iter().map(|t| t.len()).sum();
        assert_eq!(total, 50);
    }

    assert_eq!(score.rules[0], 0.0, "R1 should be 0");
}

#[test]
fn test_compute_next_round_with_dropout() {
    let players = make_players(12);
    let (rounds, _) = compute_seating(&players, 2, None, 42).unwrap();

    let remaining: Vec<String> = (1..=10).map(|i| format!("P{}", i)).collect();

    let (round3, score) = compute_next_round(&remaining, &rounds, 42).unwrap();

    let total: usize = round3.iter().map(|t| t.len()).sum();
    assert_eq!(total, 10);

    assert_eq!(round3.len(), 2);
    assert_eq!(round3[0].len(), 5);
    assert_eq!(round3[1].len(), 5);

    assert_eq!(score.rules[0], 0.0, "R1 should be 0");
}

#[test]
fn test_compute_next_round_with_addition() {
    let players = make_players(8);
    let (rounds, _) = compute_seating(&players, 2, None, 42).unwrap();

    let expanded: Vec<String> = (1..=10).map(|i| format!("P{}", i)).collect();

    let (round3, score) = compute_next_round(&expanded, &rounds, 42).unwrap();

    let total: usize = round3.iter().map(|t| t.len()).sum();
    assert_eq!(total, 10);

    assert_eq!(score.rules[0], 0.0, "R1 should be 0");
}

#[test]
#[ignore] // Run with: cargo test --release benchmark -- --ignored
fn benchmark_seating() {
    use std::time::Instant;

    for &count in &[8, 20, 50, 100] {
        let players = make_players(count);
        let start = Instant::now();
        let result = compute_seating(&players, 3, None, 42);
        let elapsed = start.elapsed();

        assert!(result.is_ok());
        let (_, score) = result.unwrap();

        println!(
            "{} players, 3 rounds: {:?} (rules={:?})",
            count, elapsed, score.rules
        );

        match count {
            8 | 20 => assert!(elapsed.as_secs() < 1, "Small/medium should be < 1s"),
            50 => assert!(elapsed.as_secs() < 3, "50 players should be < 3s"),
            100 => assert!(elapsed.as_secs() < 5, "100 players should be < 5s"),
            _ => {}
        }
    }
}

#[test]
fn test_minimum_violations_single_table() {
    let players: Vec<String> = vec!["A", "B", "C", "D"]
        .into_iter()
        .map(|s| s.to_string())
        .collect();
    let rounds = vec![vec![players.clone()], vec![players.clone()]];
    let mins = compute_minimum_violations(&rounds);

    // R2 (opponent all rounds): all C(4,2)=6 pairs forced to meet both rounds
    assert_eq!(
        mins[1], 6.0,
        "R2 min should be 6 for 4 players single table"
    );
    // R4 (opponent twice): all 6 pairs forced to repeat
    assert_eq!(
        mins[3], 6.0,
        "R4 min should be 6 for 4 players single table"
    );
    // R1 (predator-prey repeat): always 0 minimum
    assert_eq!(mins[0], 0.0, "R1 min always 0");
}

#[test]
fn test_minimum_violations_multi_table() {
    let players = make_players(8);
    let (rounds, _) = compute_seating(&players, 2, None, 42).unwrap();
    let mins = compute_minimum_violations(&rounds);

    // With 2 tables and 8 players, pairs CAN be separated → min R2 = 0
    assert_eq!(mins[1], 0.0, "R2 min should be 0 for multi-table rounds");
    // total pair-slots = 2 rounds * 2 tables * C(4,2) = 24; C(8,2) = 28 → no forced repeats
    assert_eq!(mins[3], 0.0, "R4 min should be 0 for 8 players, 2 rounds");
}

#[test]
fn test_minimum_violations_forced_r4() {
    let players = make_players(8);
    let (rounds, _) = compute_seating(&players, 3, None, 42).unwrap();
    let mins = compute_minimum_violations(&rounds);

    // total pair-slots = 3 * 12 = 36; C(8,2) = 28; excess = 8; min_R4 = ceil(8/2) = 4
    assert_eq!(mins[3], 4.0, "R4 min should be 4 for 8 players, 3 rounds");
}

#[test]
fn test_player_issues_empty_rounds() {
    let issues = compute_player_issues(&[]);
    assert!(issues.is_empty());
}

#[test]
fn test_player_issues_single_round_no_issues() {
    let rounds = vec![vec![
        vec!["A".into(), "B".into(), "C".into(), "D".into()],
        vec!["E".into(), "F".into(), "G".into(), "H".into()],
    ]];
    let issues = compute_player_issues(&rounds);
    assert!(issues.is_empty(), "Single round should produce no issues");
}

#[test]
fn test_player_issues_identical_seating_detects_violations() {
    let table = vec!["A".into(), "B".into(), "C".into(), "D".into()];
    let rounds = vec![vec![table.clone()], vec![table.clone()]];
    let issues = compute_player_issues(&rounds);

    // Identical 4-player table across 2 rounds should trip R1, R4, R6, R7, R9
    // (not R5 — no 5th seat); only R1 and R7 are asserted explicitly below.
    assert!(
        !issues.is_empty(),
        "Identical seating should produce issues"
    );

    // Check R1 (rule index 0) -- predator-prey repeat
    let r1_issues: Vec<_> = issues.iter().filter(|i| i.rule == 0).collect();
    assert!(
        !r1_issues.is_empty(),
        "Should detect predator-prey repeats (R1)"
    );
    // prey/pred are tracked per ordered pair (k=1 and k=4), so each adjacent
    // pair contributes twice; hence >=2 rather than an exact count.
    assert!(
        r1_issues.len() >= 2,
        "Should have multiple R1 violations for identical 4-player table"
    );

    // Check R4 (rule index 3) -- opponent twice (suppressed for playing <= 20)
    let r4_issues: Vec<_> = issues.iter().filter(|i| i.rule == 3).collect();
    assert_eq!(
        r4_issues.len(),
        0,
        "R4 should be suppressed for small tournaments (<=20 players)"
    );

    // Check R7 (rule index 6) -- same seat twice
    let r7_issues: Vec<_> = issues.iter().filter(|i| i.rule == 6).collect();
    assert!(
        !r7_issues.is_empty(),
        "Should detect same-seat repeats (R7)"
    );
    assert_eq!(r7_issues.len(), 4, "All 4 players should have seat repeats");
}

#[test]
fn test_player_issues_r2_requires_more_than_2_rounds() {
    // R2 (opponent all rounds) only fires when rounds > 2
    let table = vec!["A".into(), "B".into(), "C".into(), "D".into()];
    let rounds_2 = vec![vec![table.clone()], vec![table.clone()]];
    let issues_2 = compute_player_issues(&rounds_2);
    let r2_count = issues_2.iter().filter(|i| i.rule == 1).count();
    assert_eq!(r2_count, 0, "R2 should not fire with only 2 rounds");

    let rounds_3 = vec![
        vec![table.clone()],
        vec![table.clone()],
        vec![table.clone()],
    ];
    let issues_3 = compute_player_issues(&rounds_3);
    let r2_count = issues_3.iter().filter(|i| i.rule == 1).count();
    assert_eq!(
        r2_count, 6,
        "R2 should fire for all C(4,2)=6 pairs with 3 identical rounds"
    );
}

#[test]
fn test_player_issues_optimal_seating_no_issues() {
    let players = make_players(8);
    let (rounds, score) = compute_seating(&players, 3, None, 42).unwrap();
    assert_eq!(
        score.rules[0], 0.0,
        "Optimal seating should have no R1 violations"
    );
    let issues = compute_player_issues(&rounds);
    // Optimal seating may still have unavoidable R4 violations (pigeonhole),
    // but should have no hard constraint violations (R1, R2)
    let r1 = issues.iter().filter(|i| i.rule == 0).count();
    let r2 = issues.iter().filter(|i| i.rule == 1).count();
    assert_eq!(r1, 0, "Optimal 8-player seating should have no R1 issues");
    assert_eq!(r2, 0, "Optimal 8-player seating should have no R2 issues");
}

#[test]
fn test_player_issues_json_roundtrip() {
    let table = vec!["P1".into(), "P2".into(), "P3".into(), "P4".into()];
    let rounds = vec![vec![table.clone()], vec![table.clone()]];
    let issues = compute_player_issues(&rounds);

    for issue in &issues {
        let j = issue.to_json();
        assert!(j["rule"].is_number(), "rule should be a number");
        assert!(j["players"].is_array(), "players should be an array");
        let rule = j["rule"].as_usize().unwrap();
        assert!(rule <= 8, "rule index should be 0-8, got {}", rule);
        for p in j["players"].members() {
            assert!(p.is_string(), "each player should be a string");
        }
    }
}

#[test]
fn test_is_valid_table_count() {
    assert!(!is_valid_table_count(3));
    assert!(is_valid_table_count(4));
    assert!(is_valid_table_count(5));
    assert!(!is_valid_table_count(6));
    assert!(!is_valid_table_count(7));
    assert!(is_valid_table_count(8));
    assert!(is_valid_table_count(9));
    assert!(is_valid_table_count(10));
    assert!(!is_valid_table_count(11));
    assert!(is_valid_table_count(12));
    assert!(is_valid_table_count(20));
}

#[test]
fn test_select_players_normal_count() {
    let players = make_players(8);
    let selected = select_players_for_round(&players, &[]);
    assert_eq!(selected.len(), 8);
}

#[test]
fn test_select_players_6_three_rounds() {
    let players = make_players(6);
    let r1 = select_players_for_round(&players, &[]);
    assert_eq!(r1.len(), 4);
    let rounds = vec![vec![r1.clone()]];

    let r2 = select_players_for_round(&players, &rounds);
    assert_eq!(r2.len(), 4);
    let rounds2 = vec![vec![r1.clone()], vec![r2.clone()]];

    let r3 = select_players_for_round(&players, &rounds2);
    assert_eq!(r3.len(), 4);

    let mut counts: HashMap<String, usize> = HashMap::new();
    for uid in r1.iter().chain(r2.iter()).chain(r3.iter()) {
        *counts.entry(uid.clone()).or_default() += 1;
    }
    for p in &players {
        assert_eq!(counts[p], 2, "Player {} should play exactly 2 rounds", p);
    }
}

#[test]
fn test_select_players_7_three_rounds() {
    let players = make_players(7);
    let r1 = select_players_for_round(&players, &[]);
    assert_eq!(r1.len(), 5);
    let rounds = vec![vec![r1.clone()]];

    let r2 = select_players_for_round(&players, &rounds);
    assert_eq!(r2.len(), 5);
    let rounds2 = vec![vec![r1.clone()], vec![r2.clone()]];

    let r3 = select_players_for_round(&players, &rounds2);
    assert_eq!(r3.len(), 4);

    let mut counts: HashMap<String, usize> = HashMap::new();
    for uid in r1.iter().chain(r2.iter()).chain(r3.iter()) {
        *counts.entry(uid.clone()).or_default() += 1;
    }
    for p in &players {
        assert_eq!(counts[p], 2, "Player {} should play exactly 2 rounds", p);
    }
}

#[test]
fn test_select_players_11_three_rounds() {
    let players = make_players(11);
    let r1 = select_players_for_round(&players, &[]);
    assert_eq!(r1.len(), 9);

    // Split into 1×5 + 1×4 tables, as a real round would.
    let round1 = vec![r1[..5].to_vec(), r1[5..].to_vec()];
    let rounds = vec![round1.clone()];

    let r2 = select_players_for_round(&players, &rounds);
    assert_eq!(r2.len(), 9);
    let round2 = vec![r2[..5].to_vec(), r2[5..].to_vec()];
    let rounds2 = vec![round1, round2];

    let r3 = select_players_for_round(&players, &rounds2);
    assert_eq!(r3.len(), 4);

    let mut counts: HashMap<String, usize> = HashMap::new();
    for uid in r1.iter().chain(r2.iter()).chain(r3.iter()) {
        *counts.entry(uid.clone()).or_default() += 1;
    }
    for p in &players {
        assert_eq!(counts[p], 2, "Player {} should play exactly 2 rounds", p);
    }
}

#[test]
fn test_select_players_dropout_out_of_stagger() {
    let players = make_players(5);
    let selected = select_players_for_round(&players, &[]);
    assert_eq!(selected.len(), 5);
}

#[test]
fn test_select_players_dropout_into_stagger() {
    let players = make_players(7);
    let selected = select_players_for_round(&players, &[]);
    assert_eq!(selected.len(), 5);
}
