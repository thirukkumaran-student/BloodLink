/**
 * Wire model for the BloodLink API (OWNER: D1).
 *
 * Plain JavaScript: the shapes are documented with JSDoc typedefs and the enum
 * values are exported as frozen constants so forms and filters can iterate them
 * instead of hard-coding strings. The API is the source of truth — when a
 * contract changes, update this file in the same PR (shared-file change: Lead
 * review, spec §24). `tests/test_web_contract_parity.py` fails the build when a
 * wire value here drifts from `packages/contracts`.
 *
 * The canonical envelope every endpoint returns (spec §14):
 *
 * @typedef {object} Envelope
 * @property {unknown} data
 * @property {{requestId?: string|null, generatedAt?: string, pagination?: Pagination}} meta
 * @property {null|{code: string, message: string, details: Array<{field?: string, message?: string}>}} error
 *
 * @typedef {object} Pagination
 * @property {number} total
 * @property {number} page
 * @property {number} pageSize
 * @property {number} pages
 * @property {boolean} hasNext
 *
 * @typedef {object} OrganizationSummary
 * @property {string} id
 * @property {string} name
 * @property {"HOSPITAL"|"BLOOD_CENTRE"} orgType
 * @property {"PENDING"|"VERIFIED"|"SUSPENDED"} verificationStatus
 * @property {string|null} [city]
 * @property {string|null} [district]
 * @property {string|null} [locationLabel]
 * @property {boolean} [isOperational]
 * @property {string|null} [distanceBand]
 *
 * @typedef {object} CurrentUser
 * @property {string} id
 * @property {string} email
 * @property {string} fullName
 * @property {string|null} [phone]
 * @property {"INDIVIDUAL"|"HOSPITAL"|"BLOOD_CENTRE"|"ADMIN"} role
 * @property {string} initials
 * @property {OrganizationSummary|null} organization
 * @property {string[]} capabilities
 * @property {boolean} hasDonorProfile
 * @property {string|null} [lastLoginAt]
 *
 * @typedef {object} SessionResponse
 * @property {string} accessToken
 * @property {string} refreshToken
 * @property {string} tokenType
 * @property {number} expiresIn
 * @property {CurrentUser} user
 *
 * @typedef {object} NotificationItem
 * @property {string} id
 * @property {string} type
 * @property {string} title
 * @property {string} body
 * @property {Record<string, unknown>} data
 * @property {string|null} readAt
 * @property {string} createdAt
 *
 * @typedef {object} DonorProfileView
 * @property {string} id
 * @property {string} bloodGroup
 * @property {string|null} [city]
 * @property {string|null} [district]
 * @property {string|null} [state]
 * @property {string|null} [area]              coarse ~5 km grid label, never coordinates
 * @property {boolean} isAvailable
 * @property {boolean} acceptsNotifications
 * @property {boolean} notifyEmergencyOnly
 * @property {string|null} [lastDonationAt]
 * @property {number} totalDonations
 * @property {number} cooldownDaysRemaining
 * @property {string[]} canDonateTo
 *
 * @typedef {object} DonorRequestCard
 * @property {string} id
 * @property {string} reference
 * @property {string} bloodGroup
 * @property {string} component
 * @property {number} unitsRequired
 * @property {number} unitsCoordinated
 * @property {"ROUTINE"|"URGENT"|"EMERGENCY"} urgency
 * @property {string} status
 * @property {string} requiredBy
 * @property {{id: string, name: string, locationLabel: string}|null} hospital
 * @property {string} distanceBand
 * @property {boolean} compatibleForDonor
 * @property {boolean} acceptingResponses
 *
 * @typedef {object} DonorResponseView
 * @property {string} id
 * @property {string} requestId
 * @property {string|null} requestReference
 * @property {string} status
 * @property {string} standbyStatus
 * @property {string|null} confirmedAt
 * @property {string|null} selectedAt
 * @property {string} createdAt
 *
 * @typedef {object} DonationView
 * @property {string} id
 * @property {string} confirmedAt
 * @property {string} bloodGroup
 * @property {string} component
 * @property {number} units
 * @property {string|null} hospitalReference
 *
 * @typedef {object} PatientNeedView
 * @property {string} id
 * @property {string} hospitalId
 * @property {{id: string, name: string, city?: string|null, locationLabel?: string|null}|null} [hospital]
 * @property {string} bloodGroup
 * @property {string} component
 * @property {number} units
 * @property {"ROUTINE"|"URGENT"|"EMERGENCY"} urgency
 * @property {string} requiredBy
 * @property {string|null} additionalNotes
 * @property {"PENDING_HOSPITAL_REVIEW"|"APPROVED"|"REJECTED"|"CONVERTED"|"CANCELLED"} status
 * @property {string|null} [reviewReason]
 * @property {string|null} [bloodRequestId]
 * @property {string} createdAt
 *
 * @typedef {object} BloodRequestView
 * @property {string} id
 * @property {string} reference
 * @property {string} hospitalId
 * @property {{id: string, name: string, locationLabel?: string|null}|null} [hospital]
 * @property {string} patientNeedId
 * @property {string} bloodGroup
 * @property {string} component
 * @property {number} unitsRequired
 * @property {number} unitsCoordinated
 * @property {"ROUTINE"|"URGENT"|"EMERGENCY"} urgency
 * @property {string} status
 * @property {string} requiredBy
 * @property {string|null} [coordinationNote]
 * @property {string|null} [backupReason]
 * @property {number} outreachTier
 * @property {string} openedAt
 * @property {string|null} [closedAt]
 * @property {{accepted: number, selected: number, standby: number, withdrawn: number, total: number}} responders
 * @property {Array<object>} [events]
 * @property {Array<object>} [responses]
 * @property {object} [outreach]
 *
 * @typedef {object} ConversationSummary
 * @property {string} id
 * @property {string} bloodRequestId
 * @property {string|null} requestReference
 * @property {string|null} requestStatus
 * @property {string} counterpartyRole
 * @property {string} counterpartyName
 * @property {string} counterpartyInitials
 * @property {"OPEN"|"CLOSED"|"ARCHIVED"} status
 * @property {number} unreadCount
 * @property {string|null} lastMessagePreview
 * @property {string|null} lastMessageAt
 * @property {string} createdAt
 *
 * @typedef {object} MessageView
 * @property {string} id
 * @property {string} senderId
 * @property {boolean} mine
 * @property {string} content
 * @property {string} createdAt
 * @property {string|null} [readAt]
 *
 * @typedef {object} ModuleSummary
 * @property {string} key
 * @property {"D1"|"D2"|"D3"|"D4"} owner
 * @property {string} domain
 * @property {string} prefix
 * @property {string} description
 * @property {"COMPLETE"|"IMPLEMENTED"|"SCAFFOLD"} status
 * @property {string[]} dependsOn
 */

