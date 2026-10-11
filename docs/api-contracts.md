# BloodLink — API Contracts

_Generated from endpoint docstrings by `scripts/export_contracts.py` on 2026-10-11 15:17 UTC._

70 endpoints across 12 modules.

Every response uses the canonical envelope:

```json
{ "data": ..., "meta": { "requestId": "...", "generatedAt": "..." }, "error": null }
```

Every failure uses:

```json
{ "data": null, "meta": {...}, "error": { "code": "ERROR_CODE", "message": "...", "details": [] } }
```

## Ownership summary

| Owner | Endpoints |
| --- | --- |
| D1 | 25 |
| D2 | 5 |
| D3 | 11 |
| D4 | 29 |

## D1 — Lead / platform foundation — architecture, auth, RBAC, contracts, design system, shells, schema integration, CI rules.

### `GET /`

**Owner:** D1  ·  **Status:** IMPLEMENTED

Point humans and probes at the docs, health check and prefix.

- **Authorization:** Public.
- **Input:** none
- **Output:** { service, version, docs, health }
- **State changes:** none
- **Privacy:** no configuration or secrets are returned

### `GET /api/v1/admin/audit`

**Owner:** D1  ·  **Status:** COMPLETE

Accountability for consequential actions.

- **Authorization:** ADMIN only.
- **Input:** action?, page, pageSize
- **Output:** Page<AuditEntry>
- **State changes:** none
- **Errors:** 403 FORBIDDEN
- **Dependencies:** none
- **Must not:** allow edits to audit history
- **Privacy:** audit detail is constrained to ids and status codes, no patient data

### `GET /api/v1/admin/organizations`

**Owner:** D1  ·  **Status:** COMPLETE

Administration console for hospital / blood centre onboarding.

- **Authorization:** ADMIN only.
- **Input:** verificationStatus?, page, pageSize
- **Output:** Page<OrganizationAdminView>
- **State changes:** none
- **Errors:** 403 FORBIDDEN
- **Dependencies:** none
- **Must not:** mutate verification state (see the verify/suspend endpoints)
- **Privacy:** exact coordinates are withheld; only city/district are returned

### `POST /api/v1/admin/organizations/{organization_id}/suspend`

**Owner:** D1  ·  **Status:** COMPLETE

Safety valve for misuse or expired credentials.

- **Authorization:** ADMIN only.
- **Input:** path organizationId
- **Output:** OrganizationAdminView
- **State changes:** Organization.verificationStatus=SUSPENDED
- **Errors:** 404 ORGANIZATION_NOT_FOUND
- **Dependencies:** none
- **Must not:** delete data — suspension is reversible and audited

### `POST /api/v1/admin/organizations/{organization_id}/verify`

**Owner:** D1  ·  **Status:** COMPLETE

Manual verification of hospitals and blood centres.

- **Authorization:** ADMIN only.
- **Input:** path organizationId
- **Output:** OrganizationAdminView
- **State changes:** Organization.verificationStatus=VERIFIED, verifiedAt, verifiedByUserId
- **Errors:** 404 ORGANIZATION_NOT_FOUND, 409 CONFLICT when already suspended/verified
- **Dependencies:** none
- **Must not:** verify an organization without an out-of-band document check
- **Privacy:** audit entry records the acting administrator only

### `GET /api/v1/admin/platform/modules`

**Owner:** D1  ·  **Status:** COMPLETE

Single source of truth for the ownership / status map in the docs.

- **Authorization:** ADMIN only.
- **Input:** none
- **Output:** { modules: [ModuleSummary] }
- **State changes:** none
- **Errors:** 403 FORBIDDEN
- **Dependencies:** module registry
- **Must not:** reveal secrets or connection strings
- **Privacy:** metadata only

### `GET /api/v1/admin/requests/alerts`

**Owner:** D1  ·  **Status:** COMPLETE

Help operations spot requests stuck in the failure path.

- **Authorization:** ADMIN only.
- **Input:** none
- **Output:** { items: [RequestAlert] }
- **State changes:** none
- **Errors:** 403 FORBIDDEN
- **Dependencies:** BloodRequest (D3)
- **Must not:** mutate request state — this is read-only oversight
- **Privacy:** request ids, group, component, status only; no patient identity

### `GET /api/v1/admin/users`

**Owner:** D1  ·  **Status:** COMPLETE

Account oversight and support.

- **Authorization:** ADMIN only.
- **Input:** role?, page, pageSize
- **Output:** Page<UserAdminView>
- **State changes:** none
- **Errors:** 403 FORBIDDEN
- **Dependencies:** none
- **Must not:** expose password hashes or refresh tokens
- **Privacy:** email + role only; no donor location data

### `POST /api/v1/admin/users/{user_id}/deactivate`

**Owner:** D1  ·  **Status:** COMPLETE

Abuse handling / offboarding.

- **Authorization:** ADMIN only; an admin cannot deactivate themselves.
- **Input:** path userId
- **Output:** UserAdminView
- **State changes:** User.isActive=false
- **Errors:** 404 NOT_FOUND, 409 CONFLICT on self-deactivation
- **Dependencies:** none

### `POST /api/v1/auth/change-password`

