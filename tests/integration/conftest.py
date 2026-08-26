"""Pytest fixtures for integration tests."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from src.config import Settings
from tests.integration.test_harness import TestEnvironment


def _load_environments() -> list[TestEnvironment]:
    """Load test environments from project root .env file."""
    # Load .env from project root explicitly
    project_root = Path(__file__).parent.parent.parent
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    environments = []

    # Map UNIFI_API_KEY to cloud-ea if that's what we have
    api_key = os.getenv("UNIFI_API_KEY")
    api_type = os.getenv("UNIFI_API_TYPE", "cloud-ea")
    cloud_site_lab = os.getenv("UNIFI_CLOUD_SITE_LAB", "default")

    if api_key and api_type in ("cloud-v1", "cloud-ea"):
        environments.append(
            TestEnvironment(
                name=f"unifi-{api_type}-lab",
                api_type=api_type,
                api_key=api_key,
                site_id=cloud_site_lab,
            )
        )

    # Local lab environment
    lab_key = os.getenv("UNIFI_LAB_API_KEY") or os.getenv("UNIFI_LOCAL_API_KEY")
    if lab_key:
        environments.append(
            TestEnvironment(
                name="unifi-lab",
                api_type="local",
                api_key=lab_key,
                local_host=os.getenv("UNIFI_LAB_HOST", "10.2.0.1"),
                local_port=int(os.getenv("UNIFI_LAB_PORT", "443")),
                verify_ssl=os.getenv("UNIFI_LAB_VERIFY_SSL", "false").lower() == "true",
            )
        )

    # Local home environment
    home_key = os.getenv("UNIFI_HOME_API_KEY") or os.getenv("UNIFI_LOCAL_API_KEY")
    if home_key:
        environments.append(
            TestEnvironment(
                name="unifi-home",
                api_type="local",
                api_key=home_key,
                local_host=os.getenv("UNIFI_HOME_HOST", "192.168.2.1"),
                local_port=int(os.getenv("UNIFI_HOME_PORT", "443")),
                verify_ssl=os.getenv("UNIFI_HOME_VERIFY_SSL", "false").lower() == "true",
            )
        )

    return environments


@pytest.fixture(autouse=True, scope="function")
def isolate_env_file():
    """Override the root conftest's isolate_env_file for integration tests.

    Integration tests need real environment variables loaded from .env.
    """
    yield  # no-op: don't isolate, don't clear env vars


def pytest_collection_modifyitems(config, items):
    """Automatically add pytest.mark.asyncio to all async integration tests."""
    import asyncio

    for item in items:
        func = getattr(item, "obj", None)
        if asyncio.iscoroutinefunction(func):
            item.add_marker(pytest.mark.asyncio)


def pytest_generate_tests(metafunc):
    """Parametrize integration tests over available environments."""
    if "env" in metafunc.fixturenames:
        environments = _load_environments()
        if not environments:
            pytest.skip("No test environments configured (check .env file)")
        metafunc.parametrize(
            "env",
            environments,
            ids=[e.name for e in environments],
        )


@pytest.fixture
def settings(env: TestEnvironment) -> Settings:
    """Create Settings from the current test environment."""
    return env.to_settings()
