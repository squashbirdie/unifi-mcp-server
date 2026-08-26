#!/usr/bin/env python3
"""
Switching Integration Test Suite

Tests all switching-related MCP tools against real UniFi environments.
"""

from typing import Any

import pytest

from src.tools import switching
from src.utils import ResourceNotFoundError
from tests.integration.test_harness import TestEnvironment, TestHarness, TestSuite


@pytest.mark.integration
async def test_list_switch_stacks(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test list_switch_stacks tool."""
    try:
        result = await switching.list_switch_stacks(
            site_id=env.site_id,
            settings=settings,
        )

        # Validate response structure
        assert isinstance(result, list), "Result must be a list"

        if not result:
            return {
                "status": "SKIP",
                "message": "No switch stacks found (site may be unconfigured)",
            }

        # Validate switch stack structure
        stack = result[0]
        assert "id" in stack, "Switch stack must have id"
        assert "name" in stack, "Switch stack must have name"

        return {
            "status": "PASS",
            "message": f"Listed {len(result)} switch stacks",
            "details": {
                "count": len(result),
                "first_stack": stack.get("name", "unknown"),
            },
        }

    except AssertionError as e:
        return {"status": "FAIL", "message": str(e)}
    except Exception as e:
        return {"status": "ERROR", "message": f"{type(e).__name__}: {str(e)}"}


@pytest.mark.integration
async def test_list_switch_stacks_pagination(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test list_switch_stacks with pagination parameters."""
    try:
        all_stacks = await switching.list_switch_stacks(
            site_id=env.site_id,
            settings=settings,
        )

        if not all_stacks:
            return {"status": "SKIP", "message": "No switch stacks found for pagination test"}

        limited = await switching.list_switch_stacks(
            site_id=env.site_id,
            settings=settings,
            limit=1,
        )

        assert isinstance(limited, list), "Result must be a list"
        assert len(limited) <= 1, "Limit parameter should restrict results"

        return {
            "status": "PASS",
            "message": "Pagination working correctly",
            "details": {
                "total_count": len(all_stacks),
                "limited_count": len(limited),
            },
        }

    except AssertionError as e:
        return {"status": "FAIL", "message": str(e)}
    except Exception as e:
        return {"status": "ERROR", "message": f"{type(e).__name__}: {str(e)}"}


@pytest.mark.integration
async def test_get_switch_stack(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test get_switch_stack for discovered stack."""
    try:
        stack_list = await switching.list_switch_stacks(
            site_id=env.site_id,
            settings=settings,
            limit=1,
        )

        if not stack_list:
            return {"status": "SKIP", "message": "No switch stacks found for details test"}

        stack_id = stack_list[0].get("id")
        assert stack_id, "Switch stack must have an ID"

        result = await switching.get_switch_stack(
            site_id=env.site_id,
            switch_stack_id=stack_id,
            settings=settings,
        )

        assert isinstance(result, dict), "Result must be a dictionary"
        assert "name" in result, "Switch stack details must have name"
        assert result.get("id") == stack_id, "ID must match"

        return {
            "status": "PASS",
            "message": f"Retrieved details for switch stack {result.get('name')}",
            "details": {
                "stack_id": stack_id[:8] + "...",
                "name": result.get("name", "unnamed"),
            },
        }

    except AssertionError as e:
        return {"status": "FAIL", "message": str(e)}
    except Exception as e:
        return {"status": "ERROR", "message": f"{type(e).__name__}: {str(e)}"}


@pytest.mark.integration
async def test_get_switch_stack_missing(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test get_switch_stack with non-existent ID (expect error)."""
    try:
        fake_id = "497f6eca-6276-4993-bfeb-53cbbbba6f08"

        await switching.get_switch_stack(
            site_id=env.site_id,
            switch_stack_id=fake_id,
            settings=settings,
        )

        return {
            "status": "FAIL",
            "message": "Expected ResourceNotFoundError but got result",
        }

    except ResourceNotFoundError:
        return {
            "status": "PASS",
            "message": "Correctly raised ResourceNotFoundError for missing switch stack",
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"Unexpected error type: {type(e).__name__}: {str(e)}",
        }


@pytest.mark.integration
async def test_list_mclag_domains(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test list_mclag_domains tool."""
    try:
        result = await switching.list_mclag_domains(
            site_id=env.site_id,
            settings=settings,
        )

        assert isinstance(result, list), "Result must be a list"

        if not result:
            return {
                "status": "SKIP",
                "message": "No MC-LAG domains found (site may be unconfigured)",
            }

        domain = result[0]
        assert "id" in domain, "MC-LAG domain must have id"
        assert "name" in domain, "MC-LAG domain must have name"

        return {
            "status": "PASS",
            "message": f"Listed {len(result)} MC-LAG domains",
            "details": {
                "count": len(result),
                "first_domain": domain.get("name", "unknown"),
            },
        }

    except AssertionError as e:
        return {"status": "FAIL", "message": str(e)}
    except Exception as e:
        return {"status": "ERROR", "message": f"{type(e).__name__}: {str(e)}"}


@pytest.mark.integration
async def test_get_mclag_domain(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test get_mclag_domain for discovered domain."""
    try:
        domain_list = await switching.list_mclag_domains(
            site_id=env.site_id,
            settings=settings,
            limit=1,
        )

        if not domain_list:
            return {"status": "SKIP", "message": "No MC-LAG domains found for details test"}

        domain_id = domain_list[0].get("id")
        assert domain_id, "MC-LAG domain must have an ID"

        result = await switching.get_mclag_domain(
            site_id=env.site_id,
            mclag_domain_id=domain_id,
            settings=settings,
        )

        assert isinstance(result, dict), "Result must be a dictionary"
        assert "name" in result, "MC-LAG domain details must have name"
        assert result.get("id") == domain_id, "ID must match"

        return {
            "status": "PASS",
            "message": f"Retrieved details for MC-LAG domain {result.get('name')}",
            "details": {
                "domain_id": domain_id[:8] + "...",
                "name": result.get("name", "unnamed"),
            },
        }

    except AssertionError as e:
        return {"status": "FAIL", "message": str(e)}
    except Exception as e:
        return {"status": "ERROR", "message": f"{type(e).__name__}: {str(e)}"}


@pytest.mark.integration
async def test_get_mclag_domain_missing(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test get_mclag_domain with non-existent ID (expect error)."""
    try:
        fake_id = "497f6eca-6276-4993-bfeb-53cbbbba6f08"

        await switching.get_mclag_domain(
            site_id=env.site_id,
            mclag_domain_id=fake_id,
            settings=settings,
        )

        return {
            "status": "FAIL",
            "message": "Expected ResourceNotFoundError but got result",
        }

    except ResourceNotFoundError:
        return {
            "status": "PASS",
            "message": "Correctly raised ResourceNotFoundError for missing MC-LAG domain",
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"Unexpected error type: {type(e).__name__}: {str(e)}",
        }


@pytest.mark.integration
async def test_list_lags(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test list_lags tool."""
    try:
        result = await switching.list_lags(
            site_id=env.site_id,
            settings=settings,
        )

        assert isinstance(result, list), "Result must be a list"

        if not result:
            return {
                "status": "SKIP",
                "message": "No LAGs found (site may be unconfigured)",
            }

        lag = result[0]
        assert "id" in lag, "LAG must have id"
        assert "type" in lag, "LAG must have type"

        return {
            "status": "PASS",
            "message": f"Listed {len(result)} LAGs",
            "details": {
                "count": len(result),
                "first_lag_type": lag.get("type", "unknown"),
            },
        }

    except AssertionError as e:
        return {"status": "FAIL", "message": str(e)}
    except Exception as e:
        return {"status": "ERROR", "message": f"{type(e).__name__}: {str(e)}"}


@pytest.mark.integration
async def test_get_lag_details(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test get_lag_details for discovered LAG."""
    try:
        lag_list = await switching.list_lags(
            site_id=env.site_id,
            settings=settings,
            limit=1,
        )

        if not lag_list:
            return {"status": "SKIP", "message": "No LAGs found for details test"}

        lag_id = lag_list[0].get("id")
        assert lag_id, "LAG must have an ID"

        result = await switching.get_lag_details(
            site_id=env.site_id,
            lag_id=lag_id,
            settings=settings,
        )

        assert isinstance(result, dict), "Result must be a dictionary"
        assert "type" in result, "LAG details must have type"
        assert result.get("id") == lag_id, "ID must match"

        return {
            "status": "PASS",
            "message": f"Retrieved details for LAG {lag_id[:8]}...",
            "details": {
                "lag_id": lag_id[:8] + "...",
                "type": result.get("type", "unknown"),
                "member_count": len(result.get("members", [])),
            },
        }

    except AssertionError as e:
        return {"status": "FAIL", "message": str(e)}
    except Exception as e:
        return {"status": "ERROR", "message": f"{type(e).__name__}: {str(e)}"}


@pytest.mark.integration
async def test_get_lag_details_missing(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test get_lag_details with non-existent ID (expect error)."""
    try:
        fake_id = "497f6eca-6276-4993-bfeb-53cbbbba6f08"

        await switching.get_lag_details(
            site_id=env.site_id,
            lag_id=fake_id,
            settings=settings,
        )

        return {
            "status": "FAIL",
            "message": "Expected ResourceNotFoundError but got result",
        }

    except ResourceNotFoundError:
        return {
            "status": "PASS",
            "message": "Correctly raised ResourceNotFoundError for missing LAG",
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"Unexpected error type: {type(e).__name__}: {str(e)}",
        }


def create_switching_suite() -> TestSuite:
    """Create the switching test suite."""
    return TestSuite(
        name="switching",
        description="Switching Tools - switch stacks, MC-LAG domains, LAGs",
        tests=[
            test_list_switch_stacks,
            test_list_switch_stacks_pagination,
            test_get_switch_stack,
            test_get_switch_stack_missing,
            test_list_mclag_domains,
            test_get_mclag_domain,
            test_get_mclag_domain_missing,
            test_list_lags,
            test_get_lag_details,
            test_get_lag_details_missing,
        ],
    )


# CLI entry point
if __name__ == "__main__":
    import asyncio
    import sys
    from pathlib import Path

    async def main():
        harness = TestHarness()
        harness.verbose = "--verbose" in sys.argv or "-v" in sys.argv

        suite = create_switching_suite()
        harness.register_suite(suite)

        # Parse environment filter
        env_filter = None
        if "--env" in sys.argv:
            idx = sys.argv.index("--env")
            if idx + 1 < len(sys.argv):
                env_filter = [sys.argv[idx + 1]]

        # Run suite
        await harness.run_suite("switching", environment_filter=env_filter)

        # Print summary
        harness.print_summary()

        # Export results if requested
        if "--export" in sys.argv:
            idx = sys.argv.index("--export")
            output_file = (
                Path(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else Path("test_results.json")
            )
            harness.export_results(output_file)

        # Exit with error code if any tests failed
        failed_count = sum(1 for r in harness.results if r.status.value in ["FAIL", "ERROR"])
        sys.exit(1 if failed_count > 0 else 0)

    asyncio.run(main())