**Owner:** D1  ·  **Status:** COMPLETE

Credential rotation by the account owner.

- **Authorization:** Any authenticated user.
- **Input:** ChangePasswordRequest
- **Output:** 204 No Content
- **State changes:** User.password_hash; all RefreshToken(revoked)
- **Errors:** 401 INVALID_CREDENTIALS
- **Dependencies:** none
- **Must not:** accept the change without the current password

### `POST /api/v1/auth/login`

**Owner:** D1  ·  **Status:** COMPLETE

Exchange credentials for a session.

- **Authorization:** Public.
- **Input:** LoginRequest
- **Output:** SessionResponse
- **State changes:** User.last_login_at; RefreshToken(created)
- **Errors:** 401 INVALID_CREDENTIALS
- **Dependencies:** none
- **Must not:** reveal whether the email exists
- **Privacy:** identical error for unknown email and wrong password

### `POST /api/v1/auth/logout`

**Owner:** D1  ·  **Status:** COMPLETE

End a session server-side.

- **Authorization:** Valid refresh token.
- **Input:** RefreshRequest
- **Output:** 204 No Content
- **State changes:** RefreshToken(revoked)
- **Errors:** 204 even when the token is already gone (idempotent)
- **Dependencies:** none
- **Must not:** require an access token (it may already be expired)

### `GET /api/v1/auth/me`

**Owner:** D1  ·  **Status:** COMPLETE

Drive role-aware navigation and route guards in the web client.

- **Authorization:** Any authenticated user.
- **Input:** none
- **Output:** CurrentUserResponse
- **State changes:** none
- **Errors:** 401 UNAUTHENTICATED
- **Dependencies:** none
- **Must not:** return capabilities the role does not actually hold
- **Privacy:** no donor location or contact detail is included

### `POST /api/v1/auth/refresh`

**Owner:** D1  ·  **Status:** COMPLETE

Silent session renewal for the web client.

- **Authorization:** Valid refresh token.
- **Input:** RefreshRequest
- **Output:** SessionResponse
- **State changes:** old RefreshToken(revoked), new RefreshToken(created)
- **Errors:** 401 TOKEN_EXPIRED / TOKEN_INVALID
- **Dependencies:** none
- **Must not:** extend a revoked or expired session
- **Privacy:** refresh tokens are stored only as SHA-256 digests

### `POST /api/v1/auth/register`

**Owner:** D1  ·  **Status:** COMPLETE

Create an individual, hospital or blood centre account and open a session.

- **Authorization:** Public.
- **Input:** RegisterRequest
- **Output:** SessionResponse
- **State changes:** User(ACTIVE); for hospital/blood centre: Organization(PENDING)
- **Errors:** 409 EMAIL_ALREADY_REGISTERED, 422 VALIDATION_ERROR
- **Dependencies:** none
- **Must not:** verify the organization, issue ADMIN accounts, leak password hashes
- **Privacy:** organization coordinates are stored for matching and never returned exactly

### `GET /api/v1/organizations`

**Owner:** D1  ·  **Status:** COMPLETE

Shared directory used by hospital discovery (D2) and donor subscriptions (D4).

- **Authorization:** Any authenticated user; suspended organizations are hidden.
- **Input:** orgType?, q?, page, pageSize
- **Output:** Page<OrganizationView>
- **State changes:** none
- **Errors:** 401 UNAUTHENTICATED
- **Dependencies:** none
- **Must not:** return coordinates, contact phone numbers or registration numbers
- **Privacy:** name + locality only (spec §21)

### `GET /api/v1/organizations/mine`

**Owner:** D1  ·  **Status:** COMPLETE

Drives the organization workspace header and the pending-verification banner.

- **Authorization:** Organization users only.
- **Input:** none
- **Output:** OrganizationView + verification detail
- **State changes:** none
- **Errors:** 403 FORBIDDEN, 404 ORGANIZATION_NOT_FOUND
- **Privacy:** includes the organization's own contact details (self-view)

### `PATCH /api/v1/organizations/mine`

**Owner:** D1  ·  **Status:** COMPLETE

Keep facility details and coordinates current for matching and routing.

- **Authorization:** Organization users; coordinates are organization-internal data.
- **Input:** OrganizationUpdateRequest
- **Output:** OrganizationView
- **State changes:** Organization fields updated
- **Errors:** 403 FORBIDDEN, 422 VALIDATION_ERROR
- **Dependencies:** ``bloodlink_validation.validate_coordinates``
- **Must not:** change verificationStatus (admin-only) or orgType
- **Privacy:** coordinates are stored internally and never returned by the public directory

### `GET /api/v1/organizations/{organization_id}`

**Owner:** D1  ·  **Status:** COMPLETE

Detail view from directory/search results.

- **Authorization:** Any authenticated user.
- **Input:** path organizationId
- **Output:** OrganizationView (+ distanceBand for donors)
- **State changes:** none
- **Errors:** 404 ORGANIZATION_NOT_FOUND
- **Must not:** expose exact coordinates — only a rounded distance band (spec §21)

### `GET /api/v1/platform/health`

**Owner:** D1  ·  **Status:** COMPLETE

Liveness probe for the web app and deployments.

