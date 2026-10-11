"""Request-scoped communication — OWNER: D4 (spec §13).

There is **no generic chat**. A conversation always belongs to exactly one
BloodRequest, one organization and one counterparty (donor or blood centre).
REST is sufficient for the MVP; WebSockets are explicitly out of scope.
"""

from __future__ import annotations

from fastapi import Depends, Query, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from bloodlink_api.core.clock import iso, utcnow
from bloodlink_api.core.context import CurrentPrincipal
from bloodlink_api.core.envelope import success
from bloodlink_api.core.errors import ConflictError, ForbiddenError, NotFoundError
from bloodlink_api.core.registry import ModuleSpec, register_module
from bloodlink_api.core.routing import api_router
from bloodlink_api.db.models.blood_requests import BloodRequest
from bloodlink_api.db.models.coordination import Conversation, Message
from bloodlink_api.db.models.donors import DonorProfile, OrganizationResponse
from bloodlink_api.db.models.identity import User
from bloodlink_api.db.session import get_db
from bloodlink_api.modules.notifications import service as notification_service
from bloodlink_contracts.dto import APIModel
from bloodlink_contracts.enums import (
    MESSAGE_MAX_LENGTH,
    ConversationParticipantRole,
    ConversationStatus,
    NotificationType,
)
from bloodlink_contracts.errors import ErrorCode
from bloodlink_validation.common import validate_message_content

router = api_router(owner="D4", domain="communication", prefix="/conversations")


class StartConversationRequest(APIModel):
    blood_request_id: str
    counterparty_user_id: str | None = None  # required for hospital-initiated threads


class MessageRequest(APIModel):
    content: str


def _participant_conversations_query(user: User, organization_id: str | None):
    """Conversations the caller may see: their own donor threads, or their
    organization's threads."""
    clauses = [Conversation.donor_id == user.id]
    if organization_id:
        clauses.append(Conversation.organization_id == organization_id)
    return select(Conversation).where(or_(*clauses))


def _assert_can_access(conversation: Conversation, user: User, organization_id: str | None) -> None:
    if conversation.donor_id == user.id:
        return
    if organization_id and conversation.organization_id == organization_id:
        return
    raise ForbiddenError("This conversation belongs to another coordination thread")


def _serialise(db: Session, conversation: Conversation, *, viewer_id: str) -> dict:
    counterparty = db.get(User, conversation.donor_id)
    blood_request = db.get(BloodRequest, conversation.blood_request_id)
    last_message = db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    unread = db.execute(
        select(func.count())
        .select_from(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.sender_id != viewer_id,
            Message.read_at.is_(None),
        )
    ).scalar_one()
    return {
        "id": conversation.id,
        "bloodRequestId": conversation.blood_request_id,
        "requestReference": blood_request.reference if blood_request else None,
        "requestStatus": blood_request.status.value if blood_request else None,
        "counterpartyRole": conversation.counterparty_role.value,
        "counterpartyName": counterparty.full_name if counterparty else "BloodLink user",
        "counterpartyInitials": counterparty.initials if counterparty else "BL",
        "status": conversation.status.value,
        "unreadCount": unread,
        "lastMessagePreview": (last_message.content[:120] if last_message else None),
        "lastMessageAt": iso(conversation.last_message_at),
        "createdAt": iso(conversation.created_at),
    }


@router.get("", summary="My coordination threads")
def list_conversations(
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    status_filter: str | None = Query(None, alias="status"),
) -> dict:
    """List the caller's request-scoped threads.

    OWNER: D4
    PURPOSE: Coordination inbox for donors, hospitals and blood centres.
    INPUT: status? (OPEN | CLOSED | ARCHIVED)
    OUTPUT: { items: [ConversationView], unreadTotal: int }
    AUTHORIZATION: Own donor threads, or all threads of the caller's organization.
    STATE CHANGES: none
    ERRORS: 401 UNAUTHENTICATED
    DEPENDENCIES: Conversation/Message
    MUST NOT: expose threads the caller is not a participant in
    PRIVACY: counterparty display name only; no phone numbers or addresses
    """
    query = _participant_conversations_query(principal.user, principal.organization_id)
    if status_filter:
        value = ConversationStatus.coerce(status_filter)
        if value is not None:
            query = query.where(Conversation.status == value)
    rows = db.execute(query.order_by(Conversation.last_message_at.desc().nullslast())).scalars()
    items = [_serialise(db, conversation, viewer_id=principal.user_id) for conversation in rows]
    return success(request, {"items": items, "unreadTotal": sum(item["unreadCount"] for item in items)})


