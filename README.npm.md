# UniFi MCP Server

A Model Context Protocol (MCP) server for UniFi Network Controller API.

## Installation

This npm package provides metadata for the MCP registry. The actual server is Python-based.

### Python Installation (Recommended)

```bash
pip install unifi-mcp-server==0.2.0
```

### Docker Installation

```bash
docker pull ghcr.io/enuno/unifi-mcp-server:0.2.0
```

## Usage

```bash
# Run the MCP server
python -m unifi_mcp_server

# Or using Docker
docker run -e UNIFI_HOST=your-controller \
  -e UNIFI_USERNAME=admin \
  -e UNIFI_PASSWORD=password \
  ghcr.io/enuno/unifi-mcp-server:0.2.0
```

## Documentation

Full documentation available at: <https://github.com/enuno/unifi-mcp-server>

## Features

- 74 MCP tools for comprehensive UniFi network management
- Multi-site support
- QoS and traffic management
- Backup and restore operations
- Network topology visualization
- RADIUS authentication configuration

## License

Apache-2.0
