"""Continuous Security Assurance & Red-Team Sentinel API endpoints."""

import logging
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.errors import ResourceNotFoundError, InsufficientRoleError
from app.db.session import get_db
from app.models import User, SecurityTestRun, SecurityTestResult
from app.services.authorization.context import get_current_user
from app.services.security.sentinel import SentinelRunner

logger = logging.getLogger("nexus.security_api")

router = APIRouter(prefix="/api/v1/security", tags=["Security & Red-Team Sentinel"])


@router.post("/sentinel/run", status_code=status.HTTP_201_CREATED)
def trigger_sentinel_run(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Trigger the automated Red-Team Sentinel security test suite.
    Executes adversarial tests: route tampering, cross-tenant leaks, prompt injection, role escalation.
    Available to Platform Administrators and Client Administrators.
    """
    # Verify user has administrative privilege
    if current_user.platform_role != "PLATFORM_ADMIN":
        # Check if user is a client admin in at least one workspace
        from app.models import TenantMembership
        is_client_admin = (
            db.query(TenantMembership)
            .filter(TenantMembership.user_id == current_user.id, TenantMembership.role == "CLIENT_ADMIN")
            .first()
        )
        if not is_client_admin:
            raise InsufficientRoleError("Only administrators may trigger Red-Team Sentinel security tests.")

    runner = SentinelRunner(db=db)
    run = runner.run_suite(started_by_user_id=current_user.id)

    return {
        "id": str(run.id),
        "run_id": str(run.id),
        "suite_name": run.suite_name,
        "status": run.status,
        "summary": run.summary_json,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("/test-runs")
def list_security_test_runs(
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List historical Red-Team Sentinel test execution summaries.
    Redacts raw secret keys and internal payloads; surfaces aggregate pass/fail stats.
    """
    runs = (
        db.query(SecurityTestRun)
        .order_by(SecurityTestRun.started_at.desc())
        .offset(offset)
        .limit(min(limit, 50))
        .all()
    )

    return [
        {
            "id": str(r.id),
            "suite_name": r.suite_name,
            "status": r.status,
            "summary": r.summary_json,
            "started_at": r.started_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]


@router.get("/test-runs/{run_id}")
def get_security_test_run_details(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve detailed test case breakdown for a security test run."""
    run = db.query(SecurityTestRun).filter(SecurityTestRun.id == run_id).first()
    if not run:
        raise ResourceNotFoundError("Security test run not found.")

    results = (
        db.query(SecurityTestResult)
        .filter(SecurityTestResult.run_id == run_id)
        .order_by(SecurityTestResult.created_at.asc())
        .all()
    )

    return {
        "id": str(run.id),
        "run_id": str(run.id),
        "suite_name": run.suite_name,
        "status": run.status,
        "summary": run.summary_json,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "results": [
            {
                "id": str(res.id),
                "test_key": res.test_key,
                "title": res.title,
                "expected_result": res.expected_result,
                "actual_result": res.actual_result,
                "passed": res.passed,
                "severity": res.severity,
                "evidence": res.evidence_redacted,
            }
            for res in results
        ],
    }

