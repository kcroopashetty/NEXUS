"""Synthetic data seed script for NEXUS demonstration."""

import io
import os
import sys
from datetime import datetime, timezone
import uuid

# Ensure backend root is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.models import Tenant, User, TenantMembership, Document, DocumentVersion, AuditEvent
from app.services.storage.local import storage_service
from app.services.ingestion.pipeline import ingestion_pipeline
from app.services.change_intelligence.diff import compute_version_diff


def seed_database():
    """Populate database with synthetic tenants, users, memberships, and documents."""
    print("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()

    try:
        # Check if already seeded
        existing_admin = session.query(User).filter(User.email == "root@nexus.corp").first()
        if existing_admin:
            print("Database already contains seed data. Skipping.")
            return

        print("Seeding synthetic users and tenants...")
        common_password = hash_password("NexusSecretPass123!")

        # 1. Global Platform Admin
        platform_admin = User(
            email="root@nexus.corp",
            display_name="Global Platform Admin",
            password_hash=common_password,
            platform_role="PLATFORM_ADMIN",
            status="ACTIVE",
        )
        session.add(platform_admin)

        # 2. Synthetic Tenants
        tenant_configs = [
            {
                "slug": "tenant-a",
                "name": "Alpha Financial Services",
                "admin_email": "admin@a.corp",
                "admin_name": "Alice Admin (Alpha)",
                "emp_email": "emp@a.corp",
                "emp_name": "Edward Employee (Alpha)",
            },
            {
                "slug": "tenant-b",
                "name": "Beta Healthcare Systems",
                "admin_email": "admin@b.corp",
                "admin_name": "Bob Admin (Beta)",
                "emp_email": "emp@b.corp",
                "emp_name": "Emma Employee (Beta)",
            },
            {
                "slug": "tenant-c",
                "name": "Gamma Manufacturing Group",
                "admin_email": "admin@c.corp",
                "admin_name": "Carol Admin (Gamma)",
                "emp_email": "emp@c.corp",
                "emp_name": "Eric Employee (Gamma)",
            },
        ]

        tenants_map = {}

        for config in tenant_configs:
            tenant = Tenant(slug=config["slug"], name=config["name"], status="ACTIVE")
            session.add(tenant)
            session.flush()
            tenants_map[config["slug"]] = tenant

            # Client Admin
            c_admin = User(
                email=config["admin_email"],
                display_name=config["admin_name"],
                password_hash=common_password,
                platform_role="USER",
                status="ACTIVE",
            )
            # Employee
            c_emp = User(
                email=config["emp_email"],
                display_name=config["emp_name"],
                password_hash=common_password,
                platform_role="USER",
                status="ACTIVE",
            )
            session.add_all([c_admin, c_emp])
            session.flush()

            # Assign Memberships with Permission Change Guard timestamp
            now = datetime.now(timezone.utc)
            m_admin = TenantMembership(
                tenant_id=tenant.id,
                user_id=c_admin.id,
                role="CLIENT_ADMIN",
                status="ACTIVE",
                last_permission_change_at=now,
            )
            m_emp = TenantMembership(
                tenant_id=tenant.id,
                user_id=c_emp.id,
                role="EMPLOYEE",
                status="ACTIVE",
                last_permission_change_at=now,
            )
            session.add_all([m_admin, m_emp])

            audit = AuditEvent(
                tenant_id=tenant.id,
                action="TENANT_PROVISION_SEED",
                outcome="SUCCESS",
                metadata_json={"slug": tenant.slug},
            )
            session.add(audit)

        session.commit()

        print("Seeding documents and Knowledge Change Intelligence reports...")
        tenant_a = tenants_map["tenant-a"]
        admin_a = session.query(User).filter(User.email == "admin@a.corp").first()

        # Seed Document 1 in Tenant A: Customer Complaints Policy
        doc1 = Document(
            tenant_id=tenant_a.id,
            title="Customer Complaint Handling SOP",
            category="Customer Operations",
            authority_level="OFFICIAL_POLICY",
            created_by=admin_a.id,
        )
        session.add(doc1)
        session.flush()

        # Version 1 of Doc 1 (SUPERSEDED)
        v1_text = (
            b"Clause 4.1: Customer complaints shall be resolved within 48 hours.\n"
            b"Clause 4.2: Director signoff is required for financial escalations."
        )
        ver1_id = uuid.uuid4()
        q_key1 = storage_service.save_quarantine(io.BytesIO(v1_text), str(uuid.uuid4()))
        v1_key = storage_service.promote_from_quarantine(
            quarantine_key=q_key1,
            tenant_id=str(tenant_a.id),
            document_id=str(doc1.id),
            version_id=str(ver1_id),
        )
        ver1 = DocumentVersion(
            id=ver1_id,
            tenant_id=tenant_a.id,
            document_id=doc1.id,
            version_number=1,
            status="SUPERSEDED",
            original_filename="complaints_v1.txt",
            mime_type="text/plain",
            storage_key=v1_key,
            file_size_bytes=len(v1_text),
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            uploaded_by=admin_a.id,
        )
        session.add(ver1)
        session.flush()
        ingestion_pipeline.process_version(version_id=ver1.id, db=session)
        ver1.status = "SUPERSEDED"

        # Version 2 of Doc 1 (ACTIVE)
        v2_text = (
            b"Clause 4.1: Customer complaints shall be resolved within 24 hours.\n"
            b"Clause 4.2: Director signoff is required for financial escalations.\n"
            b"Clause 4.3: Expedited resolution fee is $50 USD."
        )
        ver2_id = uuid.uuid4()
        q_key2 = storage_service.save_quarantine(io.BytesIO(v2_text), str(uuid.uuid4()))
        v2_key = storage_service.promote_from_quarantine(
            quarantine_key=q_key2,
            tenant_id=str(tenant_a.id),
            document_id=str(doc1.id),
            version_id=str(ver2_id),
        )
        ver2 = DocumentVersion(
            id=ver2_id,
            tenant_id=tenant_a.id,
            document_id=doc1.id,
            version_number=2,
            status="ACTIVE",
            original_filename="complaints_v2.txt",
            mime_type="text/plain",
            storage_key=v2_key,
            file_size_bytes=len(v2_text),
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b856",
            uploaded_by=admin_a.id,
        )
        session.add(ver2)
        session.flush()
        ingestion_pipeline.process_version(version_id=ver2.id, db=session)
        ver2.status = "ACTIVE"
        session.commit()

        # Compute Diff between v1 and v2
        compute_version_diff(
            tenant_id=tenant_a.id,
            to_version_id=ver2.id,
            user_id=admin_a.id,
            db_session=session,
            from_version_id=ver1.id,
        )

        # Seed Document 2 in Tenant B for Tenant Isolation proof
        tenant_b = tenants_map["tenant-b"]
        admin_b = session.query(User).filter(User.email == "admin@b.corp").first()
        doc_b = Document(
            tenant_id=tenant_b.id,
            title="HIPAA Medical Record Retention Guidelines",
            category="Compliance",
            authority_level="OFFICIAL_POLICY",
            created_by=admin_b.id,
        )
        session.add(doc_b)
        session.flush()

        b_text = b"Clause 1.1: Patient health records shall be retained for 7 years under federal healthcare standards."
        ver_b_id = uuid.uuid4()
        q_key_b = storage_service.save_quarantine(io.BytesIO(b_text), str(uuid.uuid4()))
        b_key = storage_service.promote_from_quarantine(
            quarantine_key=q_key_b,
            tenant_id=str(tenant_b.id),
            document_id=str(doc_b.id),
            version_id=str(ver_b_id),
        )
        ver_b = DocumentVersion(
            id=ver_b_id,
            tenant_id=tenant_b.id,
            document_id=doc_b.id,
            version_number=1,
            status="ACTIVE",
            original_filename="hipaa_retention.txt",
            mime_type="text/plain",
            storage_key=b_key,
            file_size_bytes=len(b_text),
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b857",
            uploaded_by=admin_b.id,
        )
        session.add(ver_b)
        session.flush()
        ingestion_pipeline.process_version(version_id=ver_b.id, db=session)
        ver_b.status = "ACTIVE"
        session.commit()

        print("Database seeded successfully with 3 tenants, documents, and change reports.")

    finally:
        session.close()


if __name__ == "__main__":
    seed_database()
