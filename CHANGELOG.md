# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] (squashbirdie fork)

### Changed

- **Dependency refresh** (`uv lock --upgrade`, floors in `pyproject.toml` raised to the tested versions).
  Notable majors: `fastmcp` 3.2 -> 4.1, `mcp` 1.26 -> 2.3, `cryptography` 46 -> 50, `pydantic` 2.12 -> 2.14,
  `authlib` 1.6 -> 1.8, `PyJWT` 2.12 -> 2.15, `urllib3` 2.6 -> 2.8; dev: `mypy` 1.18 -> 2.4, `isort` 7 -> 9,
  `black` 26.3 -> 26.10, `pytest` 9.0 -> 9.1. No source changes were needed: 1250 unit tests pass on
  Python 3.12 and 3.14, the stdio tool list is identical (197 tools), and 11 live read-only calls against a
  UDM return byte-identical results before and after.
- Note for deployers: `uvx --from <tarball>` ignores `uv.lock` and resolves from the `pyproject.toml` floors,
  so a fresh uv cache already floated to the latest majors before this change. `fastmcp` is now capped `<5` and
  `mcp[cli]` `<3` so it cannot float to an untested major.
- `mypy src` is clean (was 16 errors) and `black`/`isort`/`ruff` pass. Typing-only changes (`cast`, a
  `dict[str, Any]` annotation, targeted `type: ignore`s); runtime behaviour is unchanged. The `settings: Settings = None`
  signature of `update_firewall_policy`/`delete_firewall_policy` is kept as is because `register_module_tools` injects it.

### Fixed

