"""Playtest NDA records: request, click-to-sign, scan-upload fallback, and the
sealed-PDF evidence. Records live in the nda_records side table — never synced,
never projected — so every read here is an explicit, gated fetch."""

import logging
from datetime import UTC, datetime
from uuid import uuid7

import msgspec
from fastapi import APIRouter, HTTPException, Response, UploadFile
from pydantic import BaseModel

from .. import nda, permissions
from ..db import (
    create_nda_request,
    get_nda_pdf,
    get_nda_pending,
    get_nda_records,
    get_user_by_uid,
    insert_nda_upload,
    seal_nda_signature,
)
from ..email_service import send_nda_copy_email
from ..middleware.auth import CurrentUser

router = APIRouter(prefix="/api/users", tags=["nda"])
logger = logging.getLogger(__name__)
encoder = msgspec.json.Encoder()

MAX_NDA_UPLOAD_SIZE = 8 * 1024 * 1024
UPLOAD_CONTENT_TYPES = ("application/pdf", "image/jpeg", "image/png", "image/webp")


def _require_manage_or_self(current_user, uid: str) -> None:
    if current_user.uid != uid and not permissions.can_manage_nda(current_user):
        raise HTTPException(
            status_code=403, detail="Only IC or PTC can manage NDA records"
        )


@router.get("/{uid}/nda")
async def get_nda_status(uid: str, current_user: CurrentUser) -> Response:
    _require_manage_or_self(current_user, uid)
    records = await get_nda_records(uid)
    return Response(
        content=encoder.encode(
            {
                "records": records,
                "pending": next((r for r in records if r["status"] == "pending"), None),
                "has_nda": any(r["status"] in ("signed", "uploaded") for r in records),
                "document_version": nda.NDA_VERSION,
            }
        ),
        media_type="application/json",
    )


@router.post("/{uid}/nda/request", status_code=201)
async def request_nda_signature(uid: str, current_user: CurrentUser) -> Response:
    if not permissions.can_manage_nda(current_user):
        raise HTTPException(
            status_code=403, detail="Only IC or PTC can request an NDA signature"
        )
    target = await get_user_by_uid(uid)
    if not target or target.deleted_at:
        raise HTTPException(status_code=404, detail="User not found")
    if not await create_nda_request(str(uuid7()), uid, current_user.uid):
        raise HTTPException(
            status_code=409, detail="This member already has a pending NDA request"
        )
    return Response(content=b'{"success": true}', media_type="application/json")


@router.get("/{uid}/nda/document")
async def get_nda_document(uid: str, current_user: CurrentUser) -> Response:
    _require_manage_or_self(current_user, uid)
    target = await get_user_by_uid(uid)
    if not target or target.deleted_at:
        raise HTTPException(status_code=404, detail="User not found")
    return Response(
        content=encoder.encode(
            {
                "text": nda.fill_template(target.name, datetime.now(UTC)),
                "version": nda.NDA_VERSION,
                "sha256": nda.nda_sha256(),
            }
        ),
        media_type="application/json",
    )


class SignNdaRequest(BaseModel):
    """JSON body for POST /api/users/{uid}/nda/sign. The typed name is the
    signature and becomes the document's Recipient."""

    name: str
    email: str
    address: str = ""
    phone: str = ""


@router.post("/{uid}/nda/sign")
async def sign_nda(
    uid: str, body: SignNdaRequest, current_user: CurrentUser
) -> Response:
    if current_user.uid != uid:
        raise HTTPException(status_code=403, detail="Only the member can sign")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="A typed name is required to sign")
    pending = await get_nda_pending(uid)
    if not pending:
        raise HTTPException(
            status_code=409, detail="No pending NDA request for this member"
        )
    requester = await get_user_by_uid(pending["requested_by"])
    signed_at = datetime.now(UTC)
    pdf = nda.build_sealed_pdf(
        recipient_name=name,
        signer_email=body.email.strip(),
        signer_address=body.address.strip(),
        signer_phone=body.phone.strip(),
        member_uid=uid,
        vekn_id=current_user.vekn_id or "-",
        requested_by=requester.name if requester else pending["requested_by"],
        record_uid=pending["uid"],
        signed_at=signed_at,
    )
    sealed = await seal_nda_signature(
        pending["uid"],
        uid,
        document_version=nda.NDA_VERSION,
        document_sha256=nda.nda_sha256(),
        signer_name=name,
        signer_email=body.email.strip(),
        signer_address=body.address.strip(),
        signer_phone=body.phone.strip(),
        signed_at=signed_at,
        pdf=pdf,
    )
    if not sealed:
        raise HTTPException(
            status_code=409, detail="No pending NDA request for this member"
        )
    if body.email.strip():
        await send_nda_copy_email(body.email.strip(), name, pdf)
    return Response(
        content=encoder.encode({"success": True, "record_uid": pending["uid"]}),
        media_type="application/json",
    )


@router.post("/{uid}/nda/upload", status_code=201)
async def upload_nda_scan(
    uid: str, file: UploadFile, current_user: CurrentUser
) -> Response:
    if not permissions.can_manage_nda(current_user):
        raise HTTPException(
            status_code=403, detail="Only IC or PTC can upload an NDA scan"
        )
    target = await get_user_by_uid(uid)
    if not target or target.deleted_at:
        raise HTTPException(status_code=404, detail="User not found")
    if file.content_type not in UPLOAD_CONTENT_TYPES:
        raise HTTPException(
            status_code=400, detail="NDA scan must be a PDF or an image"
        )
    data = await file.read()
    if len(data) > MAX_NDA_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Scan too large. Max size: {MAX_NDA_UPLOAD_SIZE // (1024 * 1024)}MB",
        )
    await insert_nda_upload(
        str(uuid7()), uid, current_user.uid, data, file.content_type
    )
    return Response(content=b'{"success": true}', media_type="application/json")


@router.get("/{uid}/nda/{record_uid}/pdf")
async def download_nda(
    uid: str, record_uid: str, current_user: CurrentUser
) -> Response:
    _require_manage_or_self(current_user, uid)
    result = await get_nda_pdf(uid, record_uid)
    if not result:
        raise HTTPException(status_code=404, detail="NDA record not found")
    data, content_type = result
    ext = content_type.rsplit("/", 1)[-1].replace("jpeg", "jpg")
    # PII evidence: never cacheable, and an attachment so the SPA stays put.
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="bcp-playtest-nda.{ext}"',
            "Content-Length": str(len(data)),
        },
    )
