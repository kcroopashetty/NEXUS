"""Test configuration and shared fixtures for Pytest."""

import os
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

# Ensure backend root is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

# Test SQLite in-memory database with StaticPool so all connections share the same memory DB
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Configure environment variables for testing."""
    settings.NEXUS_ENV = "testing"
    settings.NEXUS_STORAGE_DIR = "./data/test_storage"
    os.makedirs(settings.NEXUS_STORAGE_DIR, exist_ok=True)
    yield
    # Clean up test storage if needed
    if os.path.exists("./data/test_storage"):
        import shutil
        shutil.rmtree("./data/test_storage", ignore_errors=True)


@pytest.fixture(scope="function")
def db_session():
    """Create fresh database tables for each test and yield a clean session."""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient with overridden database dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