- **Authorization:** Public.
- **Input:** none
- **Output:** { status, version, env, database, modules }
- **State changes:** none
- **Errors:** 200 with status=DEGRADED when the database is unreachable
- **Privacy:** no configuration secrets are returned

### `GET /api/v1/platform/modules`

**Owner:** D1  ·  **Status:** COMPLETE

Machine-readable version of docs/ownership.md for dashboards.

- **Authorization:** Public (metadata only, no secrets).
- **Input:** none
- **Output:** { modules: [{ key, owner, domain, prefix, status }] }
- **State changes:** none

### `GET /api/v1/platform/version`

**Owner:** D1  ·  **Status:** COMPLETE

Client build diagnostics.

- **Authorization:** Public.
- **Input:** none
- **Output:** { version, apiPrefix, foundation }

### `GET /api/v1/users/me/donations`

**Owner:** D1  ·  **Status:** COMPLETE

Personal donation record and cooldown context.

- **Authorization:** Self only.
- **Input:** none
- **Output:** { items: [DonationRecordView] }
- **State changes:** none
- **Errors:** 401 UNAUTHENTICATED
- **Dependencies:** DonationRecord (D4)
- **Must not:** expose screening or clinical outcome data (BloodLink does not hold it)
- **Privacy:** hospital name + date + component only

### `GET /api/v1/users/me/profile`

**Owner:** D1  ·  **Status:** COMPLETE

Profile screen.

- **Authorization:** Any authenticated user (self only).
- **Input:** none
- **Output:** UserProfile
- **State changes:** none
- **Errors:** 401 UNAUTHENTICATED
- **Must not:** read another user's profile from this endpoint
- **Privacy:** no donor coordinates; phone is the user's own

### `PATCH /api/v1/users/me/profile`

**Owner:** D1  ·  **Status:** COMPLETE

Let users keep contact details current.

- **Authorization:** Any authenticated user (self only).
- **Input:** ProfileUpdateRequest
- **Output:** UserProfile
- **State changes:** User.fullName, User.phone
- **Errors:** 422 VALIDATION_ERROR
- **Must not:** change role, organization or verification state
- **Privacy:** email changes require a separate verification flow (not in MVP)

## D2 — Individual & PatientNeed — hospital discovery, submission, individual history.

### `GET /api/v1/patient-needs`

**Owner:** D2  ·  **Status:** IMPLEMENTED

Individual request/history UI (spec §5).

- **Authorization:** Self only — never another user's submissions.
- **Input:** status?, page, pageSize
- **Output:** Page<PatientNeedResponse>
- **State changes:** none
- **Errors:** 401 UNAUTHENTICATED, 422 VALIDATION_ERROR
- **Dependencies:** PatientNeed
- **Must not:** expose hospital-internal review notes
- **Privacy:** no donor or third-party data

### `POST /api/v1/patient-needs`

**Owner:** D2  ·  **Status:** IMPLEMENTED

