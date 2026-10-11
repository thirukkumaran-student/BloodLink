import { api } from "./client";
const authApi = {
  register: (payload) => api.post("/auth/register", payload),
  login: (email, password) => api.post("/auth/login", { email, password }),
  logout: (refreshToken) => api.post("/auth/logout", { refreshToken }),
  me: () => api.get("/auth/me"),
  changePassword: (currentPassword, newPassword) => api.post("/auth/change-password", { currentPassword, newPassword })
};
const platformApi = {
  health: () => api.get("/platform/health"),
  modules: () => api.get("/platform/modules")
};
const patientNeedApi = {
  create: (payload) => api.post("/patient-needs", payload),
  listMine: () => api.get("/patient-needs"),
  get: (id) => api.get(`/patient-needs/${id}`),
  cancel: (id) => api.post(`/patient-needs/${id}/cancel`),
  discoverHospitals: (q) => api.get("/patient-needs/reference/hospitals", { q })
};
const hospitalApi = {
  reviewQueue: (status) => api.get("/hospital/patient-needs", { status }),
  reviewNeed: (id, decision, reason) => api.post(`/hospital/patient-needs/${id}/review`, { decision, reason }),
  requests: (status) => api.get("/blood-requests", { status }),
  createRequest: (payload) => api.post("/blood-requests", payload),
  requestDetail: (id) => api.get(`/blood-requests/${id}`),
  outreach: (id) => api.get(`/blood-requests/${id}/outreach`),
  approvedNeeds: () => api.get("/hospital/patient-needs", { status: "APPROVED" }),
  selectDonor: (requestId, donorResponseId, alsoStandby = []) => api.post(`/blood-requests/${requestId}/select-donor`, {
    donorResponseId,
    alsoMoveToStandby: alsoStandby
  }),
  confirmFulfillment: (requestId, payload) => api.post(`/blood-requests/${requestId}/confirm-fulfillment`, payload ?? {}),
  transition: (requestId, toStatus, reason) => api.post(`/blood-requests/${requestId}/transition`, { toStatus, reason })
};
const donorApi = {
  profile: () => api.get("/donor/profile"),
  saveProfile: (payload) => api.put("/donor/profile", payload),
  setAvailability: (payload) => api.patch("/donor/availability", payload),
  matchedRequests: () => api.get("/donor/matched-requests"),
  responses: () => api.get("/donor/responses"),
  accept: (requestId, payload) => api.post(`/donor/blood-requests/${requestId}/accept`, payload),
  withdraw: (responseId, reason) => api.post(`/donor/responses/${responseId}/withdraw`, { reason }),
  donations: () => api.get("/donations"),
  subscriptions: () => api.get("/donor/subscriptions"),
  nearbyHospitals: () => api.get(
    "/donor/nearby-hospitals"
  ),
  subscribe: (hospitalId, bloodGroups = []) => api.post("/donor/subscriptions", { hospitalId, bloodGroups }),
  unsubscribe: (subscriptionId) => api.delete(`/donor/subscriptions/${subscriptionId}`)
};
const notificationApi = {
  list: (unreadOnly = false) => api.get("/notifications", { unreadOnly }),
  markRead: (notificationIds) => api.post("/notifications/read", { notificationIds }),
  registerSubscription: (payload) => api.post("/notifications/subscriptions", payload)
};
const conversationApi = {
  list: () => api.get("/conversations"),
  read: (id) => api.get(`/conversations/${id}`),
  send: (id, content) => api.post(`/conversations/${id}/messages`, { content }),
  markRead: (id) => api.post(`/conversations/${id}/read`)
};
const bloodCentreApi = {
  submitResponse: (payload) => api.post("/blood-centres/responses", payload),
  myResponses: () => api.get("/blood-centres/responses"),
  nearbyRequests: (radiusKm = 25, params = {}) => api.get("/blood-requests/nearby", {
    radiusKm,
    ...params
  })
};
const adminApi = {
  organizations: (verificationStatus) => api.get(
    "/admin/organizations",
    { verificationStatus }
  ),
  verify: (id) => api.post(`/admin/organizations/${id}/verify`),
  suspend: (id) => api.post(`/admin/organizations/${id}/suspend`),
  users: (role) => api.get(
    "/admin/users",
    { role }
  ),
  deactivate: (id) => api.post(`/admin/users/${id}/deactivate`),
  audit: () => api.get(
    "/admin/audit"
  ),
  alerts: () => api.get("/admin/requests/alerts")
};
const organizationApi = {
  directory: (q, orgType) => api.get("/organizations", { q, orgType }),
  mine: () => api.get("/organizations/mine")
};
export {
  adminApi,
  authApi,
  bloodCentreApi,
  conversationApi,
  donorApi,
  hospitalApi,
  notificationApi,
  organizationApi,
  patientNeedApi,
  platformApi
};
