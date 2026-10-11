const DEMO_MODE = (import.meta.env.VITE_DEMO_MODE ?? "true") === "true";
const DEMO_ACCOUNTS = [
  {
    label: "Priya Raman",
    email: "priya@bloodlink.dev",
    role: "INDIVIDUAL + DONOR",
    description: "Needs blood \u2022 donor profile \u2022 coordination threads"
  },
  {
    label: "Dr. Kavitha Rao",
    email: "apollo.staff@bloodlink.dev",
    role: "HOSPITAL",
    description: "Apollo General \u2014 review queue, request board"
  },
  {
    label: "Suresh Kumar",
    email: "redcross.staff@bloodlink.dev",
    role: "BLOOD CENTRE",
    description: "Red Cross Blood Centre \u2014 nearby requests, availability"
  },
  {
    label: "Ravi Iyer",
    email: "admin@bloodlink.dev",
    role: "ADMIN",
    description: "Verification, accounts, audit trail"
  }
];
const DEMO_PASSWORD = "Bloodlink#2026";
export {
  DEMO_ACCOUNTS,
  DEMO_MODE,
  DEMO_PASSWORD
};
