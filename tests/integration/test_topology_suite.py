#!/usr/bin/env python3
"""
Topology Tools Integration Test Suite

Tests all topology-related MCP tools against real UniFi environments.
"""

import json
from typing import Any

import pytest

from src.tools import topology
from tests.integration.test_harness import TestEnvironment, TestHarness, TestSuite


@pytest.mark.integration
async def test_get_network_topology(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test get_network_topology tool."""
    # Skip for cloud APIs - they don't support device/client endpoints
    if env.api_type in ["cloud-v1", "cloud-ea"]:
        return {
            "status": "SKIP",
            "message": "Cloud APIs do not support device/client endpoints (aggregate stats only)",
        }

    try:
        result = await topology.get_network_topology(
            site_id=env.site_id,
            settings=settings,
            include_coordinates=False,
        )

        # Validate response structure
        assert isinstance(result, dict), "Result must be a dictionary"
        assert "nodes" in result, "Result must contain 'nodes'"
        assert "connections" in result, "Result must contain 'connections'"
        assert "total_devices" in result, "Result must contain 'total_devices'"
        assert "total_clients" in result, "Result must contain 'total_clients'"

        nodes_count = len(result.get("nodes", []))
        connections_count = len(result.get("connections", []))

        return {
            "status": "PASS",
            "message": f"Retrieved {nodes_count} nodes, {connections_count} connections",
            "details": {
                "total_devices": result.get("total_devices"),
                "total_clients": result.get("total_clients"),
                "total_connections": result.get("total_connections"),
                "max_depth": result.get("max_depth"),
            },
        }
    except AssertionError as e:
        return {"status": "FAIL", "message": str(e)}
    except Exception as e:
        return {"status": "ERROR", "message": f"{type(e).__name__}: {str(e)}"}


@pytest.mark.integration
async def test_export_topology_json(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test export_topology tool with JSON format."""
    if env.api_type in ["cloud-v1", "cloud-ea"]:
        return {"status": "SKIP", "message": "Cloud APIs do not support topology endpoints"}

    try:
        result = await topology.export_topology(
            site_id=env.site_id,
            format="json",
            settings=settings,
        )

        # Validate response
        assert isinstance(result, str), "Result must be a string"
        data = json.loads(result)
        assert "nodes" in data, "JSON must contain 'nodes'"
        assert "connections" in data, "JSON must contain 'connections'"

        return {
            "status": "PASS",
            "message": f"Exported {len(data.get('nodes', []))} nodes as JSON",
            "details": {"format": "json", "size_bytes": len(result)},
        }
    except AssertionError as e:
        return {"status": "FAIL", "message": str(e)}
    except Exception as e:
        return {"status": "ERROR", "message": f"{type(e).__name__}: {str(e)}"}


@pytest.mark.integration
async def test_export_topology_graphml(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test export_topology tool with GraphML format."""
    if env.api_type in ["cloud-v1", "cloud-ea"]:
        return {"status": "SKIP", "message": "Cloud APIs do not support topology endpoints"}

    try:
        result = await topology.export_topology(
            site_id=env.site_id,
            format="graphml",
            settings=settings,
        )

        # Validate response
        assert isinstance(result, str), "Result must be a string"
        assert result.startswith('<?xml version="1.0"'), "GraphML must start with XML declaration"
        assert "<graphml" in result, "Must contain graphml element"
        assert "<node" in result or "<edge" in result, "Must contain nodes or edges"

        return {
            "status": "PASS",
            "message": "Exported topology as GraphML",
            "details": {"format": "graphml", "size_bytes": len(result)},
        }
    except AssertionError as e:
        return {"status": "FAIL", "message": str(e)}
    except Exception as e:
        return {"status": "ERROR", "message": f"{type(e).__name__}: {str(e)}"}


@pytest.mark.integration
async def test_export_topology_dot(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test export_topology tool with DOT format."""
    if env.api_type in ["cloud-v1", "cloud-ea"]:
        return {"status": "SKIP", "message": "Cloud APIs do not support topology endpoints"}

    try:
        result = await topology.export_topology(
            site_id=env.site_id,
            format="dot",
            settings=settings,
        )

        # Validate response
        assert isinstance(result, str), "Result must be a string"
        assert "digraph" in result, "DOT must contain digraph declaration"
        assert "{" in result and "}" in result, "DOT must have graph body"

        return {
            "status": "PASS",
            "message": "Exported topology as DOT",
            "details": {"format": "dot", "size_bytes": len(result)},
        }
    except AssertionError as e:
        return {"status": "FAIL", "message": str(e)}
    except Exception as e:
        return {"status": "ERROR", "message": f"{type(e).__name__}: {str(e)}"}


@pytest.mark.integration
async def test_get_topology_statistics(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test get_topology_statistics tool."""
    if env.api_type in ["cloud-v1", "cloud-ea"]:
        return {"status": "SKIP", "message": "Cloud APIs do not support topology endpoints"}

    try:
        result = await topology.get_topology_statistics(
            site_id=env.site_id,
            settings=settings,
        )

        # Validate response structure
        assert isinstance(result, dict), "Result must be a dictionary"
        assert "total_devices" in result, "Must contain total_devices"
        assert "total_clients" in result, "Must contain total_clients"
        assert "total_connections" in result, "Must contain total_connections"
        assert "max_depth" in result, "Must contain max_depth"

        return {
            "status": "PASS",
            "message": f"{result['total_devices']} devices, {result['total_clients']} clients",
            "details": result,
        }
    except AssertionError as e:
        return {"status": "FAIL", "message": str(e)}
    except Exception as e:
        return {"status": "ERROR", "message": f"{type(e).__name__}: {str(e)}"}


@pytest.mark.integration
async def test_get_device_connections(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test get_device_connections tool."""
    if env.api_type in ["cloud-v1", "cloud-ea"]:
        return {"status": "SKIP", "message": "Cloud APIs do not support topology endpoints"}

    try:
        # First get topology to find a device
        topo = await topology.get_network_topology(site_id=env.site_id, settings=settings)

        devices = [n for n in topo.get("nodes", []) if n.get("node_type") == "device"]
        if not devices:
            return {"status": "SKIP", "message": "No devices found in topology"}

        device_id = devices[0]["node_id"]

        # Get connections for the device
        result = await topology.get_device_connections(
            site_id=env.site_id,
            device_id=device_id,
            settings=settings,
        )

        # Validate response
        assert isinstance(result, list), "Result must be a list"

        return {
            "status": "PASS",
            "message": f"Retrieved {len(result)} connections for device",
            "details": {"device_id": device_id[:8] + "...", "connections": len(result)},
        }
    except AssertionError as e:
        return {"status": "FAIL", "message": str(e)}
    except Exception as e:
        return {"status": "ERROR", "message": f"{type(e).__name__}: {str(e)}"}


@pytest.mark.integration
async def test_get_device_connections_all(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test get_device_connections tool with device_id=None (all devices)."""
    if env.api_type in ["cloud-v1", "cloud-ea"]:
        return {"status": "SKIP", "message": "Cloud APIs do not support topology endpoints"}

    try:
        result = await topology.get_device_connections(
            site_id=env.site_id,
            device_id=None,
            settings=settings,
        )

        # Validate response
        assert isinstance(result, list), "Result must be a list"

        return {
            "status": "PASS",
            "message": f"Retrieved {len(result)} total connections",
            "details": {"connections": len(result)},
        }
    except AssertionError as e:
        return {"status": "FAIL", "message": str(e)}
    except Exception as e:
        return {"status": "ERROR", "message": f"{type(e).__name__}: {str(e)}"}


@pytest.mark.integration
async def test_get_port_mappings(settings, env: TestEnvironment) -> dict[str, Any]:
    """Test get_port_mappings tool."""
    if env.api_type in ["cloud-v1", "cloud-ea"]:
        return {"status": "SKIP", "message": "Cloud APIs do not support topology endpoints"}

    try:
        # First get topology to find a device
        topo = await topology.get_network_topology(site_id=env.site_id, settings=settings)

        devices = [n for n in topo.get("nodes", []) if n.get("node_type") == "device"]
        if not devices:
            return {"status": "SKIP", "message": "No devices found in topology"}

        device_id = devices[0]["node_id"]

        # Get port mappings for the device
        result = await topology.get_port_mappings(
            site_id=env.site_id,
            device_id=device_id,
            settings=settings,
        )

        # Validate response
        assert isinstance(result, dict), "Result must be a dictionary"
        assert "device_id" in result, "Must contain device_id"
        assert "ports" in result, "Must contain ports"
        assert isinstance(result["ports"], dict), "Ports must be a dictionary"

        return {
            "status": "PASS",
            "message": "Retrieved port mappings for device",
            "details": {
                "device_id": device_id[:8] + "...",
                "mapped_ports": len(result["ports"]),
            },
        }
    except AssertionError as e:
        return {"status": "FAIL", "message": str(e)}
    except Exception as e:
        return {"status": "ERROR", "message": f"{type(e).__name__}: {str(e)}"}


# Create the test suite
def create_topology_suite() -> TestSuite:
    """Create the topology test suite."""
    suite = TestSuite(
        name="topology",
        description="Network Topology Tools - retrieve and visualize network structure",
        tests=[
            test_get_network_topology,
            test_export_topology_json,
            test_export_topology_graphml,
            test_export_topology_dot,
            test_get_topology_statistics,
            test_get_device_connections,
            test_get_device_connections_all,
            test_get_port_mappings,
        ],
    )
    return suite


# CLI entry point
if __name__ == "__main__":
    import asyncio
    import sys
    from pathlib import Path

    async def main():
        # Create harness and register suite
        harness = TestHarness()
        harness.verbose = "--verbose" in sys.argv or "-v" in sys.argv

        suite = create_topology_suite()
        harness.register_suite(suite)

        # Parse command line arguments
        env_filter = None
        if "--env" in sys.argv:
            idx = sys.argv.index("--env")
            if idx + 1 < len(sys.argv):
                env_filter = [sys.argv[idx + 1]]

        # Run the suite
        await harness.run_suite("topology", environment_filter=env_filter)

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
