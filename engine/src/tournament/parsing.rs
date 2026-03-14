//! JSON parsing for TournamentEvent.

use json::JsonValue;

use super::types::{SeatScore, TournamentEvent};

impl TournamentEvent {
    pub fn from_json(value: &JsonValue) -> Result<Self, String> {
        let event_type = value["type"].as_str().ok_or("event type required")?;

        match event_type {
            "OpenRegistration" => Ok(Self::OpenRegistration),
            "CloseRegistration" => Ok(Self::CloseRegistration),
            "CancelRegistration" => Ok(Self::CancelRegistration),
            "ReopenRegistration" => Ok(Self::ReopenRegistration),
            "ReopenTournament" => Ok(Self::ReopenTournament),
            "FinishTournament" => Ok(Self::FinishTournament),
            "Register" => Ok(Self::Register {
                user_uid: value["user_uid"]
                    .as_str()
                    .ok_or("user_uid required")?
                    .to_string(),
                vekn_id: value["vekn_id"].as_str().map(|s| s.to_string()),
            }),
            "Unregister" => Ok(Self::Unregister {
                user_uid: value["user_uid"]
                    .as_str()
                    .ok_or("user_uid required")?
                    .to_string(),
            }),
            "AddPlayer" => Ok(Self::AddPlayer {
                user_uid: value["user_uid"]
                    .as_str()
                    .ok_or("user_uid required")?
                    .to_string(),
                vekn_id: value["vekn_id"].as_str().map(|s| s.to_string()),
            }),
            "RemovePlayer" => Ok(Self::RemovePlayer {
                user_uid: value["user_uid"]
                    .as_str()
                    .ok_or("user_uid required")?
                    .to_string(),
            }),
            "DropOut" => Ok(Self::DropOut {
                player_uid: value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string(),
            }),
            "CheckIn" => Ok(Self::CheckIn {
                player_uid: value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string(),
            }),
            "CheckOut" => Ok(Self::CheckOut {
                player_uid: value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string(),
            }),
            "CheckInAll" => Ok(Self::CheckInAll),
            "ResetCheckIn" => Ok(Self::ResetCheckIn),
            "SetPaymentStatus" => {
                let player_uid = value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let status = value["status"]
                    .as_str()
                    .ok_or("status required")?
                    .to_string();
                Ok(Self::SetPaymentStatus { player_uid, status })
            }
            "MarkAllPaid" => Ok(Self::MarkAllPaid),
            "StartRound" => {
                let seating = if value["seating"].is_null() || !value["seating"].is_array() {
                    None
                } else {
                    Some(
                        value["seating"]
                            .members()
                            .map(|t| {
                                t.members()
                                    .filter_map(|p| p.as_str().map(|s| s.to_string()))
                                    .collect()
                            })
                            .collect(),
                    )
                };
                Ok(Self::StartRound { seating })
            }
            "FinishRound" => Ok(Self::FinishRound),
            "CancelRound" => Ok(Self::CancelRound),
            "SwapSeats" => {
                let round = value["round"].as_usize().ok_or("round required")?;
                let table1 = value["table1"].as_usize().ok_or("table1 required")?;
                let seat1 = value["seat1"].as_usize().ok_or("seat1 required")?;
                let table2 = value["table2"].as_usize().ok_or("table2 required")?;
                let seat2 = value["seat2"].as_usize().ok_or("seat2 required")?;
                Ok(Self::SwapSeats {
                    round,
                    table1,
                    seat1,
                    table2,
                    seat2,
                })
            }
            "SeatPlayer" => {
                let player_uid = value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let table = value["table"].as_usize().ok_or("table required")?;
                let seat = value["seat"].as_usize().ok_or("seat required")?;
                Ok(Self::SeatPlayer {
                    player_uid,
                    table,
                    seat,
                })
            }
            "UnseatPlayer" => Ok(Self::UnseatPlayer {
                player_uid: value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string(),
            }),
            "AddTable" => Ok(Self::AddTable),
            "RemoveTable" => {
                let table = value["table"].as_usize().ok_or("table required")?;
                Ok(Self::RemoveTable { table })
            }
            "SetScore" => {
                let round = value["round"].as_usize().ok_or("round required")?;
                let table = value["table"].as_usize().ok_or("table required")?;
                let scores: Vec<SeatScore> = value["scores"]
                    .members()
                    .map(|s| {
                        Ok(SeatScore {
                            player_uid: s["player_uid"]
                                .as_str()
                                .ok_or("player_uid required")?
                                .to_string(),
                            vp: s["vp"].as_f64().unwrap_or(0.0),
                        })
                    })
                    .collect::<Result<Vec<_>, String>>()?;
                Ok(Self::SetScore {
                    round,
                    table,
                    scores,
                })
            }
            "Override" => {
                let round = value["round"].as_usize().ok_or("round required")?;
                let table = value["table"].as_usize().ok_or("table required")?;
                let comment = value["comment"]
                    .as_str()
                    .ok_or("comment required")?
                    .to_string();
                Ok(Self::Override {
                    round,
                    table,
                    comment,
                })
            }
            "Unoverride" => {
                let round = value["round"].as_usize().ok_or("round required")?;
                let table = value["table"].as_usize().ok_or("table required")?;
                Ok(Self::Unoverride { round, table })
            }
            "SetToss" => {
                let player_uid = value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let toss = value["toss"].as_u32().ok_or("toss required")?;
                Ok(Self::SetToss { player_uid, toss })
            }
            "RandomToss" => Ok(Self::RandomToss),
            "StartFinals" => Ok(Self::StartFinals),
            "FinishFinals" => Ok(Self::FinishFinals),
            "AlterSeating" => {
                let round = value["round"].as_usize().ok_or("round required")?;
                let seating: Vec<Vec<String>> = value["seating"]
                    .members()
                    .map(|t| {
                        t.members()
                            .filter_map(|p| p.as_str().map(|s| s.to_string()))
                            .collect()
                    })
                    .collect();
                Ok(Self::AlterSeating { round, seating })
            }
            "UpsertDeck" | "UploadDeck" | "UpdateDeck" => {
                let player_uid = value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let deck = value["deck"].clone();
                if deck.is_null() {
                    return Err("deck required".to_string());
                }
                let multideck = value["multideck"].as_bool().unwrap_or(false);
                Ok(Self::UpsertDeck {
                    player_uid,
                    deck,
                    multideck,
                })
            }
            "DeleteDeck" => {
                let player_uid = value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let deck_index = value["deck_index"].as_usize();
                let multideck = value["multideck"].as_bool().unwrap_or(false);
                Ok(Self::DeleteDeck {
                    player_uid,
                    deck_index,
                    multideck,
                })
            }
            "RaffleDraw" => {
                let label = value["label"].as_str().ok_or("label required")?.to_string();
                let pool = value["pool"].as_str().ok_or("pool required")?.to_string();
                let exclude_drawn = value["exclude_drawn"].as_bool().unwrap_or(true);
                let count = value["count"].as_usize().ok_or("count required")?;
                let seed = value["seed"].as_u64().ok_or("seed required")?;
                Ok(Self::RaffleDraw {
                    label,
                    pool,
                    exclude_drawn,
                    count,
                    seed,
                })
            }
            "RaffleUndo" => Ok(Self::RaffleUndo),
            "RaffleClear" => Ok(Self::RaffleClear),
            "UpdateConfig" => {
                let config = value["config"].clone();
                if config.is_null() || !config.is_object() {
                    return Err("config object required".to_string());
                }
                Ok(Self::UpdateConfig { config })
            }
            _ => Err(format!("Unknown event type: {}", event_type)),
        }
    }
}
