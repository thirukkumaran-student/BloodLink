"""Development seed data (owner: D1).

Creates a small, coherent Chennai-area dataset so every role can sign in and see
something real. It is **idempotent** and refuses to run in production.

Seeded accounts (password for every demo account: ``Bloodlink#2026``)::

    admin@bloodlink.dev        ADMIN
    apollo.staff@bloodlink.dev HOSPITAL   (Apollo General — VERIFIED)
    mhc.staff@bloodlink.dev    HOSPITAL   (Meridian Health City — VERIFIED)
    pend.staff@bloodlink.dev   HOSPITAL   (Sunrise Care Hospital — PENDING)
    redcross.staff@bloodlink.dev BLOOD_CENTRE (Red Cross Blood Centre — VERIFIED)
    priya@bloodlink.dev        INDIVIDUAL + donor profile (O-)
    arjun@bloodlink.dev        INDIVIDUAL + donor profile (A+)
    meera@bloodlink.dev        INDIVIDUAL (A-)

Seeded flow state (so the coordination story is visible immediately):
  * one PatientNeed awaiting Meridian's review
  * one PatientNeed already converted into an OPEN BloodRequest with outreach
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from bloodlink_api.core.clock import utcnow
from bloodlink_api.core.security import hash_password
from bloodlink_api.db.models.blood_requests import BloodRequest, BloodRequestEvent, DonorOutreach
from bloodlink_api.db.models.donors import DonorProfile, HospitalSubscription
from bloodlink_api.db.models.identity import Organization, OrganizationMembership, User
from bloodlink_api.db.models.needs import PatientNeed
from bloodlink_api.db.session import create_all, session_scope
from bloodlink_api.modules.notifications import service as notification_service
from bloodlink_config.logging import get_logger
from bloodlink_contracts.enums import (
    BloodComponent,
    BloodGroup,
    BloodRequestStatus,
    DonorStandbyStatus,
    NotificationType,
    OrgType,
    OrgVerificationStatus,
    PatientNeedStatus,
    Platform,
    Role,
    Urgency,
)

logger = get_logger("bloodlink.seed")

DEMO_PASSWORD = "Bloodlink#2026"


def _user(db: Session, email: str, *, full_name: str, role: Role, phone: str, organization_id=None, verified=True) -> User:
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        return existing
    user = User(
        email=email,
        password_hash=hash_password(DEMO_PASSWORD),
        full_name=full_name,
        phone=phone,
        role=role,
        organization_id=organization_id,
        is_active=True,
        email_verified=verified,
    )
    db.add(user)
    db.flush()
    return user


def _organization(
    db: Session,
    *,
    name: str,
    org_type: OrgType,
    verification: OrgVerificationStatus,
    city: str,
    district: str,
    latitude: float,
    longitude: float,
    address: str,
    contact_phone: str,
) -> Organization:
    existing = db.execute(select(Organization).where(Organization.name == name)).scalar_one_or_none()
    if existing:
        return existing
    organization = Organization(
        name=name,
        org_type=org_type,
        registration_number=f"TN-{org_type.value[:3]}-{abs(hash(name)) % 90000 + 10000}",
        contact_email=f"contact@{name.lower().replace(' ', '')[:18]}.org",
        contact_phone=contact_phone,
        address=address,
        city=city,
        district=district,
        state="Tamil Nadu",
        pincode="600028",
        latitude=latitude,
        longitude=longitude,
        verification_status=verification,
        verified_at=utcnow() if verification is OrgVerificationStatus.VERIFIED else None,
    )
    db.add(organization)
    db.flush()
    return organization


def _membership(db: Session, user: User, organization: Organization, title: str) -> None:
    existing = db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if existing:
        return
    db.add(
        OrganizationMembership(
            user_id=user.id, organization_id=organization.id, title=title, is_primary=True
        )
    )


def _reference() -> str:
    return f"BL-{utcnow():%y%m%d}-{abs(hash(utcnow().isoformat())) % 9000 + 1000}"


def seed_demo_data() -> bool:
    """Seed the demo dataset. Returns True when data was created this call."""
    from bloodlink_api.core.settings import get_settings

    if get_settings().is_production:
        logger.warning("seed.skipped reason=production")
        return False

    with session_scope() as db:
        existing = db.execute(select(User).where(User.email == "admin@bloodlink.dev")).scalar_one_or_none()
        if existing is not None:
            return False

        create_all()  # safety for callers that seed outside the app lifespan

        # ---- organizations ------------------------------------------------
        apollo = _organization(
            db,
            name="Apollo General Hospital",
            org_type=OrgType.HOSPITAL,
            verification=OrgVerificationStatus.VERIFIED,
            city="Chennai",
            district="Chennai",
            latitude=13.0067,
            longitude=80.2570,
            address="12 Greams Road, Thousand Lights",
            contact_phone="4428200000",
        )
        meridian = _organization(
            db,
            name="Meridian Health City",
            org_type=OrgType.HOSPITAL,
            verification=OrgVerificationStatus.VERIFIED,
            city="Chennai",
            district="Chennai",
            latitude=12.9719,
            longitude=80.2207,
            address="4 Velachery Main Road, Guindy",
            contact_phone="4428100000",
        )
        sunrise = _organization(
            db,
            name="Sunrise Care Hospital",
            org_type=OrgType.HOSPITAL,
            verification=OrgVerificationStatus.PENDING,
            city="Chennai",
            district="Chennai",
            latitude=13.0827,
            longitude=80.2707,
            address="88 Poonamallee High Road",
            contact_phone="4428300000",
        )
        redcross = _organization(
            db,
            name="Red Cross Blood Centre",
            org_type=OrgType.BLOOD_CENTRE,
            verification=OrgVerificationStatus.VERIFIED,
            city="Chennai",
            district="Chennai",
            latitude=13.0700,
            longitude=80.2600,
            address="Anna Salai, Egmore",
            contact_phone="4428400000",
        )

        # ---- accounts ------------------------------------------------------
        admin = _user(db, "admin@bloodlink.dev", full_name="Ravi Iyer", role=Role.ADMIN, phone="9840000001")
        apollo_staff = _user(
            db, "apollo.staff@bloodlink.dev", full_name="Dr. Kavitha Rao", role=Role.HOSPITAL,
            phone="9840000002", organization_id=apollo.id,
        )
        meridian_staff = _user(
            db, "mhc.staff@bloodlink.dev", full_name="Dr. Sanjay Menon", role=Role.HOSPITAL,
            phone="9840000003", organization_id=meridian.id,
        )
        pending_staff = _user(
            db, "pend.staff@bloodlink.dev", full_name="Dr. Anita Sharma", role=Role.HOSPITAL,
            phone="9840000004", organization_id=sunrise.id,
        )
        centre_staff = _user(
            db, "redcross.staff@bloodlink.dev", full_name="Suresh Kumar", role=Role.BLOOD_CENTRE,
            phone="9840000005", organization_id=redcross.id,
        )
        priya = _user(db, "priya@bloodlink.dev", full_name="Priya Raman", role=Role.INDIVIDUAL, phone="9840000006")
        arjun = _user(db, "arjun@bloodlink.dev", full_name="Arjun Das", role=Role.INDIVIDUAL, phone="9840000007")
        meera = _user(db, "meera@bloodlink.dev", full_name="Meera Nair", role=Role.INDIVIDUAL, phone="9840000008")

        _membership(db, apollo_staff, apollo, "Transfusion Coordinator")
        _membership(db, meridian_staff, meridian, "Blood Bank Officer")
        _membership(db, pending_staff, sunrise, "Administrator")
        _membership(db, centre_staff, redcross, "Centre Coordinator")
        db.flush()

        # ---- donor profiles (coordinates are internal matching data) -------
        donors = [
            (priya, BloodGroup.O_NEGATIVE, 12.9784, 80.2240, "Adyar", "Chennai", date(1994, 3, 12), 58.0),
            (arjun, BloodGroup.A_POSITIVE, 13.0400, 80.2337, "Nungambakkam", "Chennai", date(1991, 7, 2), 72.0),
            (meera, BloodGroup.A_NEGATIVE, 13.0900, 80.2200, "Anna Nagar", "Chennai", date(1996, 11, 21), 54.0),
        ]
        profiles: dict[str, DonorProfile] = {}
        for user, group, lat, lon, city, district, dob, weight in donors:
            profile = db.execute(
                select(DonorProfile).where(DonorProfile.user_id == user.id)
            ).scalar_one_or_none()
            if profile is None:
                profile = DonorProfile(
                    user_id=user.id,
                    blood_group=group,
                    date_of_birth=dob,
                    weight_kg=weight,
                    city=city,
                    district=district,
                    state="Tamil Nadu",
                    pincode="600020",
                    latitude=lat,
                    longitude=lon,
                    is_available=True,
                    accepts_notifications=True,
                    acknowledged_screening_notice=True,
                    total_donations=0,
                )
                db.add(profile)
            profiles[user.id] = profile

        # A staff member is also a donor (hospital staff may donate).
        staff_profile = db.execute(
            select(DonorProfile).where(DonorProfile.user_id == apollo_staff.id)
        ).scalar_one_or_none()
        if staff_profile is None:
            staff_profile = DonorProfile(
                user_id=apollo_staff.id,
                blood_group=BloodGroup.B_POSITIVE,
                city="Chennai",
                district="Chennai",
                state="Tamil Nadu",
                latitude=13.0100,
                longitude=80.2500,
                total_donations=3,
                last_donation_at=utcnow() - timedelta(days=140),
            )
            db.add(staff_profile)
        db.flush()

        # ---- PatientNeed pending review (D2 -> D3 gate) --------------------
        pending_need = PatientNeed(
            submitted_by_user_id=meera.id,
            hospital_id=meridian.id,
            blood_group=BloodGroup.O_POSITIVE,
            component=BloodComponent.PRBC,
            units=2,
            urgency=Urgency.URGENT,
            required_by=utcnow() + timedelta(hours=18),
            additional_notes="Coordination contact available on the ward desk between 8am-8pm.",
            status=PatientNeedStatus.PENDING_HOSPITAL_REVIEW,
        )
        db.add(pending_need)
        db.flush()

        # ---- Converted need + OPEN request with outreach -------------------
        converted_need = PatientNeed(
            submitted_by_user_id=priya.id,
            hospital_id=apollo.id,
            blood_group=BloodGroup.O_NEGATIVE,
            component=BloodComponent.PRBC,
            units=1,
            urgency=Urgency.EMERGENCY,
            required_by=utcnow() + timedelta(hours=6),
            additional_notes="Emergency coordination requested; hospital will confirm screening.",
            status=PatientNeedStatus.CONVERTED,
            reviewed_by_user_id=apollo_staff.id,
            reviewed_at=utcnow() - timedelta(hours=1),
        )
        db.add(converted_need)
        db.flush()

        blood_request = BloodRequest(
            reference=_reference(),
            hospital_id=apollo.id,
            patient_need_id=converted_need.id,
            blood_group=BloodGroup.O_NEGATIVE,
            component=BloodComponent.PRBC,
            units_required=1,
            units_coordinated=0,
            urgency=Urgency.EMERGENCY,
            status=BloodRequestStatus.OPEN,
            required_by=converted_need.required_by,
            coordination_note="Report to the transfusion desk; carry a photo ID.",
        )
        db.add(blood_request)
        db.flush()
        db.add(
            BloodRequestEvent(
                blood_request_id=blood_request.id,
                event_type="REQUEST_CREATED",
                to_status=BloodRequestStatus.OPEN,
                actor_user_id=apollo_staff.id,
                detail={"unitsRequired": 1, "urgency": "EMERGENCY"},
            )
        )
        db.add(
            BloodRequestEvent(
                blood_request_id=blood_request.id,
                event_type="OUTREACH_TIER_1",
                actor_user_id=apollo_staff.id,
                detail={"tier": 1},
            )
        )
        db.add(
            DonorOutreach(
                blood_request_id=blood_request.id,
                donor_profile_id=profiles[priya.id].id,
                tier=1,
                distance_km=3.4,
                compatibility_rank=1,
                standby_status=DonorStandbyStatus.NONE,
                notified_at=utcnow(),
            )
        )
        notification_service.create_notification(
            db,
            user_id=priya.id,
            notification_type=NotificationType.REQUEST_OPENED,
            data={
                "requestId": blood_request.id,
                "reference": blood_request.reference,
                "bloodGroup": "O-",
                "component": "PRBC",
                "urgency": "EMERGENCY",
                "distanceBand": "~3 km away",
                "url": f"/donor/requests/{blood_request.id}",
            },
            blood_request_id=blood_request.id,
        )

        # ---- a donor subscription ------------------------------------------
        db.add(
            HospitalSubscription(
                hospital_id=apollo.id,
                user_id=priya.id,
                donor_profile_id=profiles[priya.id].id,
                blood_groups="O-,O+",
                max_urgency=None,
                is_active=True,
            )
        )
        db.add(
            HospitalSubscription(
                hospital_id=apollo.id,
                user_id=arjun.id,
                donor_profile_id=profiles[arjun.id].id,
                blood_groups="A+",
                max_urgency=Urgency.URGENT,
                is_active=True,
            )
        )

        db.flush()
        logger.info(
            "seed.complete users=%d organizations=%d requests=%d",
            8,
            4,
            1,
        )
        return True


if __name__ == "__main__":  # pragma: no cover - manual invocation
    created = seed_demo_data()
    print("Seeded demo data." if created else "Demo data already present; nothing to do.")
