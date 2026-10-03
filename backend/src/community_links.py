"""The rules a community link obeys, shared by the owner's editor and a moderator's."""

import logging

from litestar.exceptions import HTTPException

from . import permissions
from .models import (
    CONTENT_LINK_TYPES,
    CommunityLink,
    CommunityLinkType,
    LinkModeration,
    User,
)

logger = logging.getLogger(__name__)

MAX_LANGUAGES = 5


def moderation_for(
    actor: User,
    state: str,
    country: str | None,
    current: LinkModeration | None,
    target_uid: str,
    url: str,
) -> LinkModeration | None:
    if state == "global":
        allowed = permissions.can_promote_link_global(actor)
    elif state == "national":
        allowed = permissions.can_promote_link_national(actor, country)
    elif state in ("none", "hidden"):
        allowed = permissions.can_moderate_link(actor, country)
    else:
        raise HTTPException(status_code=422, detail=f"Invalid moderation: {state}")
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=f"You don't have the authority to set a link {state} in {country}",
        )
    if state == (current.value if current else "none"):
        return current
    logger.info(f"{actor.uid} moderated {target_uid}'s {url} ({country}) to {state}")
    return None if state == "none" else LinkModeration(state)


def placement(
    actor: User,
    link_type: CommunityLinkType,
    raw_country: str | None,
    state: str | None,
    prior: CommunityLink | None,
    owner: User,
    url: str,
) -> tuple[str | None, LinkModeration | None]:
    """The country and moderation a link is saved with."""
    current = prior.moderation if prior else None
    if link_type not in CONTENT_LINK_TYPES:
        country = validated_country(
            raw_country, (prior and prior.country) or owner.country
        )
        if state is None:
            return country, current
        return country, moderation_for(actor, state, country, current, owner.uid, url)

    pinned_in = None
    if current is LinkModeration.NATIONAL:
        pinned_in = (prior and prior.country) or owner.country
    if state is None:
        return pinned_in, current
    sits_in = pinned_in or owner.country
    lands_in = sits_in
    if state == "national" and current is not LinkModeration.NATIONAL:
        if current is not None and not permissions.can_moderate_link(actor, sits_in):
            raise HTTPException(
                status_code=403,
                detail=f"Only a moderator in {sits_in} can pin a {current.value} link",
            )
        lands_in = validated_country(actor.country, None)
    elif state == "national" and not permissions.can_promote_link_national(
        actor, pinned_in
    ):
        raise HTTPException(
            status_code=403, detail=f"This link is already pinned in {pinned_in}"
        )
    mod = moderation_for(actor, state, lands_in, current, owner.uid, url)
    return (lands_in if mod is LinkModeration.NATIONAL else None), mod


def validated_type(raw: str) -> CommunityLinkType:
    try:
        return CommunityLinkType(raw)
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"Invalid link type: {raw}"
        ) from None


def validated_languages(
    languages: list[str], link_type: CommunityLinkType, prior: CommunityLink | None
) -> list[str]:
    if len(languages) > MAX_LANGUAGES:
        raise HTTPException(
            status_code=422, detail=f"Maximum {MAX_LANGUAGES} languages per link"
        )
    for lang in languages:
        if not (len(lang) == 2 and lang.isascii() and lang.islower()):
            raise HTTPException(
                status_code=422, detail=f"Invalid language code: {lang}"
            )
    # A language-less content link predating the rule may be resubmitted
    # unchanged, so one legacy entry cannot block every later edit.
    grandfathered = prior is not None and prior.type == link_type
    if link_type in CONTENT_LINK_TYPES and not languages and not grandfathered:
        raise HTTPException(
            status_code=422,
            detail=f"A {link_type.value} link must declare a language",
        )
    return languages


def validated_country(raw: str | None, fallback: str | None) -> str:
    country = (raw or fallback or "").upper()
    if not country:
        raise HTTPException(
            status_code=422,
            detail="A community link needs a country",
        )
    if not (len(country) == 2 and country.isascii() and country.isalpha()):
        raise HTTPException(status_code=422, detail=f"Invalid country: {raw}")
    return country