@router.post("", status_code=status.HTTP_201_CREATED, summary="Start a coordination thread")
def start_conversation(
    payload: StartConversationRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Open (or return) the coordination thread for a request + counterparty pair.

    OWNER: D4
    PURPOSE: Coordinating a concrete request without enabling social chat (§13).
    INPUT: StartConversationRequest { bloodRequestId, counterpartyUserId }
    OUTPUT: 201 ConversationView
    AUTHORIZATION: Hospital coordinators of the request, or a donor who already
                   responded to it.
    STATE CHANGES: Conversation(OPEN) created if absent
    ERRORS: 403 NOT_A_PARTICIPANT, 404 REQUEST_NOT_FOUND, 409 CONFLICT if the
            counterparty is not a participant
    DEPENDENCIES: BloodRequest, DonorResponse/OrganizationResponse
    MUST NOT: create threads decoupled from a BloodRequest
    """
    blood_request = db.get(BloodRequest, payload.blood_request_id)
    if blood_request is None:
        raise NotFoundError("Blood request not found", code=ErrorCode.REQUEST_NOT_FOUND)

    is_hospital_staff = principal.organization_id == blood_request.hospital_id
    donor_profile = db.execute(
        select(DonorProfile).where(DonorProfile.user_id == principal.user_id)
    ).scalar_one_or_none()

    if is_hospital_staff:
        counterparty_id = payload.counterparty_user_id
        if not counterparty_id:
            raise ConflictError(
                "counterpartyUserId is required for hospital-initiated threads",
                code=ErrorCode.VALIDATION_ERROR,
            )
        counterparty = db.get(User, counterparty_id)
        if counterparty is None:
            raise NotFoundError("Counterparty not found")
        organization_id = blood_request.hospital_id
        counterparty_role = ConversationParticipantRole.DONOR
        donor_id = counterparty.id
        donor_response_id = None
    elif donor_profile is not None:
        from bloodlink_api.db.models.donors import DonorResponse

        response = db.execute(
            select(DonorResponse).where(
                DonorResponse.blood_request_id == blood_request.id,
                DonorResponse.donor_profile_id == donor_profile.id,
            )
        ).scalar_one_or_none()
        if response is None:
            raise ForbiddenError(
                "Accept this request before coordinating with the hospital",
                code=ErrorCode.NOT_A_PARTICIPANT,
            )
        organization_id = blood_request.hospital_id
        counterparty_role = ConversationParticipantRole.HOSPITAL
        donor_id = principal.user_id
        donor_response_id = response.id
    else:
        # Blood centre responding to the request.
        response = db.execute(
            select(OrganizationResponse).where(
                OrganizationResponse.blood_request_id == blood_request.id,
                OrganizationResponse.organization_id == principal.organization_id,
            )
        ).scalar_one_or_none()
        if response is None or principal.organization_id is None:
            raise ForbiddenError(
                "Respond to this request before coordinating",
                code=ErrorCode.NOT_A_PARTICIPANT,
            )
        organization_id = principal.organization_id
        counterparty_role = ConversationParticipantRole.BLOOD_CENTRE
        donor_id = principal.user_id
        donor_response_id = None

    existing = db.execute(
        select(Conversation).where(
            Conversation.blood_request_id == blood_request.id,
            Conversation.organization_id == organization_id,
            Conversation.donor_id == donor_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return success(request, _serialise(db, existing, viewer_id=principal.user_id))

    conversation = Conversation(
        blood_request_id=blood_request.id,
        organization_id=organization_id,
        donor_id=donor_id,
        donor_response_id=donor_response_id,
        counterparty_role=counterparty_role,
        status=ConversationStatus.OPEN,
    )
    db.add(conversation)
    db.commit()
    return success(request, _serialise(db, conversation, viewer_id=principal.user_id))


@router.get("/{conversation_id}", summary="Read a thread and its messages")
def read_conversation(
    conversation_id: str,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=300),
) -> dict:
    """Return a thread with its most recent messages.

    OWNER: D4
    PURPOSE: Coordination thread view.
    INPUT: path conversationId, limit?
    OUTPUT: { conversation: ConversationView, messages: [MessageView] }
    AUTHORIZATION: Participants only (donor, counterparty, organization staff).
    STATE CHANGES: none
    ERRORS: 403 FORBIDDEN, 404 CONVERSATION_NOT_FOUND
    PRIVACY: message bodies only; no contact details in the payload
    """
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found", code=ErrorCode.CONVERSATION_NOT_FOUND)
    _assert_can_access(conversation, principal.user, principal.organization_id)

    messages = db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    ).scalars()
    serialised = [
        {
            "id": message.id,
            "senderId": message.sender_id,
            "mine": message.sender_id == principal.user_id,
            "content": message.content,
            "createdAt": iso(message.created_at),
            "readAt": iso(message.read_at),
        }
        for message in reversed(list(messages))
    ]
    return success(
        request,
        {"conversation": _serialise(db, conversation, viewer_id=principal.user_id), "messages": serialised},
    )


@router.post("/{conversation_id}/messages", status_code=status.HTTP_201_CREATED, summary="Post a message")
def post_message(
    conversation_id: str,
    payload: MessageRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    """Append a message to a coordination thread.

    OWNER: D4
    PURPOSE: Request-scoped coordination (phones/addresses belong outside).
    INPUT: MessageRequest { content }
    OUTPUT: 201 MessageView
    AUTHORIZATION: Participants only.
    STATE CHANGES: Message(created); Conversation.lastMessageAt; counterparty notified
    ERRORS: 403 NOT_A_PARTICIPANT, 404 CONVERSATION_NOT_FOUND,
            409 CONVERSATION_CLOSED, 422 MESSAGE_TOO_LONG / VALIDATION_ERROR
    DEPENDENCIES: notifications module
    MUST NOT: carry attachments in the MVP; accept messages on closed threads
    PRIVACY: notification payload contains no message body, only the thread link
    """
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found", code=ErrorCode.CONVERSATION_NOT_FOUND)
    _assert_can_access(conversation, principal.user, principal.organization_id)
    if conversation.status is not ConversationStatus.OPEN:
        raise ConflictError("This coordination thread is closed", code=ErrorCode.CONVERSATION_CLOSED)

    if len(payload.content or "") > MESSAGE_MAX_LENGTH:
        raise ConflictError(
            f"Keep messages under {MESSAGE_MAX_LENGTH} characters", code=ErrorCode.MESSAGE_TOO_LONG
        )
    content = validate_message_content(payload.content)

    message = Message(
        conversation_id=conversation.id, sender_id=principal.user_id, content=content, created_at=utcnow()
    )
    db.add(message)
    conversation.last_message_at = message.created_at

    # Notify the other side — recipients of a hospital thread are the coordinators.
    if principal.organization_id == conversation.organization_id:
        recipients = [conversation.donor_id]
    else:
        recipients = [
            user.id
            for user in db.execute(
                select(User).where(
                    User.organization_id == conversation.organization_id, User.is_active.is_(True)
                )
            ).scalars()
        ]
    for recipient_id in recipients:
        if recipient_id == principal.user_id:
            continue
        notification_service.create_notification(
            db,
            user_id=recipient_id,
            notification_type=NotificationType.MESSAGE_RECEIVED,
            data={
                "conversationId": conversation.id,
                "requestId": conversation.blood_request_id,
                "url": f"/messages/{conversation.id}",
            },
            blood_request_id=conversation.blood_request_id,
        )

    db.commit()
    return success(
        request,
        {
            "id": message.id,
            "senderId": message.sender_id,
            "mine": True,
            "content": message.content,
            "createdAt": iso(message.created_at),
        },
    )


@router.post("/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT, summary="Mark a thread read")
def mark_read(
    conversation_id: str, principal: CurrentPrincipal, db: Session = Depends(get_db)
) -> Response:
    """Mark every message from the counterparty as read.

    OWNER: D4
    PURPOSE: Read receipts (``Message.readAt``, spec §13).
    INPUT: path conversationId
    OUTPUT: 204 No Content
    AUTHORIZATION: Participants only.
    STATE CHANGES: Message.readAt for messages not sent by the caller
    ERRORS: 403 FORBIDDEN, 404 CONVERSATION_NOT_FOUND
    """
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found", code=ErrorCode.CONVERSATION_NOT_FOUND)
    _assert_can_access(conversation, principal.user, principal.organization_id)

    rows = db.execute(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.sender_id != principal.user_id,
            Message.read_at.is_(None),
        )
    ).scalars()
    now = utcnow()
    for message in rows:
        message.read_at = now
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{conversation_id}/close", summary="Close a coordination thread")
def close_conversation(
    conversation_id: str, request: Request, principal: CurrentPrincipal, db: Session = Depends(get_db)
) -> dict:
    """Close a thread once coordination is done.

    OWNER: D4
    PURPOSE: Thread hygiene; closing does not affect request state (D3 owns that).
    INPUT: path conversationId
    OUTPUT: ConversationView
    AUTHORIZATION: Hospital coordinators of the request.
    STATE CHANGES: Conversation(status=CLOSED, closedAt)
    ERRORS: 403 FORBIDDEN, 404 CONVERSATION_NOT_FOUND
    MUST NOT: change BloodRequest status
    """
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation not found", code=ErrorCode.CONVERSATION_NOT_FOUND)
    if principal.organization_id != conversation.organization_id:
        raise ForbiddenError("Only the hospital coordinating this request can close the thread")

    conversation.status = ConversationStatus.CLOSED
    conversation.closed_at = utcnow()
    db.commit()
    return success(request, _serialise(db, conversation, viewer_id=principal.user_id))


MODULE = register_module(
    ModuleSpec(
        key="communication",
        owner="D4",
        domain="communication",
        api_prefix="/conversations",
        description="Request-scoped coordination threads and messages (REST only).",
        foundation_status="COMPLETE",
        router=router,
        depends_on=("auth", "responses", "notifications"),
    )
)
