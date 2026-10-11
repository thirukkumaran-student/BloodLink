function can(user, capability) {
  return Boolean(user?.capabilities?.includes(capability));
}
const ROLE_LABELS = {
  INDIVIDUAL: "Individual",
  HOSPITAL: "Hospital",
  BLOOD_CENTRE: "Blood centre",
  ADMIN: "Administrator"
};
const BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"];
const COMPONENT_LABELS = {
  WHOLE_BLOOD: "Whole blood",
  PRBC: "Packed red cells (PRBC)",
  PLASMA: "Plasma",
  PLATELETS: "Platelets",
  CRYOPRECIPITATE: "Cryoprecipitate"
};
const URGENCY_LABELS = {
  ROUTINE: "Routine",
  URGENT: "Urgent",
  EMERGENCY: "Emergency"
};
const CLINICAL_DISCLAIMER = "BloodLink coordinates. Screening, testing, crossmatching, collection and issue always remain with the hospital or blood centre.";
export {
  BLOOD_GROUPS,
  CLINICAL_DISCLAIMER,
  COMPONENT_LABELS,
  ROLE_LABELS,
  URGENCY_LABELS,
  can
};