/** Blood groups, in the order the platform displays them. */
export const BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"];

/** Blood components (spec §8). */
export const BLOOD_COMPONENTS = [
  "WHOLE_BLOOD",
  "PRBC",
  "PLASMA",
  "PLATELETS",
  "CRYOPRECIPITATE",
];

/** Urgency levels. */
export const URGENCIES = ["ROUTINE", "URGENT", "EMERGENCY"];

/** PatientNeed lifecycle (D2 submission + D3 review). */
export const PATIENT_NEED_STATUSES = [
  "PENDING_HOSPITAL_REVIEW",
  "APPROVED",
  "REJECTED",
  "CONVERTED",
  "CANCELLED",
];

/** BloodRequest lifecycle (spec §9 — the transition table lives in the API). */
export const BLOOD_REQUEST_STATUSES = [
  "OPEN",
  "RESPONSES_RECEIVED",
  "COVERED",
  "COORDINATING",
  "FULFILLMENT_PENDING",
  "FULFILLMENT_CONFIRMED",
  "FULFILLED",
  "BACKUP_REQUIRED",
  "CANCELLED",
  "EXPIRED",
];

/** DonorResponse lifecycle. */
export const DONOR_RESPONSE_STATUSES = [
  "ACCEPTED",
  "SELECTED",
  "STANDBY",
  "WITHDRAWN",
  "DECLINED",
  "RELEASED",
];

/** Organization verification states. */
export const ORG_VERIFICATION_STATUSES = ["PENDING", "VERIFIED", "SUSPENDED"];

/** Statuses that still accept fresh donor responses. */
export const REQUEST_ACCEPTS_RESPONSES = [
  "OPEN",
  "RESPONSES_RECEIVED",
  "BACKUP_REQUIRED",
  "COORDINATING",
];

/** Statuses where the coordination decision (select donor / fulfil) is live. */
export const REQUEST_COORDINATION_STATUSES = [
  "RESPONSES_RECEIVED",
  "COVERED",
  "COORDINATING",
  "FULFILLMENT_PENDING",
  "BACKUP_REQUIRED",
];

/** No request may move again once it reaches one of these. */
export const REQUEST_TERMINAL_STATUSES = ["FULFILLED", "CANCELLED", "EXPIRED"];

/**
 * The client mirror of the API's transition table (spec §9). The API still
 * enforces it — this only decides which buttons to offer, and
 * `tests/test_web_contract_parity.py` fails the build if the two drift apart.
 */
export const REQUEST_TRANSITIONS = {
  OPEN: ["RESPONSES_RECEIVED", "COVERED", "CANCELLED", "EXPIRED"],
  RESPONSES_RECEIVED: ["COVERED", "BACKUP_REQUIRED", "CANCELLED", "EXPIRED"],
  COVERED: ["COORDINATING", "BACKUP_REQUIRED", "CANCELLED"],
  COORDINATING: ["FULFILLMENT_PENDING", "BACKUP_REQUIRED", "CANCELLED"],
  BACKUP_REQUIRED: ["RESPONSES_RECEIVED", "COVERED", "COORDINATING", "CANCELLED"],
  FULFILLMENT_PENDING: ["FULFILLMENT_CONFIRMED", "COORDINATING", "BACKUP_REQUIRED"],
  FULFILLMENT_CONFIRMED: ["FULFILLED"],
  FULFILLED: [],
  CANCELLED: [],
  EXPIRED: [],
};

/** Component labels for UI copy. */
export const COMPONENT_LABELS = {
  WHOLE_BLOOD: "Whole blood",
  PRBC: "Packed red cells",
  PLASMA: "Plasma",
  PLATELETS: "Platelets",
  CRYOPRECIPITATE: "Cryoprecipitate",
};

/** Urgency labels for UI copy. */
export const URGENCY_LABELS = {
  ROUTINE: "Routine",
  URGENT: "Urgent",
  EMERGENCY: "Emergency",
};
