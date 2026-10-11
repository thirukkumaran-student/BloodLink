import { useState } from "react";
import { Button, Card, FormField, Input, Select, useToast } from "@bloodlink/ui";
import { session } from "../../api/client";
import { authApi } from "../../api/endpoints";
import { CLINICAL_DISCLAIMER } from "../../lib/capabilities";
const ROLE_OPTIONS = [
  { value: "INDIVIDUAL", label: "Individual \u2014 I need blood or I want to donate" },
  { value: "HOSPITAL", label: "Hospital staff" },
  { value: "BLOOD_CENTRE", label: "Blood centre staff" }
];
function RegisterPage({ onDone }) {
  const toast = useToast();
  const [role, setRole] = useState("INDIVIDUAL");
  const [form, setForm] = useState({
    fullName: "",
    email: "",
    phone: "",
    password: "",
    organizationName: "",
    city: "Chennai",
    district: "Chennai",
    latitude: "13.0827",
    longitude: "80.2707",
    registrationNumber: ""
  });
  const [error, setError] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const needsOrganization = role === "HOSPITAL" || role === "BLOOD_CENTRE";
  function update(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }
  async function submit() {
    setBusy(true);
    setError(null);
    setFieldErrors({});
    try {
      const payload = {
        email: form.email,
        password: form.password,
        fullName: form.fullName,
        phone: form.phone || void 0,
        role
      };
      if (needsOrganization) {
        payload.organization = {
          name: form.organizationName,
          orgType: role,
          registrationNumber: form.registrationNumber || void 0,
          city: form.city || void 0,
          district: form.district || void 0,
          latitude: form.latitude ? Number(form.latitude) : void 0,
          longitude: form.longitude ? Number(form.longitude) : void 0
        };
      }
      const result = await authApi.register(payload);
      session.save(result);
      toast.success(
        "Account created",
        needsOrganization ? "Your organization is pending BloodLink verification." : "Welcome to BloodLink."
      );
      onDone();
      window.location.reload();
    } catch (caught) {
      const apiError = caught;
      setError(apiError.message);
      setFieldErrors(apiError.fieldErrors);
    } finally {
      setBusy(false);
    }
  }
  return <div className="bl-auth"><aside className="bl-auth__aside"><div><span className="bl-app__logo" aria-hidden="true">
            B
          </span><h1 style={{ marginTop: "var(--bl-space-6)" }}>Create your BloodLink account</h1><p style={{ marginTop: "var(--bl-space-3)" }}>
            Individuals can raise a request for a hospital and enable a donor profile. Hospitals and
            blood centres are onboarded as organizations and verified before they can operate.
          </p></div><p className="bl-auth__disclaimer">{CLINICAL_DISCLAIMER}</p></aside><div className="bl-auth__panel"><form
    className="bl-auth__form"
    onSubmit={(event) => {
      event.preventDefault();
      void submit();
    }}
  ><div><h2>Register</h2><p className="bl-muted" style={{ marginTop: "var(--bl-space-2)" }}>
              Administrator accounts are provisioned by BloodLink operations.
            </p></div><FormField label="I am registering as" htmlFor="role" required><Select id="role" options={ROLE_OPTIONS} value={role} onChange={(event) => setRole(event.target.value)} /></FormField><FormField label="Full name" htmlFor="fullName" required error={fieldErrors.fullName}><Input id="fullName" value={form.fullName} onChange={(event) => update("fullName", event.target.value)} required /></FormField><FormField label="Email" htmlFor="email" required error={fieldErrors.email}><Input id="email" type="email" value={form.email} onChange={(event) => update("email", event.target.value)} required /></FormField><FormField label="Mobile number" htmlFor="phone" hint="10-digit Indian mobile number" error={fieldErrors.phone}><Input id="phone" value={form.phone} onChange={(event) => update("phone", event.target.value)} inputMode="numeric" /></FormField><FormField
    label="Password"
    htmlFor="password"
    required
    hint="At least 10 characters, with a letter and a number"
    error={fieldErrors.password}
  ><Input id="password" type="password" value={form.password} onChange={(event) => update("password", event.target.value)} required /></FormField>{needsOrganization ? <Card title="Organization details" subtitle="Operations unlock once administration verifies the facility."><div className="bl-stack"><FormField label="Organization name" htmlFor="organizationName" required error={fieldErrors["organization.name"]}><Input id="organizationName" value={form.organizationName} onChange={(event) => update("organizationName", event.target.value)} /></FormField><FormField label="Registration number" htmlFor="registrationNumber" hint="Facility licence / registration reference"><Input id="registrationNumber" value={form.registrationNumber} onChange={(event) => update("registrationNumber", event.target.value)} /></FormField><div className="bl-grid" style={{ gridTemplateColumns: "1fr 1fr" }}><FormField label="City" htmlFor="city"><Input id="city" value={form.city} onChange={(event) => update("city", event.target.value)} /></FormField><FormField label="District" htmlFor="district"><Input id="district" value={form.district} onChange={(event) => update("district", event.target.value)} /></FormField><FormField label="Latitude" htmlFor="latitude" hint="Used for distance-first matching"><Input id="latitude" value={form.latitude} onChange={(event) => update("latitude", event.target.value)} /></FormField><FormField label="Longitude" htmlFor="longitude" hint="Never shown to donors exactly"><Input id="longitude" value={form.longitude} onChange={(event) => update("longitude", event.target.value)} /></FormField></div></div></Card> : null}{error ? <p className="bl-error-text" role="alert">{error}</p> : null}<Button type="submit" variant="primary" block loading={busy}>
            Create account
          </Button><p className="bl-subtle">
            Already registered?{" "}<a href="/login" onClick={(event) => {
    event.preventDefault();
    window.location.assign("/login");
  }}>
              Sign in
            </a></p></form></div></div>;
}
export {
  RegisterPage
};
