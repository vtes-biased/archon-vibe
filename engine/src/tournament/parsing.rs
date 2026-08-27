//! JSON parsing for TournamentEvent.

use crate::model::{arg, promo_distribution};
use json::JsonValue;

use super::types::{SeatScore, TournamentEvent};
use crate::error::EngineError;

impl TournamentEvent {
    pub fn from_json(value: &JsonValue) -> Result<Self, EngineError> {
        let event_type = value[arg::TYPE].as_str().ok_or("event type required")?;

        match event_type {
            "OpenRegistration" => Ok(Self::OpenRegistration),
            "CloseRegistration" => Ok(Self::CloseRegistration),
            "CancelRegistration" => Ok(Self::CancelRegistration),
            "ReopenRegistration" => Ok(Self::ReopenRegistration),
            "ReopenTournament" => Ok(Self::ReopenTournament),
            "FinishTournament" => Ok(Self::FinishTournament),
            "Register" => Ok(Self::Register {
                user_uid: value[arg::USER_UID]
                    .as_str()
                    .ok_or("user_uid required")?
                    .to_string(),
                vekn_id: value[arg::VEKN_ID].as_str().map(|s| s.to_string()),
                display_name: value[arg::DISPLAY_NAME].as_str().map(|s| s.to_string()),
            }),
            "Unregister" => Ok(Self::Unregister {
                user_uid: value[arg::USER_UID]
                    .as_str()
                    .ok_or("user_uid required")?
                    .to_string(),
            }),
            "AddPlayer" => Ok(Self::AddPlayer {
                user_uid: value[arg::USER_UID]
                    .as_str()
                    .ok_or("user_uid required")?
                    .to_string(),
                vekn_id: value[arg::VEKN_ID].as_str().map(|s| s.to_string()),
                display_name: value[arg::DISPLAY_NAME].as_str().map(|s| s.to_string()),
                waitlist_past_cap: value[arg::WAITLIST_PAST_CAP].as_bool().unwrap_or(false),
            }),
            "RemovePlayer" => Ok(Self::RemovePlayer {
                user_uid: value[arg::USER_UID]
                    .as_str()
                    .ok_or("user_uid required")?
                    .to_string(),
            }),
            "DropOut" => Ok(Self::DropOut {
                player_uid: value[arg::PLAYER_UID]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string(),
            }),
            "CheckIn" => Ok(Self::CheckIn {
                player_uid: value[arg::PLAYER_UID]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string(),
                vekn_id: value[arg::VEKN_ID].as_str().map(|s| s.to_string()),
                display_name: value[arg::DISPLAY_NAME].as_str().map(|s| s.to_string()),
            }),
            "CheckOut" => Ok(Self::CheckOut {
                player_uid: value[arg::PLAYER_UID]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string(),
            }),
            "CheckInAll" => Ok(Self::CheckInAll),
            "ResetCheckIn" => Ok(Self::ResetCheckIn),
            "SetPaymentStatus" => {
                let player_uid = value[arg::PLAYER_UID]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let status = value[arg::STATUS]
                    .as_str()
                    .ok_or("status required")?
                    .to_string();
                Ok(Self::SetPaymentStatus { player_uid, status })
            }
            "MarkAllPaid" => Ok(Self::MarkAllPaid),
            "SetNonCompeting" => {
                let player_uid = value[arg::PLAYER_UID]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let non_competing = value[arg::NON_COMPETING]
                    .as_bool()
                    .ok_or("non_competing required")?;
                Ok(Self::SetNonCompeting {
                    player_uid,
                    non_competing,
                })
            }
            "SetWaitlisted" => {
                let player_uid = value[arg::PLAYER_UID]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let waitlisted = value[arg::WAITLISTED]
                    .as_bool()
                    .ok_or("waitlisted required")?;
                Ok(Self::SetWaitlisted {
                    player_uid,
                    waitlisted,
                })
            }
            "StartRound" => {
                let seating = if value[arg::SEATING].is_null() || !value[arg::SEATING].is_array() {
                    None
                } else {
                    Some(
                        value[arg::SEATING]
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
            "FinishRound" => Ok(Self::FinishRound {
                round: value[arg::ROUND].as_usize(),
            }),
            "CancelRound" => Ok(Self::CancelRound {
                round: value[arg::ROUND].as_usize(),
            }),
            "RestoreRound" => Ok(Self::RestoreRound {
                round: value[arg::ROUND].as_usize(),
            }),
            "SelfOrganizeRound" => Ok(Self::SelfOrganizeRound {
                player_uids: value[arg::PLAYER_UIDS]
                    .members()
                    .filter_map(|p| p.as_str().map(|s| s.to_string()))
                    .collect(),
            }),
            "SwapSeats" => {
                let round = value[arg::ROUND].as_usize().ok_or("round required")?;
                let table1 = value[arg::TABLE1].as_usize().ok_or("table1 required")?;
                let seat1 = value[arg::SEAT1].as_usize().ok_or("seat1 required")?;
                let table2 = value[arg::TABLE2].as_usize().ok_or("table2 required")?;
                let seat2 = value[arg::SEAT2].as_usize().ok_or("seat2 required")?;
                Ok(Self::SwapSeats {
                    round,
                    table1,
                    seat1,
                    table2,
                    seat2,
                })
            }
            "SeatPlayer" => {
                let player_uid = value[arg::PLAYER_UID]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let table = value[arg::TABLE].as_usize().ok_or("table required")?;
                let seat = value[arg::SEAT].as_usize().ok_or("seat required")?;
                Ok(Self::SeatPlayer {
                    player_uid,
                    table,
                    seat,
                    round: value[arg::ROUND].as_usize(),
                })
            }
            "UnseatPlayer" => Ok(Self::UnseatPlayer {
                player_uid: value[arg::PLAYER_UID]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string(),
                round: value[arg::ROUND].as_usize(),
            }),
            "AddTable" => Ok(Self::AddTable),
            "RemoveTable" => {
                let table = value[arg::TABLE].as_usize().ok_or("table required")?;
                Ok(Self::RemoveTable { table })
            }
            "SetScore" => {
                let round = value[arg::ROUND].as_usize().ok_or("round required")?;
                let table = value[arg::TABLE].as_usize().ok_or("table required")?;
                let scores: Vec<SeatScore> = value[arg::SCORES]
                    .members()
                    .map(|s| {
                        Ok(SeatScore {
                            player_uid: s[arg::PLAYER_UID]
                                .as_str()
                                .ok_or("player_uid required")?
                                .to_string(),
                            vp: s[arg::VP].as_f64().unwrap_or(0.0),
                        })
                    })
                    .collect::<Result<Vec<_>, EngineError>>()?;
                Ok(Self::SetScore {
                    round,
                    table,
                    scores,
                })
            }
            "Override" => {
                let round = value[arg::ROUND].as_usize().ok_or("round required")?;
                let table = value[arg::TABLE].as_usize().ok_or("table required")?;
                let comment = value[arg::COMMENT]
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
                let round = value[arg::ROUND].as_usize().ok_or("round required")?;
                let table = value[arg::TABLE].as_usize().ok_or("table required")?;
                Ok(Self::Unoverride { round, table })
            }
            "SetToss" => {
                let player_uid = value[arg::PLAYER_UID]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let toss = value[arg::TOSS].as_u32().ok_or("toss required")?;
                Ok(Self::SetToss { player_uid, toss })
            }
            "RandomToss" => Ok(Self::RandomToss),
            "StartFinals" => Ok(Self::StartFinals),
            "FinishFinals" => Ok(Self::FinishFinals),
            "CancelFinals" => Ok(Self::CancelFinals),
            "AlterSeating" => {
                let round = value[arg::ROUND].as_usize().ok_or("round required")?;
                let seating: Vec<Vec<String>> = value[arg::SEATING]
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
                let player_uid = value[arg::PLAYER_UID]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let deck = value[arg::DECK].clone();
                if deck.is_null() {
                    return Err(EngineError::internal("deck required"));
                }
                let multideck = value[arg::MULTIDECK].as_bool().unwrap_or(false);
                Ok(Self::UpsertDeck {
                    player_uid,
                    deck,
                    multideck,
                })
            }
            "DeleteDeck" => {
                let player_uid = value[arg::PLAYER_UID]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let deck_index = value[arg::DECK_INDEX].as_usize();
                let multideck = value[arg::MULTIDECK].as_bool().unwrap_or(false);
                Ok(Self::DeleteDeck {
                    player_uid,
                    deck_index,
                    multideck,
                })
            }
            "RaffleDraw" => {
                let label = value[arg::LABEL]
                    .as_str()
                    .ok_or("label required")?
                    .to_string();
                let pool = value[arg::POOL]
                    .as_str()
                    .ok_or("pool required")?
                    .to_string();
                let exclude_drawn = value[arg::EXCLUDE_DRAWN].as_bool().unwrap_or(true);
                let count = value[arg::COUNT].as_usize().ok_or("count required")?;
                let seed = value[arg::SEED].as_u64().ok_or("seed required")?;
                Ok(Self::RaffleDraw {
                    label,
                    pool,
                    exclude_drawn,
                    count,
                    seed,
                    prize_promo_uid: value[arg::PRIZE_PROMO_UID].as_str().map(String::from),
                })
            }
            "ReportPromos" => {
                let rows = match &value[arg::PROMOS] {
                    JsonValue::Array(rows) => rows,
                    _ => return Err("promos required".into()),
                };
                let mut promos = Vec::with_capacity(rows.len());
                for row in rows {
                    let promo_uid = row[arg::PROMO_UID].as_str().ok_or("promo_uid required")?;
                    let qty = row[arg::QTY].as_usize().ok_or("qty required")?;
                    if promo_uid.is_empty() || qty == 0 {
                        return Err("promo rows need a promo_uid and a positive qty".into());
                    }
                    promos.push(json::object! {
                        promo_distribution::PROMO_UID => promo_uid,
                        promo_distribution::QTY => qty,
                    });
                }
                Ok(Self::ReportPromos {
                    promos: JsonValue::Array(promos),
                    stock_source_uid: value[arg::STOCK_SOURCE_UID].as_str().map(String::from),
                })
            }
            "RaffleUndo" => Ok(Self::RaffleUndo),
            "RaffleClear" => Ok(Self::RaffleClear),
            "UpdateConfig" => {
                let config = value[arg::CONFIG].clone();
                if config.is_null() || !config.is_object() {
                    return Err(EngineError::internal("config object required"));
                }
                Ok(Self::UpdateConfig { config })
            }
            "SetArchivalResults" => {
                let players: Vec<String> = value[arg::PLAYERS]
                    .members()
                    .filter_map(|p| p.as_str().map(String::from))
                    .filter(|p| !p.is_empty())
                    .collect();
                Ok(Self::SetArchivalResults {
                    winner: value[arg::WINNER]
                        .as_str()
                        .ok_or("winner required")?
                        .to_string(),
                    players,
                    reported_player_count: value[arg::REPORTED_PLAYER_COUNT]
                        .as_usize()
                        .ok_or("reported_player_count required")?,
                })
            }
            _ => Err(EngineError::internal(format!(
                "Unknown event type: {}",
                event_type
            ))),
        }
    }
}
