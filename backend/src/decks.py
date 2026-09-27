from datetime import UTC, datetime
from uuid import uuid7

import msgspec

from .broadcast import broadcast_personal, broadcast_precomputed, deck_org_uids
from .db import (
    BroadcastData,
    get_decks_for_tournament,
    save_object_from_model,
    tournament_transaction,
)
from .models import DeckAttribution, DeckObject, DeckView, ObjectType, Tournament


async def build_decks_json(tournament_uid: str, conn=None) -> str:
    decks = await get_decks_for_tournament(tournament_uid, conn=conn)
    return msgspec.json.encode(
        [
            {
                "user_uid": d.user_uid,
                "round": d.round,
                "uid": d.uid,
                "public": d.public,
                "winner": d.winner,
                "private": d.private,
            }
            for d in decks
        ]
    ).decode()


async def process_deck_ops(
    deck_ops: list,
    tournament_uid: str,
    tournament: Tournament,
) -> list[BroadcastData]:
    if not deck_ops:
        return []
    existing_decks = await get_decks_for_tournament(tournament_uid)

    def stamp(bd: BroadcastData, deck: DeckObject) -> BroadcastData:
        bd.org_uids = deck_org_uids(
            deck.private, tournament.state, tournament.organizers_uids
        )
        return bd

    affected: list[BroadcastData] = []
    for op in deck_ops:
        op_type = op.get("op")
        if op_type == "upsert":
            deck_data = op["deck"]
            player_uid = op["player_uid"]
            round_val = deck_data.get("round")
            existing = next(
                (
                    d
                    for d in existing_decks
                    if d.user_uid == player_uid and d.round == round_val
                ),
                None,
            )
            if existing:
                deck_obj = existing
                deck_obj.modified = datetime.now(UTC)
            else:
                deck_obj = DeckObject(
                    uid=str(uuid7()),
                    modified=datetime.now(UTC),
                    tournament_uid=tournament_uid,
                    user_uid=player_uid,
                )
            deck_obj.round = round_val
            deck_obj.name = deck_data.get("name", "")
            deck_obj.comments = deck_data.get("comments", "")
            deck_obj.cards = deck_data.get("cards", {})
            # The engine strips the credit off a replacement, so an absent one
            # leaves a stored credit standing rather than clearing it.
            if "attribution" in deck_data:
                deck_obj.attribution = msgspec.convert(
                    deck_data["attribution"], DeckAttribution
                )
            deck_obj.public = deck_data.get("public", False)
            deck_obj.winner = deck_data.get("winner", False)
            deck_obj.private = deck_data.get("private", False)
            affected.append(
                stamp(await save_object_from_model(ObjectType.DECK, deck_obj), deck_obj)
            )

        elif op_type == "delete":
            player_uid = op["player_uid"]
            deck_index = op.get("deck_index")
            is_multideck = op.get("multideck", False)
            for d in existing_decks:
                if d.user_uid == player_uid:
                    if is_multideck and d.round != deck_index:
                        continue
                    d.deleted_at = datetime.now(UTC)
                    d.modified = datetime.now(UTC)
                    affected.append(
                        stamp(await save_object_from_model(ObjectType.DECK, d), d)
                    )

        elif op_type == "set_round":
            deck_uid = op.get("deck_uid")
            target = next((d for d in existing_decks if d.uid == deck_uid), None)
            if target:
                target.round = op.get("round")
                target.modified = datetime.now(UTC)
                affected.append(
                    stamp(await save_object_from_model(ObjectType.DECK, target), target)
                )

        elif op_type == "set_publication":
            deck_uid = op.get("deck_uid")
            target = next((d for d in existing_decks if d.uid == deck_uid), None)
            if target:
                target.public = op.get("public", False)
                target.winner = op.get("winner", False)
                target.modified = datetime.now(UTC)
                affected.append(
                    stamp(await save_object_from_model(ObjectType.DECK, target), target)
                )

        elif op_type == "set_attribution":
            deck_uid = op.get("deck_uid")
            target = next((d for d in existing_decks if d.uid == deck_uid), None)
            if target:
                target.attribution = msgspec.convert(op["attribution"], DeckAttribution)
                target.modified = datetime.now(UTC)
                affected.append(
                    stamp(await save_object_from_model(ObjectType.DECK, target), target)
                )

        elif op_type == "set_private":
            deck_uid = op.get("deck_uid")
            target = next((d for d in existing_decks if d.uid == deck_uid), None)
            if target:
                target.private = op.get("private", False)
                target.modified = datetime.now(UTC)
                affected.append(
                    stamp(await save_object_from_model(ObjectType.DECK, target), target)
                )

        elif op_type == "log_view":
            deck_uid = op.get("deck_uid")
            viewer_uid = op["user_uid"]
            # Re-read under the row lock: two organizers opening the same deck
            # at once would otherwise each append to a stale list.
            async with tournament_transaction(tournament_uid):
                decks = await get_decks_for_tournament(tournament_uid)
                target = next((d for d in decks if d.uid == deck_uid), None)
                if target and all(v.user_uid != viewer_uid for v in target.views):
                    target.views.append(
                        DeckView(user_uid=viewer_uid, round=op["round"])
                    )
                    target.modified = datetime.now(UTC)
                    affected.append(
                        stamp(
                            await save_object_from_model(ObjectType.DECK, target),
                            target,
                        )
                    )

    return affected


def push_decks(
    tournament: Tournament,
    user_uids: list[str],
    decks: list[DeckObject],
    *,
    modified_at: str | None = None,
    access_version: str | None = None,
) -> None:
    for user_uid in user_uids:
        for deck in decks:
            broadcast_personal(
                user_uid,
                obj_type=ObjectType.DECK,
                uid=deck.uid,
                full_dict=msgspec.to_builtins(deck),
                org_uids=deck_org_uids(
                    deck.private, tournament.state, tournament.organizers_uids
                ),
                obj_user_uid=deck.user_uid,
                modified_at=modified_at,
                access_version=access_version,
            )


async def withdraw_private_decks(tournament: Tournament) -> None:
    """The no-op re-save is what evicts the decks from an organizer offline now."""
    bds = []
    async with tournament_transaction(tournament.uid):
        decks = [d for d in await get_decks_for_tournament(tournament.uid) if d.private]
        for deck in decks:
            deck.modified = datetime.now(UTC)
            bd = await save_object_from_model(ObjectType.DECK, deck)
            bd.org_uids = deck_org_uids(
                deck.private, tournament.state, tournament.organizers_uids
            )
            bds.append(bd)
    for bd in bds:
        broadcast_precomputed(bd)
    push_decks(tournament, tournament.organizers_uids, decks)