Let an individual (or hospital staff on a patient's behalf) request blood from a chosen hospital.

- **Authorization:** Any authenticated user; hospitalId must reference a VERIFIED hospital.
- **Input:** CreatePatientNeedRequest
- **Output:** 201 PatientNeedResponse { id, status: PENDING_HOSPITAL_REVIEW, ... }
- **State changes:** PatientNeed(status=PENDING_HOSPITAL_REVIEW); Notification(NEED_SUBMITTED) to the hospital's active staff
- **Errors:** 404 ORGANIZATION_NOT_FOUND, 409 ORGANIZATION_NOT_VERIFIED / ORGANIZATION_SUSPENDED, 422 NEED_REQUIRED_BY_IN_PAST / VALIDATION_ERROR
- **Dependencies:** Organization (D1), bloodlink_validation, notifications (D4)
- **Must not:** create a BloodRequest, contact donors, or notify donors
- **Privacy:** additionalNotes is coordination context — reject anything that looks like a diagnosis, test result or medical record

### `GET /api/v1/patient-needs/reference/hospitals`

**Owner:** D2  ·  **Status:** IMPLEMENTED

Hospital discovery for individuals (spec §5).

- **Authorization:** Any authenticated user.
- **Input:** q?, city?, district?
- **Output:** { items: [HospitalDiscoveryView] } { id, name, city, district, distanceBand? }
- **State changes:** none
- **Errors:** 401 UNAUTHENTICATED, 422 VALIDATION_ERROR
- **Dependencies:** Organization (D1, VERIFIED hospitals only), geo distance bands
- **Must not:** return exact coordinates — only coarse distance bands (spec §21)
- **Privacy:** expose name + locality + distance band only

### `GET /api/v1/patient-needs/{need_id}`

**Owner:** D2  ·  **Status:** IMPLEMENTED

Submission detail screen, including the hospital's decision.

- **Authorization:** Submitter only (org users see needs for their hospital through the D3 review endpoints). ADMIN for oversight.
- **Input:** path needId
- **Output:** PatientNeedResponse
- **State changes:** none
- **Errors:** 404 NEED_NOT_FOUND
- **Dependencies:** PatientNeed
- **Must not:** return another submitter's need — a foreign id answers 404, not 403
- **Privacy:** rejection reason is submitter-visible; internal memos are not stored here

### `POST /api/v1/patient-needs/{need_id}/cancel`

**Owner:** D2  ·  **Status:** IMPLEMENTED

Submitter-controlled cancellation before review.

- **Authorization:** Submitter only.
- **Input:** path needId, optional { reason }
- **Output:** PatientNeedResponse (status CANCELLED)
- **State changes:** PatientNeed.status=PENDING_HOSPITAL_REVIEW -> CANCELLED
- **Errors:** 404 NEED_NOT_FOUND, 409 NEED_NOT_CANCELLABLE (already reviewed/converted)
- **Dependencies:** PatientNeed
- **Must not:** cancel a need that already produced a BloodRequest — that request must be cancelled through the D3 lifecycle so backup coordination can run
- **Privacy:** none

## D3 — Hospital & BloodRequest — review gate, request lifecycle, responders, fulfilment.

### `GET /api/v1/blood-requests`

**Owner:** D3  ·  **Status:** IMPLEMENTED

Hospital dashboard of open and historical requests.

- **Authorization:** HOSPITAL users, verified org, own organization only.
- **Input:** status?, urgency?, page, pageSize
- **Output:** Page<BloodRequestResponse>
- **State changes:** none
- **Errors:** 403 ORGANIZATION_NOT_VERIFIED / FORBIDDEN
- **Dependencies:** BloodRequest
- **Must not:** leak needs from other hospitals
- **Privacy:** response counts only, never patient identity

### `POST /api/v1/blood-requests`

**Owner:** D3  ·  **Status:** IMPLEMENTED

Turn a verified PatientNeed into an actionable request.

- **Authorization:** HOSPITAL users only, verified org, need belongs to this hospital.
- **Input:** CreateBloodRequestRequest
- **Output:** 201 BloodRequestResponse (status OPEN)
- **State changes:** PatientNeed(APPROVED -> CONVERTED); BloodRequest(OPEN); BloodRequestEvent(REQUEST_CREATED); tier-1 outreach dispatched via D4
- **Errors:** 403 ORGANIZATION_NOT_VERIFIED, 404 NEED_NOT_FOUND, 409 NEED_ALREADY_REVIEWED
- **Dependencies:** Approved PatientNeed, ``bloodlink_validation.validate_units``, D4 outreach
- **Must not:** perform donor matching inline, send push notifications directly, or manage donor acceptance — those are D4 (spec §15 example contract)
- **Privacy:** no patient identity in the request or its events

### `GET /api/v1/blood-requests/nearby`

**Owner:** D3  ·  **Status:** IMPLEMENTED

Blood-centre discovery of requests it can support.

- **Authorization:** BLOOD_CENTRE users in a verified organization.
- **Input:** radiusKm?, bloodGroup?, component?
- **Output:** Page<NearbyRequestView> (distance is returned as a coarse band)
- **State changes:** none
- **Errors:** 403 ORGANIZATION_NOT_VERIFIED
- **Dependencies:** bloodlink_api.core.geo distance helpers
- **Must not:** expose the requesting hospital's patient details
- **Privacy:** request id, group, component, urgency, distance band, hospital name

### `GET /api/v1/blood-requests/{request_id}`

**Owner:** D3  ·  **Status:** IMPLEMENTED

Coordination workspace for hospital staff.

- **Authorization:** Owning hospital users (ADMIN oversight reads via /admin).
- **Input:** path requestId
- **Output:** BloodRequestDetailResponse
- **State changes:** none
- **Errors:** 403 FORBIDDEN, 404 REQUEST_NOT_FOUND
- **Dependencies:** BloodRequest, BloodRequestEvent, DonorResponse (read-only, D4)
- **Must not:** expose donor exact location or contact data (spec §21)
- **Privacy:** donors appear as display name + distance band + status only

### `POST /api/v1/blood-requests/{request_id}/confirm-fulfillment`

**Owner:** D3  ·  **Status:** IMPLEMENTED

Terminal confirmation; BloodLink does not issue blood (spec §2).

- **Authorization:** Owning hospital users, verified org.
- **Input:** path requestId, optional { donorProfileIds, hospitalReference }
- **Output:** BloodRequestResponse (status FULFILLED)
- **State changes:** BloodRequest(FULFILLMENT_CONFIRMED -> FULFILLED); DonationRecord(s) created through D4's donations module for the donors who actually donated; their cooldown starts
- **Errors:** 404 REQUEST_NOT_FOUND, 409 REQUEST_INVALID_TRANSITION, 409 DONATION_CONFIRMATION_INCOMPLETE
- **Dependencies:** D4 donations module (this is the ONLY path that creates a DonationRecord — acceptance alone never does, spec §10)
- **Must not:** record screening results or medical clearance
- **Privacy:** fulfilment records hold no patient data

### `GET /api/v1/blood-requests/{request_id}/outreach`

**Owner:** D3  ·  **Status:** IMPLEMENTED

Let hospital staff judge whether to expand outreach or go to backup.

- **Authorization:** Owning hospital users, verified org.
- **Input:** path requestId
- **Output:** { tiers: [...], notified: n, accepted: n, standby: n, withdrawn: n }
- **State changes:** none
- **Errors:** 404 REQUEST_NOT_FOUND
- **Dependencies:** DonorOutreach, DonorResponse (D4, read-only)
- **Must not:** expose donor identities beyond what the hospital already sees in the response list
- **Privacy:** aggregate counts by distance tier

### `POST /api/v1/blood-requests/{request_id}/select-donor`

**Owner:** D3  ·  **Status:** IMPLEMENTED

Fulfilment coordination (spec §10).

- **Authorization:** Owning hospital users, verified org.
- **Input:** SelectDonorRequest
- **Output:** { selected: DonorResponseView, standby: [DonorResponseView] }
- **State changes:** DonorResponse(SELECTED) for the chosen donor; DonorResponse(STANDBY, standbyStatus=STANDBY) for the others; BloodRequest advances to COORDINATING through the legal path
- **Errors:** 404 RESPONSE_NOT_FOUND, 409 DONOR_NOT_SELECTABLE / REQUEST_TERMINAL
- **Dependencies:** D4 response module (``bloodlink_api.modules.responses.service``)
- **Must not:** notify donors directly — notifications go through D4's service
- **Privacy:** only display name, distance band and response status leave this endpoint

### `POST /api/v1/blood-requests/{request_id}/transition`

**Owner:** D3  ·  **Status:** IMPLEMENTED

Single controlled entry point for every lifecycle change.

- **Authorization:** Owning hospital users; ADMIN oversight is read-only elsewhere.
- **Input:** TransitionRequest { toStatus, reason? }
- **Output:** BloodRequestResponse
- **State changes:** BloodRequest.status; BloodRequestEvent(from,to,reason); on BACKUP_REQUIRED: backup_reason set, tier-2 outreach requested; on FULFILLMENT_PENDING: donors notified; on terminal status: active responses released and closedAt set
- **Errors:** 404 REQUEST_NOT_FOUND, 409 REQUEST_INVALID_TRANSITION / REQUEST_TERMINAL
- **Dependencies:** ``BLOOD_REQUEST_TRANSITIONS`` (D1 contract), D4 matching + notifications
- **Must not:** bypass the transition table; a first donor acceptance must not auto-close the request (spec §9)
- **Privacy:** reasons are coordination notes, not clinical notes

### `GET /api/v1/hospital/patient-needs`

**Owner:** D3  ·  **Status:** IMPLEMENTED

The hospital's inbox of incoming needs (spec §5).

- **Authorization:** HOSPITAL users in a verified organization, own hospital only.
- **Input:** status?, page, pageSize
- **Output:** Page<PatientNeedResponse>
- **State changes:** none
- **Errors:** 403 ORGANIZATION_NOT_VERIFIED / FORBIDDEN
- **Dependencies:** PatientNeed (D2 model)
- **Must not:** show pending needs addressed to a different hospital
- **Privacy:** submitter name + contact window only; no diagnosis stored or returned

### `GET /api/v1/hospital/patient-needs/{need_id}`

**Owner:** D3  ·  **Status:** IMPLEMENTED

Hospital review screen.

- **Authorization:** HOSPITAL users of the addressed hospital only.
- **Input:** path needId
- **Output:** PatientNeedResponse
- **State changes:** none
- **Errors:** 404 NEED_NOT_FOUND, 403 FORBIDDEN
- **Dependencies:** PatientNeed
- **Must not:** expose data to blood centres or other hospitals — a foreign id is 404
- **Privacy:** notes are coordination context; the hospital already owns the clinical relationship

### `POST /api/v1/hospital/patient-needs/{need_id}/review`

**Owner:** D3  ·  **Status:** IMPLEMENTED

Gate between a request submitted by an individual and an official BloodRequest (spec §8 flow).

- **Authorization:** HOSPITAL users of the addressed hospital, verified org.
- **Input:** ReviewDecisionRequest { decision: APPROVED | REJECTED, reason? }
- **Output:** PatientNeedResponse
- **State changes:** PatientNeed(PENDING_HOSPITAL_REVIEW -> APPROVED | REJECTED); reviewedByUserId, reviewedAt, reviewReason; Notification(NEED_REVIEWED) to the submitter
- **Errors:** 404 NEED_NOT_FOUND, 409 NEED_ALREADY_REVIEWED
- **Dependencies:** PatientNeed; notification request to D4 for the submitter
- **Must not:** create the BloodRequest (separate explicit step: POST /blood-requests), or contact donors
- **Privacy:** reason is shared with the submitter and must stay non-clinical

## D4 — Donor & coordination — matching, responses, notifications, threads, donations, subscriptions.

### `GET /api/v1/blood-centres/responses`

**Owner:** D4  ·  **Status:** COMPLETE

Blood centre dashboard.

- **Authorization:** BLOOD_CENTRE users in their own organization.
- **Input:** none
- **Output:** { items: [OrganizationResponseView] }
- **State changes:** none
- **Errors:** 403 FORBIDDEN
- **Privacy:** hospital name + request status only, no patient data

### `POST /api/v1/blood-centres/responses`

**Owner:** D4  ·  **Status:** COMPLETE

OrganizationResponse flow (spec §7).

- **Authorization:** BLOOD_CENTRE users in a VERIFIED organization.
- **Input:** OrganizationResponseRequest
- **Output:** 201 OrganizationResponseView
- **State changes:** OrganizationResponse(AVAILABLE|PARTIAL|UNAVAILABLE); hospital coordinators notified
- **Errors:** 403 ORGANIZATION_NOT_VERIFIED, 404 REQUEST_NOT_FOUND, 409 ORGANIZATION_RESPONSE_EXISTS
- **Dependencies:** notifications module
- **Must not:** modify the request lifecycle (D3 owns transitions), claim stock that BloodLink does not track, or expose donor data
- **Privacy:** notes are coordination text; no patient information

### `GET /api/v1/conversations`

**Owner:** D4  ·  **Status:** COMPLETE

Coordination inbox for donors, hospitals and blood centres.

- **Authorization:** Own donor threads, or all threads of the caller's organization.
- **Input:** status? (OPEN | CLOSED | ARCHIVED)
- **Output:** { items: [ConversationView], unreadTotal: int }
- **State changes:** none
- **Errors:** 401 UNAUTHENTICATED
- **Dependencies:** Conversation/Message
- **Must not:** expose threads the caller is not a participant in
- **Privacy:** counterparty display name only; no phone numbers or addresses

### `POST /api/v1/conversations`

**Owner:** D4  ·  **Status:** COMPLETE

Coordinating a concrete request without enabling social chat (§13).

- **Authorization:** Hospital coordinators of the request, or a donor who already responded to it.
- **Input:** StartConversationRequest { bloodRequestId, counterpartyUserId }
- **Output:** 201 ConversationView
- **State changes:** Conversation(OPEN) created if absent
- **Errors:** 403 NOT_A_PARTICIPANT, 404 REQUEST_NOT_FOUND, 409 CONFLICT if the counterparty is not a participant
- **Dependencies:** BloodRequest, DonorResponse/OrganizationResponse
- **Must not:** create threads decoupled from a BloodRequest

### `GET /api/v1/conversations/{conversation_id}`

**Owner:** D4  ·  **Status:** COMPLETE

Coordination thread view.

- **Authorization:** Participants only (donor, counterparty, organization staff).
- **Input:** path conversationId, limit?
- **Output:** { conversation: ConversationView, messages: [MessageView] }
- **State changes:** none
- **Errors:** 403 FORBIDDEN, 404 CONVERSATION_NOT_FOUND
- **Privacy:** message bodies only; no contact details in the payload

### `POST /api/v1/conversations/{conversation_id}/close`

**Owner:** D4  ·  **Status:** COMPLETE

Thread hygiene; closing does not affect request state (D3 owns that).

- **Authorization:** Hospital coordinators of the request.
- **Input:** path conversationId
- **Output:** ConversationView
- **State changes:** Conversation(status=CLOSED, closedAt)
- **Errors:** 403 FORBIDDEN, 404 CONVERSATION_NOT_FOUND
- **Must not:** change BloodRequest status

### `POST /api/v1/conversations/{conversation_id}/messages`

**Owner:** D4  ·  **Status:** COMPLETE

Request-scoped coordination (phones/addresses belong outside).

- **Authorization:** Participants only.
- **Input:** MessageRequest { content }
- **Output:** 201 MessageView
- **State changes:** Message(created); Conversation.lastMessageAt; counterparty notified
- **Errors:** 403 NOT_A_PARTICIPANT, 404 CONVERSATION_NOT_FOUND, 409 CONVERSATION_CLOSED, 422 MESSAGE_TOO_LONG / VALIDATION_ERROR
- **Dependencies:** notifications module
- **Must not:** carry attachments in the MVP; accept messages on closed threads
- **Privacy:** notification payload contains no message body, only the thread link

### `POST /api/v1/conversations/{conversation_id}/read`

**Owner:** D4  ·  **Status:** COMPLETE

Read receipts (``Message.readAt``, spec §13).

- **Authorization:** Participants only.
- **Input:** path conversationId
- **Output:** 204 No Content
- **State changes:** Message.readAt for messages not sent by the caller
- **Errors:** 403 FORBIDDEN, 404 CONVERSATION_NOT_FOUND

### `GET /api/v1/donations`

**Owner:** D4  ·  **Status:** COMPLETE

Personal history + cooldown context (spec §5, §12).

- **Authorization:** Self only.
- **Input:** none
- **Output:** { items: [DonationView], totalUnits: int }
- **State changes:** none
- **Errors:** 401 UNAUTHENTICATED
- **Dependencies:** DonationRecord
- **Must not:** include screening results or medical clearance — BloodLink never receives them (§2)
- **Privacy:** hospital name, date, component, units only

### `GET /api/v1/donations/requests/{request_id}`

**Owner:** D4  ·  **Status:** COMPLETE

Let hospitals and the donor see what was actually recorded.

- **Authorization:** Hospital coordinators of the request, the donors involved, ADMIN.
- **Input:** path requestId
- **Output:** { items: [{ donorProfileId, displayName, units, confirmedAt }] }
- **State changes:** none
- **Errors:** 403 NOT_A_PARTICIPANT
- **Must not:** allow a blood centre to enumerate donors of a request
- **Privacy:** display name + units only; no location, no contact details

### `PATCH /api/v1/donor/availability`

**Owner:** D4  ·  **Status:** COMPLETE

Donors control when they can be matched (§11 notification preference).

- **Authorization:** Authenticated donor.
- **Input:** AvailabilityRequest
- **Output:** DonorProfileView
- **State changes:** DonorProfile.isAvailable / acceptsNotifications
- **Errors:** 403 DONOR_PROFILE_REQUIRED
- **Must not:** affect responses the donor already committed to

### `POST /api/v1/donor/blood-requests/{request_id}/accept`

**Owner:** D4  ·  **Status:** COMPLETE

The donor-side acceptance contract (spec §10).

- **Authorization:** Authenticated donor (profile required).
- **Input:** AcceptRequest { confirmation: "EXPLICIT", etaMinutes?, remarks? }
- **Output:** 201 DonorResponseView (status ACCEPTED)
- **State changes:** DonorResponse(ACCEPTED, confirmedAt); BloodRequest OPEN -> RESPONSES_RECEIVED (never closed); hospital coordinators notified
- **Errors:** 422 CONFIRMATION_REQUIRED (confirmation step skipped), 409 REQUEST_NOT_OPEN_FOR_RESPONSES, 409 DONOR_IN_COOLDOWN, 409 RESPONSE_ALREADY_EXISTS, 409 DONOR_NOT_ELIGIBLE_FOR_OUTREACH, 404 REQUEST_NOT_FOUND
- **Dependencies:** notifications module
- **Must not:** mark the request covered/fulfilled, mutate state when the confirmation step is cancelled, or treat acceptance as a donation
- **Privacy:** hospital sees the donor's name and distance band only

### `GET /api/v1/donor/lookup/donors`

**Owner:** D4  ·  **Status:** COMPLETE

Placeholder documenting a deliberately *rejected* capability: a browsable donor directory would break spec §21 (ordinary users must never receive donor locations/contact data).

- **Authorization:** none — always 404 by design.
- **Must not:** ever be implemented as a general donor directory. Matching is request-scoped and driven by an open BloodRequest (§11).

### `GET /api/v1/donor/matched-requests`

**Owner:** D4  ·  **Status:** COMPLETE

Donor discovery surface (web).

- **Authorization:** Authenticated user with a donor profile.
- **Input:** none (uses the caller's donor profile)
- **Output:** { items: [DonorRequestCard], donor: { bloodGroup, distanceBandNote } }
- **State changes:** none
- **Errors:** 403 DONOR_PROFILE_REQUIRED
- **Dependencies:** matching + geo helpers (D1), compatibility matrix (D1 contract)
- **Must not:** rank by anything other than distance for MVP; never decide medical eligibility; never expose patient identity (§2, §11, §21)
- **Privacy:** hospital name + coarse distance band only; no patient, no coordinates

### `GET /api/v1/donor/nearby-hospitals`

**Owner:** D4  ·  **Status:** COMPLETE

Subscription discovery.

- **Authorization:** Authenticated donor.
- **Input:** none
- **Output:** { items: [ { id, name, locationLabel, distanceBand } ] }
- **State changes:** none
- **Errors:** 403 DONOR_PROFILE_REQUIRED
- **Must not:** leak hospital exact coordinates (banded only, spec §21)

### `GET /api/v1/donor/profile`

**Owner:** D4  ·  **Status:** COMPLETE

Donor settings screen.

- **Authorization:** Authenticated donor.
- **Input:** none
- **Output:** DonorProfileView
- **State changes:** none
- **Errors:** 403 DONOR_PROFILE_REQUIRED
- **Must not:** return latitude/longitude (spec §21)

### `PUT /api/v1/donor/profile`

**Owner:** D4  ·  **Status:** COMPLETE

Opt into donation and manage matching inputs.

- **Authorization:** Any authenticated user (creates the capability on first save).
- **Input:** DonorProfileRequest
- **Output:** DonorProfileView
- **State changes:** DonorProfile(created|updated)
- **Errors:** 422 VALIDATION_ERROR (coordinates / fields)
- **Dependencies:** ``bloodlink_validation.validate_coordinates``
- **Must not:** determine medical eligibility; store screening data; return the coordinates that were submitted
- **Privacy:** coordinates stored as internal matching data only; ``area`` in the response is a ~5 km grid label

### `GET /api/v1/donor/responses`

**Owner:** D4  ·  **Status:** COMPLETE

Donor "my commitments" screen.

- **Authorization:** Self only.
- **Input:** none
- **Output:** { items: [DonorResponseView] }
- **State changes:** none
- **Errors:** 403 DONOR_PROFILE_REQUIRED
- **Privacy:** no hospital-internal notes

### `POST /api/v1/donor/responses/{response_id}/withdraw`

**Owner:** D4  ·  **Status:** COMPLETE

Donors must be able to step back; the hospital then needs backup.

- **Authorization:** The donor who owns the response.
- **Input:** path responseId, { reason? }
- **Output:** DonorResponseView (status WITHDRAWN)
- **State changes:** DonorResponse(WITHDRAWN); if the donor was SELECTED, the request moves to BACKUP_REQUIRED and the hospital is notified
- **Errors:** 403 FORBIDDEN, 404 RESPONSE_NOT_FOUND, 409 CONFLICT
- **Dependencies:** notifications module
- **Must not:** silently reopen a request without telling the hospital

### `GET /api/v1/donor/subscriptions`

**Owner:** D4  ·  **Status:** COMPLETE

Donor alert management (HospitalSubscription, spec §5, §12).

- **Authorization:** Self only.
- **Input:** none
- **Output:** { items: [HospitalSubscriptionView] }
- **State changes:** none
- **Privacy:** hospital name/locality only

### `POST /api/v1/donor/subscriptions`

**Owner:** D4  ·  **Status:** COMPLETE

Donor networks (§2): follow a hospital and get alerts for matching requests.

- **Authorization:** Any authenticated user; hospital must be VERIFIED.
- **Input:** SubscriptionRequest { hospitalId, bloodGroups[], maxUrgency? }
- **Output:** 201 HospitalSubscriptionView
- **State changes:** HospitalSubscription(created), alert notification queued
- **Errors:** 404 ORGANIZATION_NOT_FOUND, 409 CONFLICT on duplicate
- **Dependencies:** notifications module
- **Must not:** subscribe a user to a suspended organization
- **Privacy:** the hospital does not receive the follower's location

### `DELETE /api/v1/donor/subscriptions/{subscription_id}`

**Owner:** D4  ·  **Status:** COMPLETE

Donor alert management.

- **Authorization:** Self only.
- **Input:** path subscriptionId
- **Output:** 204 No Content
- **State changes:** HospitalSubscription deleted
- **Errors:** 404 NOT_FOUND

### `POST /api/v1/matching/blood-requests/{request_id}/expand-outreach`

**Owner:** D4  ·  **Status:** IMPLEMENTED

Failure path recovery (spec §9): standby -> expanded outreach.

- **Authorization:** Hospital users of the requesting organization.
- **Input:** path requestId
- **Output:** { tier, notified: int }
- **State changes:** DonorOutreach rows for the new tier; notifications dispatched
- **Errors:** 404 REQUEST_NOT_FOUND, 403 FORBIDDEN
- **Dependencies:** matching service, notifications service
- **Must not:** notify the same donor twice for the same tier; bypass the privacy guard
- **Privacy:** payload contains group/component/urgency/distance band only

### `GET /api/v1/matching/config`

**Owner:** D4  ·  **Status:** IMPLEMENTED

Makes the tiering explicit to hospital staff ("should I widen the net?").

- **Authorization:** Any authenticated user (non-sensitive configuration).
- **Input:** none
- **Output:** { tiers: [{ tier, radiusKm, limit }], cooldownDays, ranking }
- **State changes:** none
- **Errors:** 401 UNAUTHENTICATED
- **Dependencies:** Settings (D1)
- **Must not:** reveal donor counts or identities
- **Privacy:** configuration only

### `GET /api/v1/notifications`

**Owner:** D4  ·  **Status:** COMPLETE

Web notification centre.

- **Authorization:** Self only.
- **Input:** unreadOnly?, limit?
- **Output:** { items: [NotificationView], unreadCount: int }
- **State changes:** none
- **Errors:** 401 UNAUTHENTICATED
- **Dependencies:** Notification ledger
- **Must not:** return another user's notifications
- **Privacy:** payloads are privacy-safe by construction (§12)

### `POST /api/v1/notifications/read`

**Owner:** D4  ·  **Status:** COMPLETE

Feed hygiene for the web client.

- **Authorization:** Self only.
- **Input:** MarkReadRequest
- **Output:** { updated: int }
- **State changes:** Notification.readAt
- **Errors:** 401 UNAUTHENTICATED

### `GET /api/v1/notifications/subscriptions`

**Owner:** D4  ·  **Status:** COMPLETE

Notification settings screen.

- **Authorization:** Self only.
- **Input:** none
- **Output:** { items: [PushSubscriptionView] }
- **State changes:** none
- **Privacy:** endpoints are returned truncated to host so they cannot be replayed

### `POST /api/v1/notifications/subscriptions`

**Owner:** D4  ·  **Status:** COMPLETE

Enable Web Push / service-worker delivery for this browser.

- **Authorization:** Self only.
- **Input:** PushSubscriptionRequest { endpoint, keys.p256dh, keys.auth }
- **Output:** 201 PushSubscriptionView
- **State changes:** PushSubscription(enabled=True, created or re-enabled)
- **Errors:** 422 VALIDATION_ERROR
- **Dependencies:** transport (``notifications/transport.py``)
- **Must not:** accept a subscription for another user
- **Privacy:** endpoint keys are stored for delivery and never returned in full

### `DELETE /api/v1/notifications/subscriptions/{subscription_id}`

**Owner:** D4  ·  **Status:** COMPLETE

Notification control, and the browser-unsubscribe path.

- **Authorization:** Self only.
- **Input:** path subscriptionId
- **Output:** 204 No Content
- **State changes:** PushSubscription.enabled=False
- **Errors:** 404 NOT_FOUND when the subscription is not the caller's
