"""PostgreSQL Row-Level Security (RLS) Manager and Connection-Pool Context Guard."""

import logging
import uuid
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.engine import Engine
from sqlalchemy import event

logger = logging.getLogger("nexus.rls")

# Tables subject to strict PostgreSQL Row-Level Security
RLS_TABLES = [
    "documents",
    "document_versions",
    "document_chunks",
    "document_pages",
    "processing_jobs",
    "document_changes",
    "document_change_items",
    "query_events",
    "query_evidence",
    "audit_events",
    "security_events",
]


class TenantRLSManager:
    """
    Manages transaction-scoped PostgreSQL session configuration for Row-Level Security.
    
    Guarantees:
    1. Tenant context is set via `SET LOCAL app.current_tenant_id = '<uuid>'` within the current transaction.
    2. Platform administrators may explicitly enable `SET LOCAL app.bypass_rls = 'on'`.
    3. Engine-level pool listeners guarantee that checkout/checkin resets lingering session state,
       preventing cross-request tenant context leakage on pooled connections.
    4. Provides transparent fallback/mock tracking when executing under SQLite for unit tests.
    """

    @classmethod
    def set_tenant_context(cls, db: Session, tenant_id: uuid.UUID) -> None:
        """
        Configure the transaction-local tenant context for RLS enforcement.
        Uses SET LOCAL so settings revert automatically at transaction commit/rollback.
        """
        bind = db.get_bind()
        if bind and bind.dialect.name == "postgresql":
            try:
                db.execute(
                    text("SET LOCAL app.current_tenant_id = :tenant_id"),
                    {"tenant_id": str(tenant_id)},
                )
                db.execute(text("SET LOCAL app.bypass_rls = 'off'"))
            except Exception as exc:
                logger.error("Failed to set PostgreSQL RLS tenant context: %s", exc)
                raise
        else:
            # SQLite / Test dialect tracking in session info
            db.info["current_tenant_id"] = str(tenant_id)
            db.info["bypass_rls"] = False

    @classmethod
    def set_bypass_rls(cls, db: Session) -> None:
        """
        Enable platform administrator RLS bypass for verified global admin operations.
        """
        bind = db.get_bind()
        if bind and bind.dialect.name == "postgresql":
            try:
                db.execute(text("SET LOCAL app.bypass_rls = 'on'"))
            except Exception as exc:
                logger.error("Failed to set PostgreSQL RLS bypass: %s", exc)
                raise
        else:
            db.info["bypass_rls"] = True

    @classmethod
    def reset_tenant_context(cls, db: Session) -> None:
        """Explicitly reset tenant RLS variables in the active session."""
        bind = db.get_bind()
        if bind and bind.dialect.name == "postgresql":
            try:
                db.execute(text("RESET app.current_tenant_id;"))
                db.execute(text("RESET app.bypass_rls;"))
            except Exception:
                pass
        else:
            db.info.pop("current_tenant_id", None)
            db.info.pop("bypass_rls", None)

    @classmethod
    def generate_rls_sql(cls, app_role: str = "nexus_app_user") -> str:
        """
        Generate production DDL script to enable and force RLS on all tenant-sensitive tables.
        Applies FORCE ROW LEVEL SECURITY to prevent accidental bypass by table owners.
        """
        import re
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", app_role):
            raise ValueError(f"Invalid SQL role identifier: {app_role}")

        statements = [
            "-- =================================================================",
            "-- NEXUS PostgreSQL Row-Level Security (RLS) Enforcement Script",
            "-- =================================================================",
            f"DO $$ BEGIN",
            f"  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{app_role}') THEN",  # nosec B608
            f"    CREATE ROLE {app_role} WITH NOLOGIN NOBYPASSRLS;",
            f"  END IF;",
            f"END $$;\n",
        ]

        for table in RLS_TABLES:
            statements.extend([
                f"-- Enable & Force RLS on {table}",
                f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;",
                f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;",
                f"DROP POLICY IF EXISTS tenant_isolation_{table}_policy ON {table};",
                f"CREATE POLICY tenant_isolation_{table}_policy ON {table}",
                f"  FOR ALL",
                f"  TO PUBLIC",
                f"  USING (",
                f"    current_setting('app.bypass_rls', true) = 'on'",
                f"    OR tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid",
                f"  )",
                f"  WITH CHECK (",
                f"    current_setting('app.bypass_rls', true) = 'on'",
                f"    OR tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid",
                f"  );\n",
            ])

        return "\n".join(statements)


def register_rls_pool_listeners(engine: Engine) -> None:
    """
    Register connection pool lifecycle listeners on the SQLAlchemy engine.
    Ensures that connections checked out from or returned to the connection pool
    are strictly scrubbed of any residual session settings (app.current_tenant_id).
    """

    @event.listens_for(engine, "checkin")
    def _on_connection_checkin(dbapi_connection, connection_record):
        if engine.dialect.name == "postgresql":
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("RESET app.current_tenant_id; RESET app.bypass_rls;")
            except Exception:
                pass
            finally:
                cursor.close()

    @event.listens_for(engine, "checkout")
    def _on_connection_checkout(dbapi_connection, connection_record, connection_proxy):
        if engine.dialect.name == "postgresql":
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("RESET app.current_tenant_id; RESET app.bypass_rls;")
            except Exception:
                pass
            finally:
                cursor.close()

