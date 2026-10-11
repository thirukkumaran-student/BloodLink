import { useEffect, useState } from "react";
import { Banner, Button, Card, FormField, Input, PageHeader, Select, useToast } from "@bloodlink/ui";
import { donorApi } from "../../api/endpoints";
import { BLOOD_GROUPS } from "../../lib/capabilities";
import { useDonorProfile, queryKeys } from "../../app/hooks";
import { useQueryClient } from "@tanstack/react-query";
function DonorProfilePage({ user }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const profile = useDonorProfile();
  const [form, setForm] = useState({
    bloodGroup: "O+",
    city: "Chennai",
    district: "Chennai",
    state: "Tamil Nadu",
    pincode: "",
    latitude: "",
    longitude: "",
    isAvailable: true,
    acceptsNotifications: true,
    notifyEmergencyOnly: false,
    dateOfBirth: "",
    weightKg: ""
  });
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState({});
  useEffect(() => {
    if (!profile.data) return;
    setForm((current) => ({
      ...current,
      bloodGroup: profile.data.bloodGroup,
      city: profile.data.city ?? "",
      district: profile.data.district ?? "",
      state: profile.data.state ?? "",
      isAvailable: profile.data.isAvailable,
      acceptsNotifications: profile.data.acceptsNotifications,
      notifyEmergencyOnly: profile.data.notifyEmergencyOnly
    }));
  }, [profile.data]);
  function update(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }
  function useMyLocation() {
    if (!navigator.geolocation) {
      toast.error("Location unavailable", "This browser does not expose the geolocation API.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        update("latitude", position.coords.latitude.toFixed(5));
        update("longitude", position.coords.longitude.toFixed(5));
        toast.success("Location captured", "Stored as internal matching data \u2014 never shown to other users.");
      },
      () => toast.error("Location denied", "Enter coordinates manually or pick your locality instead."),
      { enableHighAccuracy: false, timeout: 8e3 }
    );
  }
  async function save() {
    setBusy(true);
    setErrors({});
    try {
      await donorApi.saveProfile({
        bloodGroup: form.bloodGroup,
        city: form.city || void 0,
        district: form.district || void 0,
        state: form.state || void 0,
        pincode: form.pincode || void 0,
        latitude: form.latitude ? Number(form.latitude) : void 0,
        longitude: form.longitude ? Number(form.longitude) : void 0,
        isAvailable: form.isAvailable,
        acceptsNotifications: form.acceptsNotifications,
        notifyEmergencyOnly: form.notifyEmergencyOnly,
        dateOfBirth: form.dateOfBirth || void 0,
        weightKg: form.weightKg ? Number(form.weightKg) : void 0
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.donorProfile });
      await queryClient.invalidateQueries({ queryKey: queryKeys.donorMatches });
      toast.success("Donor profile saved", "Matching uses your group, availability and distance.");
    } catch (caught) {
      const error = caught;
      setErrors(error.fieldErrors);
      toast.error("Could not save", error.message);
    } finally {
      setBusy(false);
    }
  }
  return <><PageHeader
    title="Donor profile"
    subtitle="This is what BloodLink matches on. Medical eligibility is decided at the facility, never here."
  /><div className="bl-grid" style={{ gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)" }}><Card title="Matching details"><div className="bl-stack"><div className="bl-grid" style={{ gridTemplateColumns: "1fr 1fr" }}><FormField label="Blood group" htmlFor="bloodGroup" required error={errors.bloodGroup}><Select
    id="bloodGroup"
    value={form.bloodGroup}
    onChange={(event) => update("bloodGroup", event.target.value)}
    options={BLOOD_GROUPS.map((group) => ({ value: group, label: group }))}
  /></FormField><FormField label="Date of birth" htmlFor="dateOfBirth" hint="Used only for donor suitability prompts"><Input
    id="dateOfBirth"
    type="date"
    value={form.dateOfBirth}
    onChange={(event) => update("dateOfBirth", event.target.value)}
  /></FormField><FormField label="City" htmlFor="city"><Input id="city" value={form.city} onChange={(event) => update("city", event.target.value)} /></FormField><FormField label="District" htmlFor="district" hint="Not a hard matching boundary"><Input id="district" value={form.district} onChange={(event) => update("district", event.target.value)} /></FormField></div><Card flat title="Location" subtitle="Used for distance-first ranking only."><div className="bl-stack-sm"><div className="bl-grid" style={{ gridTemplateColumns: "1fr 1fr" }}><FormField label="Latitude" htmlFor="latitude"><Input id="latitude" value={form.latitude} onChange={(event) => update("latitude", event.target.value)} /></FormField><FormField label="Longitude" htmlFor="longitude"><Input id="longitude" value={form.longitude} onChange={(event) => update("longitude", event.target.value)} /></FormField></div><div className="bl-row"><Button variant="outline" size="sm" onClick={useMyLocation}>
                    Use my current location
                  </Button>{profile.data?.area ? <span className="bl-subtle">Stored area: {profile.data.area}</span> : null}</div><Banner tone="muted">
                  Exact coordinates never leave the matching engine. Hospitals and other donors only
                  ever see a rounded distance such as "~4 km away".
                </Banner></div></Card><div className="bl-choice"><label className="bl-choice__option"><input
    type="checkbox"
    checked={form.isAvailable}
    onChange={(event) => update("isAvailable", event.target.checked)}
  />
                Available for outreach
              </label><label className="bl-choice__option"><input
    type="checkbox"
    checked={form.acceptsNotifications}
    onChange={(event) => update("acceptsNotifications", event.target.checked)}
  />
                Send me push notifications
              </label><label className="bl-choice__option"><input
    type="checkbox"
    checked={form.notifyEmergencyOnly}
    onChange={(event) => update("notifyEmergencyOnly", event.target.checked)}
  />
                Emergency requests only
              </label></div><Button variant="primary" loading={busy} onClick={() => void save()}>
              Save donor profile
            </Button></div></Card><div className="bl-stack"><Card title="Your privacy" subtitle="What BloodLink does and does not expose."><ul className="bl-muted" style={{ paddingLeft: "var(--bl-space-5)" }}><li>Hospitals see your name, blood group and a distance band.</li><li>No other donor can see you, or your locality.</li><li>Notifications carry no patient identity and no coordinates.</li><li>Your donation history is private to you and the hospital you donated at.</li></ul></Card>{(profile.data?.totalDonations ?? 0) > 0 ? <Card title="Donation history"><div className="bl-stack-sm"><div className="bl-row-between"><span className="bl-muted">Confirmed donations</span><strong>{profile.data?.totalDonations}</strong></div><div className="bl-row-between"><span className="bl-muted">Last donation</span><span>{profile.data?.lastDonationAt ? new Date(profile.data.lastDonationAt).toLocaleDateString() : "\u2014"}</span></div><div className="bl-row-between"><span className="bl-muted">Cooldown</span><span>{profile.data?.cooldownDaysRemaining ? `${profile.data.cooldownDaysRemaining} day(s) remaining` : "Clear"}</span></div></div></Card> : null}<Card title="Donor" subtitle={user?.email}><p className="bl-muted">
              A donor profile is a capability on your account, not a separate role — you can still
              raise requests for a patient as an individual.
            </p></Card></div></div></>;
}
export {
  DonorProfilePage
};
