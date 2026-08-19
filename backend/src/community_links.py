"""The rules a community link obeys, shared by the owner's editor and a moderator's."""

from datetime import UTC, datetime

from fastapi import HTTPException

from . import permissions
from .models import (
    CONTENT_LINK_TYPES,
    CommunityLink,
    CommunityLinkType,
    LinkModeration,
    User,
)

MAX_LANGUAGES = 5


def state_of(moderation: LinkModeration | None) -> str:
    if moderation is None:
        return "none"
    return moderation.scope or "none" if moderation.status == "promoted" else "hidden"


def moderation_for(
    actor: User, state: str, country: str | None, current: LinkModeration | None
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
    if state == state_of(current):
        return current
    if state == "none":
        return None
    stamp = {"by": actor.uid, "at": datetime.now(UTC)}
    if state == "hidden":
        return LinkModeration(status="hidden", **stamp)
    return LinkModeration(status="promoted", scope=state, **stamp)


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