- **Integration API paths rejected the short site name** (`'default' is not a valid 'siteId' value`,
  `400 api.request.argument-type-mismatch`). `UniFiClient._request` now rewrites a non-UUID site segment in
  local `/integration/v1/sites/{site}/...` paths to the site UUID (`_resolve_integration_site`, reusing
  `resolve_site_id` and its cache), so every tool that builds those paths by hand works with `site_id="default"`.
  Verified live: `list_pending_devices`, `list_wan_connections`, `list_site_to_site_vpns`, `list_vpn_servers`,
  `list_device_tags`, `list_radius_profiles`, `list_switch_stacks`, `list_lags` and `list_mclag_domains` now
  succeed with `default`; an unknown name raises a clear `site 'x' not found`. Not yet fixed, separate cause:
  `list_vouchers`, `list_hotspot_packages` and `get_guest_portal_config` now reach the right site but the
  controller answers 404 because those Integration endpoints do not exist (enuno/unifi-mcp-server #122, #123
  and #130 move them to the routes that do).

## [0.2.7] - 2026-08-26 (squashbirdie fork)

### Fixed

- **`TrafficMatchingList`/`ACLRule` were still wrong after 0.2.6** — that release's fixes were
  necessary but not sufficient. Rebuilt both against the actual OpenAPI spec
  (`developer.ui.com/network/v10.4.57/openapi.json`, fetched live) rather than guessing from
  single observed responses:
  - **`TrafficMatchingList` items**: 0.2.6 assumed a flat `{"type": str, "value": str}` shape
    for every item. The real shape is a *per-list-type* discriminated union: `PORTS` items are
    `{"type": "PORT_NUMBER", "value": <int>}` (an integer, not a string — the exact bug that
    broke `list_traffic_matching_lists` in production, `items.0.value` "Input should be a
    valid string" for values like `50000`) or `{"type": "PORT_NUMBER_RANGE", "start": <int>,
    "stop": <int>}`; `IPV4_ADDRESSES`/`IPV6_ADDRESSES` items are `IP_ADDRESS`/`SUBNET` (and,
    IPv4 only, `IP_ADDRESS_RANGE`). None of the range variants existed in the old model at all.
    `create_traffic_matching_list`/`update_traffic_matching_list` sent the same wrong flat
    shape on write. New tool signatures accept plain ints/strings/range-dicts and build the
    correct discriminated payload (see `_normalise_traffic_matching_item`).
  - **`ACLRule`**: was an entirely guessed flat shape (`source_type`, `dst_port`,
    `source_network`, ...) that does not exist in the real API at all — it only ever "worked"
    because every field was `Optional` and the one production controller checked against had
    zero ACL rules to validate against. The real shape is a discriminated union on `type`
    (`IPV4`/`MAC`), each carrying `sourceFilter`/`destinationFilter` objects that are
    themselves discriminated unions (`NETWORKS`/`PORTS`/`IP_ADDRESSES_OR_SUBNETS` for IPv4,
    `MAC_ADDRESSES` for MAC). **This also means `create_acl_rule`'s previous claim that "the
    integration API accepts only `{name, action, type, enabled}`" was wrong** — it was a
    symptom of the wrong field names being tried, not a real API limitation.
    `create_acl_rule`/`update_acl_rule` now accept flat, auto-detected filter parameters
    (`source_network_ids`, `destination_ip_addresses_or_subnets`, `source_mac_addresses`, ...,
    matching the existing `firewall_policies.py` convention) and build the correct nested
    request body.
  - **A real business rule found only by a live mutation, not the spec**: the integration API
    rejects any ACL rule port filter with no `protocolFilter` set
    (`api.acl-rule.validation.port-filter-not-allowed-without-protocol-filter`) — undocumented
    in the OpenAPI schema, which marks both fields independently optional. `create_acl_rule`/
    `update_acl_rule` now check this locally and raise before a network round trip, rather than
    surfacing a raw 400.
  - Both models now use `pydantic.TypeAdapter` for parsing (`parse_acl_rule`,
    `parse_traffic_matching_list`) since a real discriminated union can't be instantiated by
    calling a class directly — `ACLRule(**data)` is gone; callers use the module-level
    function instead.

### Notes

- **Fully verified against a live UDM Pro (Network 10.5.67), real mutations, not just parsing**:
  for both `create_traffic_matching_list` and `create_acl_rule`, ran a real
  create → get → list → delete round trip against the live controller (site
  `88f7af54-98f8-306a-a1c7-c9349722b1f6`) using the fork's own client code directly, bypassing
  the MCP protocol. Confirmed: POST returns `201` and the response parses cleanly through the
  new models; the created object is retrievable by ID and appears in the list; DELETE returns
  `200` and leaves no residue (checked with a follow-up list). The port-filter/protocol-filter
  rule above was found exactly this way — a "should have worked" request came back a real
  `400` from the live controller with a specific error code, which is what prompted adding the
  local check. Every test artifact created during verification was deleted immediately after;
  a final listing confirmed zero leftover ACL rules and zero leftover traffic matching lists
  bearing the `DELETE-ME` marker used during testing.
- 1250 tests pass (up from 1243 in 0.2.6); the ACL/traffic-matching-list test fixtures were
  themselves wrong in the same way the models were (`_id` instead of `id`, string port values,
  a nonexistent `IPV6_ADDRESS` item type) and are rewritten to match the real spec.

## [0.2.6] - 2026-08-26 (squashbirdie fork)

### Fixed

- **Critical: local-mode site UUID resolution (~25 broken tools)**. Every tool that built an
  `/ea/sites/{site_id}/...` or `/proxy/network/v2/api/site/{site_id}/...` endpoint from a raw
  site UUID — which is what every other endpoint on the fleet actually returns — silently
  failed against a real local controller with `api.err.NoSiteContext`, because the UUID → short
  `internalReference` ("default") mapping was only ever built as a side effect of calling
  `authenticate()` first, and almost no tool function did. Root-caused and fixed by adding
  `UniFiClient._ensure_site_map()`, called unconditionally at the top of `_request()` (bounded,
  non-recursive), plus a process-wide `_SITE_MAP_CACHE` shared across client instances so the
  fix doesn't cost a repeated `/sites` round trip on every single tool call. Also generalized
  `_translate_endpoint`'s UUID substitution to cover `/proxy/network/api/s/{id}/...` and
  `/proxy/network/v2/api/site/{id}/...`, not just the original `/ea/sites/{id}/...` pattern.
  Verified against a live UDM Pro (Network 10.5.67): 48/72 previously-failing read tools now
  pass; the remainder are genuine controller-side gaps (Site Manager disabled by config,
  backups/vouchers/hotspot/guest-portal/speedtest/spectrum-scan endpoints confirmed absent from
  this firmware's local Integration API — not fork bugs).
- **`get_application_info` 404**: hit `/integration/v1/application/info`, which does not exist
  (`No endpoint GET /integration/v1/application/info`). The real endpoint is
  `/integration/v1/info`, and its response is only `{"applicationVersion": "..."}` — no
  `build`/`deploymentType`/`capabilities`/`systemInfo`, which the old code assumed unconditionally.
- **`list_pending_devices` 400**: built `/devices/pending` as a path segment, which the
  controller parsed as a literal `deviceId` of `"pending"`
  (`'pending' is not a valid 'deviceId' value`). Pending devices are a filter over the plain
  `/devices` listing (`filter=state.eq('PENDING')`), not a sub-resource.
- **ACL rules and traffic matching lists incorrectly refused on local gateways**. Both raised
  `NotImplementedError` unconditionally for `api_type == LOCAL`, based on the (once true, no
  longer true) assumption that these were cloud/Integration-API-only. The local Integration API
  mirror has supported both since it went GA (Network App >= 9.3); verified live —
  `GET .../acl-rules` and `GET .../traffic-matching-lists` both return 200 with real data
  against a UDM Pro on Network 10.5.67.
- **`DPICategory`/`DPIApplication` models rejected every real response**: required a Mongo-style
  `_id` string alias; the actual Integration API returns a plain integer `id`
  (`{"id": 0, "name": "Instant messengers"}`). `DPIApplication` additionally required
  `category_id`, which does not exist at this endpoint at all.
- **`WANConnection` model rejected every real response**: required `site_id`, `wan_type`,
  `interface`, and `status`, none of which the `/sites/{id}/wans` endpoint returns — it's just
  `{"id": "...", "name": "Internet 1"}`. Relaxed to optional rather than invented, since no
  endpoint that populates them was found.
- **`TrafficMatchingList` model rejected every real response**: same `_id` alias bug, plus
  `items` was typed as `list[str]` when the real API returns typed objects
  (`{"type": "IP_ADDRESS", "value": "10.0.1.25"}`). Added a proper `TrafficMatchingListItem`
  submodel.

### Notes

- `zbf_matrix.py`'s deprecation notice (zone-policy matrix / per-zone application blocking
  endpoints do not exist) re-verified 2026-08-26 against Network 10.5.67 — still holds, five-plus
  minor versions after the original 2025-11-18 finding on v10.0.156.
- Not fixed, left as documented gaps rather than guessed at: `backups.list_backups` /
  `get_backup_schedule` (both still fail even with a correctly-resolved site name — a deeper,
  separate issue), and `vouchers`/`hotspot`/`guest-portal` (confirmed genuinely absent from this
  firmware's local Integration API, not currently exposed via this deployment's tool allowlist
  either).

### Tests

- Added `TestUniFiClientEnsureSiteMap` (5 tests) and 3 new `TestUniFiClientEndpointTranslation`
  cases covering the site-map fix, including a shared-cache-across-instances regression test and
  an end-to-end `client.get()` test with no prior `authenticate()` call — the exact shape every
  broken tool function used.
- Added `isolate_site_map_cache` autouse fixture to `conftest.py` — the new process-wide cache is
  keyed by `base_url`, which several existing fixtures share, so tests need it cleared between
  runs to stay order-independent.
- Rewrote `test_application_tools.py`, and updated fixtures in `test_dpi_tools.py` and
  `test_traffic_matching_lists_tools.py`, to match the corrected (real, verified) API response
  shapes — the previous fixtures encoded the same wrong assumptions the model/endpoint fixes
  above correct.
- Full suite: 1,243 passing.

## [0.2.4] - 2026-02-19

### Fixed

- **Critical startup bug (issue #42)**: `ImportError: cannot import 'config' from 'agnost'` prevented the server from starting for all users, even when `AGNOST_ENABLED=false`. Root cause: `agnost` v0.1.13 removed the `config` export, and the old code imported it unconditionally at module top-level. Fixed by moving agnost imports inside the conditional block — they now only execute when `AGNOST_ENABLED=true` and `AGNOST_ORG_ID` is set, and any import or runtime failure is gracefully caught and logged as a warning.

### Tests

- Added `tests/unit/test_main_agnost_import.py` with 3 regression tests covering missing `config` export, agnost not installed, and agnost disabled scenarios.
- Test count: 1,159 passing (up from 1,156).

## [0.2.3] - 2026-02-18

### Added

**RADIUS & Guest Portal — Complete CRUD (4 new tools)**

- `get_radius_account` — Retrieve a single RADIUS account by ID; password field auto-redacted
- `update_radius_account` — Update username, password, VLAN, tunnel type, enabled status, and notes; confirm/dry-run support
- `get_hotspot_package` — Retrieve a single hotspot package by ID
- `update_hotspot_package` — Update name, duration, bandwidth limits, quotas, price, currency, and enabled status; confirm/dry-run support

These complete full CRUD for RADIUS accounts and hotspot packages. Phase 6 (Enhanced RADIUS & Guest Portal) is now feature-complete.

### Fixed

- **QoS Tools**: Fixed runtime `TypeError` in 6 `audit_action` calls in `qos.py` that incorrectly used `action=` keyword argument instead of the required `action_type=`. Affected `create_qos_profile`, `update_qos_profile`, `configure_smart_queue`, `disable_smart_queue`, `create_traffic_route`, `update_traffic_route`. Would have crashed at runtime whenever audit logging was enabled.
- **Site Manager**: Removed duplicate `@require_site_manager` decorator on `get_sdwan_config_status` (was applied twice — redundant and confusing).
- **Topology Tests**: Fixed 6 `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` warnings in the topology test suite. Root cause: 6 tests called `client.settings.get_integration_path()` through an auto-created `AsyncMock` (because `mock_instance.settings` was not set). Fixed by adding `mock_instance.settings = mock_settings` to each affected test.
- **Backup Client**: Added 3 missing methods to `UniFiClient` that `backups.py` calls at runtime:
  - `get_restore_status(operation_id)` — returns `not_supported` stub (endpoint not in UniFi API)
  - `configure_backup_schedule(...)` — `PUT /proxy/network/api/s/{site}/rest/backup/schedule`
  - `get_backup_schedule(site_id)` — `GET /proxy/network/api/s/{site}/rest/backup/schedule`
  Previously these silently fell back to an `AttributeError` handler in `backups.py`.

### Tests

- Added `TestUniFiClientBackupMethods` with 5 tests covering the new backup client methods.
- Test count: 1,156 passing (up from 1,128).
- Zero `RuntimeWarning` coroutine warnings (down from 6).

## [0.2.2] - 2026-02-16

### 🎉 Feature Release - Port Profile Management & Security Hardening

This release adds comprehensive switch port management capabilities, fixes critical security vulnerabilities, corrects API endpoint issues, and improves code quality across the codebase.

### Added

**Port Profile & Switch Port Management (8 new tools)**

- `list_port_profiles` - Paginated listing of switch port profiles with filtering
- `get_port_profile` - Fetch detailed port profile configuration by ID
- `create_port_profile` - Create port profiles with full configuration:
  - PoE settings (auto, passthrough, 24V, 48V, passthrough+)
  - VLAN configuration (native, trunk, excluded VLANs)
  - 802.1X port-based authentication
  - LLDP-MED voice VLAN support
  - Port speed/duplex configuration
  - Port isolation and storm control
- `update_port_profile` - Update profiles with fetch-then-merge to preserve fields
- `delete_port_profile` - Delete port profiles with existence verification
- `get_device_port_overrides` - Retrieve per-port overrides and full port table for devices
- `set_device_port_overrides` - Apply port-specific configuration:
  - Smart merge by `port_idx` (preserves other ports)
  - Full replace mode for complete reconfiguration
  - Validation of required fields (`port_idx`, `portconf_id`)
- `get_device_by_mac` - Look up devices by MAC address for port configuration

**Pydantic Models**

- `PortProfile` - Complete port profile data model with validation
- `PortOverride` - Per-port override configuration
- `PortTableEntry` - Read-only port status and statistics
- `DuplicateResourceError` - Exception for duplicate name detection

**Test Coverage**

- 75 new unit tests for port profile tools (100% of new code covered)
- Total test count: 1,068 (up from 990)
- All tests passing across Python 3.10, 3.11, 3.12

### Security

**Critical Dependency Updates (18 vulnerabilities fixed)**

- **FastMCP**: 0.1.0 → 2.14.5
  - Fixed CVE-2025-66416 (high severity)
  - Fixed auth integration confused deputy attack (high)
  - Fixed reflected XSS in callback page (medium)
  - Fixed Windows command injection (medium)
- **MCP SDK**: 1.16.0 → 1.26.0
  - Enabled DNS rebinding protection by default (high)
- **cryptography**: 43.0.0 → 46.0.5
  - Fixed SECT curve subgroup attack vulnerability (high)
- **httpx**: 0.27.0 → 0.28.1
- **pydantic**: 2.0.0 → 2.12.5
- **agnost**: 0.1.8 → 0.1.12
- **urllib3**: Added >=2.3.0 requirement
  - Fixed decompression bomb safeguards bypass (high)
  - Fixed unbounded links in decompression chain (high)
  - Fixed O(n²) streaming API DoS (high)

**Security Hardening**

- Removed `session-work.md` and `TEST_RESULTS.md` from git tracking (contained real internal IPs)
- Added both files to `.gitignore` to prevent future leaks
- Replaced PII in `SECURITY.md` (placeholder emails → GitHub Security Advisories)
- MAC address sanitization in logs and error messages (masked to `aa:bb:cc:xx:xx:xx`)
- Git history verified clean - no secrets ever committed

### Fixed

**API Endpoint & Payload Corrections**

- **RADIUS Tools** - Corrected endpoints and field names:
  - Profile endpoints: `/integration/v1/.../radius/profiles` → `/ea/sites/.../rest/radiusprofile`
  - Account endpoints: `/integration/v1/.../radius/accounts` → `/ea/sites/.../rest/account`
  - Password field: `password` → `x_password` (actual UniFi API field)
  - VLAN field: `vlan_id` → `vlan`
  - Auto-populate `tunnel_type`/`tunnel_medium_type` when VLAN specified
  - Secrets redacted (`***REDACTED***`) in all responses
  - Fixed list response handling at 5 locations (prevents `AttributeError` on `.get()`)

- **Firewall Tools** - New payload fields for proper rule creation:
  - Added `ruleset` (default `WAN_IN`) and `rule_index` (default `2000`)
  - Added `src_networkconf_id`/`dst_networkconf_id` with type variants (default `None`, typed `str | None`)
  - Added connection state flags: `state_established`, `state_related`, `state_new`, `state_invalid`
  - Added traffic `logging` flag
  - Fixed parameter names: `source`/`destination` → `src_address`/`dst_address`

- **WLAN Tools** - New creation parameters:
  - Added `networkconf_id` - associate SSID with specific network
  - Added `ap_group_ids`/`ap_group_mode` - per-AP-group broadcasting
  - Added `wlan_bands` - band selection (`2g`, `5g`, or both)
  - Added IoT optimization and minimum data rate controls

- **Network Config Tools** - Fixed VLAN field name (`vlan_id` → `vlan`)

- **All Tools** - Boolean parameter coercion (`"true"` → `True`) for MCP JSON-RPC compatibility

**Bug Fixes**

- Fixed `dry_run` requiring `confirm=True` - `validate_confirmation()` now accepts `dry_run` parameter
- Fixed missing `DuplicateResourceError` exception (was imported but not defined)
- Fixed RADIUS response crashes where list responses were passed to `.get()` or Pydantic constructors
- Updated all 55 call sites across 16 tool modules for dry_run fix

**Code Quality**

- Added full type hints to `coerce_bool(value: bool | str | None) -> bool`
- Added full type hints to `validate_confirmation(confirm: bool | str | None, operation: str, dry_run: bool | str = False) -> None`
- Port profile tools validate responses through Pydantic models before returning
- Fixed import ordering (isort) across all files

### Changed

- Tool count: 74 → 82+ MCP tools
- Test count: 990 → 1,068 tests
- Updated version references in README.md, CLAUDE.md, pyproject.toml

### Technical Details

**Commits**

- `94277cb` - Fix RADIUS, firewall, WLAN, network endpoints/payloads (29 files)
- `20efe10` - Add port profile and device port override tools (6 files)
- `b7c0489` - Remove PII, harden repo for public release (4 files)
- `448b916` - Add missing DuplicateResourceError exception (2 files)
- `653d957` - Allow dry_run without confirm, fix firewall param names
- `360339f` - Add type hints to coerce_bool and validate_confirmation
- `d666965` - Validate port profile responses through Pydantic models
- `e77129c` - Fix MAC leak in logs/errors, firewall defaults, RADIUS response handling
- `ffe8d86` - Merge PR #35: port profile tools, API fixes, and security hardening
- `9feb15b` - Style: apply black and isort formatting fixes
- `ddaa9e9` - Fix(deps): update dependencies to address security vulnerabilities
- `5674286` - Style: fix isort import ordering
- `ffc1e6e` - Docs: update documentation for v0.2.2 release

**Statistics**

- 40 files changed (+2,726 / -1,235 lines)
- 8 new MCP tools (total: ~82)
- 75 new unit tests (total: 1,068)
- 3 new Pydantic models
- 1 new exception class
- 18 security vulnerabilities fixed
- 0 test failures
- 6 warnings (pre-existing async mock coroutines)

## [0.2.1] - 2026-01-25

### 🔧 Critical Bug Fix - Topology Tools

Fixed topology tools that were completely non-functional due to using non-existent API endpoints.

### Fixed

- **Topology Tools (5 tools)**: Rewrote all topology tools to use correct Integration API endpoints
  - Changed from non-existent `/api/s/{site}/stat/topology` to proper Integration API endpoints
  - Now uses `/v1/sites/{siteId}/devices` and `/v1/sites/{siteId}/clients`
  - Updated data model field names to match Integration API response format
  - Fixed endpoint path construction using `get_integration_path()` for proper API translation
  - Added pagination support for large device/client lists
  - Fixed network depth calculation and client connection type detection

### Added

- **Integration Test Framework**: Comprehensive test harness for real-world validation
  - Multi-environment support (6 environments: 2 local + 4 cloud)
  - API mode testing (local, cloud-v1, cloud-ea)
  - Intelligent test skipping for unsupported API features
  - Detailed reporting with pass/fail/skip statistics
  - JSON export for CI/CD integration
  - Dry-run mode for test planning
  - Test suite organization with setup/teardown hooks
- **Topology Test Suite**: 8 comprehensive tests with 100% pass rate on local APIs
- **Test Documentation**: Complete guide for writing and running integration tests

### Technical Details

**Data Model Changes**:

- `device._id` → `device.id`
- `device.mac` → `device.macAddress`
- `device.ip` → `device.ipAddress`
- `uplink.device_id` → `uplink.deviceId`
- `device.state` (int) → `device.state` (string: "CONNECTED"|other)

**Test Results**:

- 16/16 tests PASSED on local APIs (100%)
- 32/32 tests SKIPPED on cloud APIs (expected - topology not supported)
- 0 FAILED
- Total test duration: 6.97s across 6 environments

**API Limitations Documented**:

- Local APIs: Full topology support
- Cloud APIs (v1 & EA): Aggregate statistics only, no device-level data

## [0.2.0] - 2026-01-25

### 🎉 Production Release - All Features Complete

This is the definitive v0.2.0 release with all 7 planned feature phases complete, comprehensive testing, and production-ready quality.

### Added

**Phase 1: QoS Enhancements (11 tools)**

- QoS profile management (list, get, create, update, delete)
- Reference QoS profiles and ProAV templates
- Traffic routing with time-based schedules
- Application-based QoS configuration
- Coverage: 82.43% (46 tests passing)

**Phase 2: Backup & Restore (8 tools)**

- Manual and automated backup creation
- Backup listing and download with checksum verification
- Backup restore functionality
- Automated scheduling with cron expressions
- Cloud synchronization tracking
- Coverage: 86.32% (10 tests passing)

**Phase 3: Multi-Site Aggregation (4 tools)**

- Cross-site device and client analytics
- Site health monitoring and scoring
- Side-by-side site comparison
- Consolidated reporting across locations
- Coverage: 92.95% (10 tests passing)

**Phase 4: ACL & Traffic Filtering (7 tools)**

- Layer 3/4 access control list management
- Traffic matching lists (IP, MAC, domain, port groups)
- Firewall policy automation
- Rule ordering and priority management
- Coverage: 89.30-93.84%

**Phase 5: Site Management (9 tools)**

- Multi-site provisioning and configuration
- Site-to-site VPN setup
- Device migration between sites
- Advanced site settings management
- Configuration export for backup
- Coverage: 92.95% (10 tests passing)

**Phase 6: RADIUS & Guest Portal (6 tools)**

- RADIUS profile configuration (802.1X authentication)
- RADIUS accounting server support
- Guest portal customization
- Hotspot billing and voucher management
- Session timeout and redirect control
- Coverage: 69.77% (17 tests passing)

**Phase 7: Network Topology (5 tools)**

- Complete network topology graph retrieval
- Multi-format export (JSON, GraphML, DOT)
- Device interconnection mapping
- Port-level connection tracking
- Network depth analysis
- Coverage: 95.83% (29 tests passing)

### Quality Metrics

- **74 Total MCP Tools**: Comprehensive UniFi network management
- **990 Tests Passing**: Robust validation across all modules
- **78.18% Test Coverage**: 4,865 of 6,105 statements covered
- **18/18 CI/CD Checks Passing**: All quality gates met
- **Zero Security Vulnerabilities**: Clean security scans
- **30+ AI Assistant Example Prompts**: Comprehensive usage documentation

### Documentation

- Added comprehensive VERIFICATION_REPORT.md documenting complete testing and validation
- Added 30+ AI assistant example prompts across 10 categories in API.md
- Updated API.md with all 74 tools documented with examples
- Updated UNIFI_API.md with complete API endpoint reference

### Fixed

- CodeQL security alerts resolved (wrong parameter names in QoS tools)
- Secret redaction in RADIUS dry-run logging
- Pre-commit hook failures (import formatting)
- Duplicate function definitions
- Test coverage gaps in critical paths

### Changed

- License: Apache 2.0
- Architecture: All 7 feature phases complete
- Test coverage improved from 41.27% to 78.18%
- Total tests increased from 228 to 990

### Release Artifacts

- Docker: ghcr.io/enuno/unifi-mcp-server:0.2.0 (multi-arch: amd64, arm64, arm/v7)
- npm: unifi-mcp-server@0.2.0
- PyPI: unifi-mcp-server==0.2.0
- GitHub: <https://github.com/enuno/unifi-mcp-server/releases/tag/v0.2.0>

See [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md) for complete details.

---

## [0.1.4] - 2025-11-17

### Version Correction Notice

This release corrects a premature v0.2.0 release. The code is identical to v0.2.0, but v0.1.4 is the correct version number. The true v0.2.0 release is planned for Q1 2025 with complete Zone-Based Firewall implementation, full Traffic Flow monitoring, and 80%+ test coverage.

### Added

- Comprehensive WiFi tools test suite with 23 tests and 70.34% coverage
- Cloud API compatibility for Site model using Pydantic v2 validation_alias
- Support for both Cloud API (`siteId`, `isOwner`) and Local API (`_id`, `name`) schemas
- 17 comprehensive unit tests for Site model covering Cloud/Local API compatibility
- Automatic name fallback generation for Cloud API sites without explicit names

### Fixed

- **GitHub Issue #3**: Cloud API schema mismatch in Site model
  - Fixed Pydantic validation errors when using Cloud API
  - Site model now accepts `siteId` (Cloud) and `_id` (Local) field names
  - Site model now accepts `siteName` and `name` field variations
  - Added model_validator to generate fallback names from site IDs
- All 16 failing WiFi tests resolved (23/23 now passing)
  - Fixed mock return value structures to match UniFi API response format
  - Added missing `security` parameter to WLAN creation tests
  - Changed exception types from ConfirmationRequiredError to ValidationError
  - Fixed missing API call mocks for update/delete operations
  - Fixed field name assertions (passphrase → x_passphrase)
  - Rewrote statistics tests to handle dual API calls correctly
- Python 3.10 compatibility issues resolved
- Import sorting issues fixed per isort/pre-commit requirements
- Ruff linting errors in WiFi test suite resolved
- Missing ValidationError import added to Site model tests
- Traffic flows formatting with Black

### Changed

- Site model made backward compatible with existing Local API code
- Enhanced Site model with Cloud API-specific fields (`is_owner`)
- Improved test coverage from 36.83% to 41.27% overall
- Site model test coverage: 100%

### Technical Details

- All 228 tests passing
- Test coverage: 41.27%
- CI/CD pipelines: All checks passing
- Compatible with Python 3.10, 3.11, 3.12

## [0.2.0] - 2025-11-16 [PREMATURE - DO NOT USE]

### ⚠️ Version Correction Notice

**This version was published prematurely. Please use v0.1.4 instead, which contains identical code.**

The true v0.2.0 release is planned for Q1 2025 and will include:

- Complete Zone-Based Firewall (ZBF) implementation (~60% complete as of this release)
- Full Traffic Flow monitoring (~100% complete as of this release)
- Advanced QoS and traffic management
- Backup and restore operations
- 80%+ test coverage (currently 34%)

See [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) for the complete roadmap.

### Original v0.2.0 Release Notes (For Reference)

### Added

- Comprehensive WiFi tools test suite with 23 tests and 70.34% coverage
- Cloud API compatibility for Site model using Pydantic v2 validation_alias
- Support for both Cloud API (`siteId`, `isOwner`) and Local API (`_id`, `name`) schemas
- 17 comprehensive unit tests for Site model covering Cloud/Local API compatibility
- Automatic name fallback generation for Cloud API sites without explicit names

### Fixed

- **GitHub Issue #3**: Cloud API schema mismatch in Site model
  - Fixed Pydantic validation errors when using Cloud API
  - Site model now accepts `siteId` (Cloud) and `_id` (Local) field names
  - Site model now accepts `siteName` and `name` field variations
  - Added model_validator to generate fallback names from site IDs
- All 16 failing WiFi tests resolved (23/23 now passing)
  - Fixed mock return value structures to match UniFi API response format
  - Added missing `security` parameter to WLAN creation tests
  - Changed exception types from ConfirmationRequiredError to ValidationError
  - Fixed missing API call mocks for update/delete operations
  - Fixed field name assertions (passphrase → x_passphrase)
  - Rewrote statistics tests to handle dual API calls correctly
- Python 3.10 compatibility issues resolved
- Import sorting issues fixed per isort/pre-commit requirements
- Ruff linting errors in WiFi test suite resolved
- Missing ValidationError import added to Site model tests
- Traffic flows formatting with Black

### Changed

- Site model made backward compatible with existing Local API code
- Enhanced Site model with Cloud API-specific fields (`is_owner`)
- Improved test coverage from 36.83% to 41.27% overall
- Site model test coverage: 100%

### Technical Details

- All 228 tests passing
- Test coverage: 41.27%
- CI/CD pipelines: All checks passing
- Compatible with Python 3.10, 3.11, 3.12

## [0.1.3] - 2025-01-XX

### Initial Release

- Model Context Protocol (MCP) server for UniFi Network API
- Support for Cloud and Local Controller APIs
- Device, Client, Network, and Site management tools
- Traffic flow monitoring and analysis
- Zone-based firewall (ZBF) management
- WiFi network configuration
- Comprehensive test suite

[0.2.0]: https://github.com/enuno/unifi-mcp-server/compare/v0.1.3...v0.2.0
[0.1.4]: https://github.com/enuno/unifi-mcp-server/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/enuno/unifi-mcp-server/releases/tag/v0.1.3
