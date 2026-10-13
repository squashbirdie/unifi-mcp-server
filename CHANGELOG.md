# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] (squashbirdie fork)

### Added

- **Opt-in read-only mode, `UNIFI_READ_ONLY=true`** (ported from enuno `149541e`/#153): tools that can change
  state are not registered, so they are absent from the tool list and a call fails with `Unknown tool`.
  Tools are classified by signature (`confirm` or `dry_run` parameter) plus `MUTATING_TOOLS_WITHOUT_GATE`
  (`run_speed_test`, and `download_backup`, which changes nothing on the controller but writes a file on the
  host). Live: 124 of 205 tools remain (118 of 197 before the tools added below); `update_wlan`, `create_firewall_policy`, `delete_acl_rule`,
  `restart_device`, `adopt_device`, `download_backup`, `run_speed_test`, `trigger_backup` and `block_client`
  are absent, reads work. `test_tool_registry.py` asserts that every write-verb tool in `src/tools` is
  classified as mutating, so a new tool that forgets the markers fails the suite.
  The upstream `UNIFI_PROFILE` warning was not ported (this fork has no profiles).
- **Read tools from enuno, cherry-picked** (all read-only, so they stay in read-only mode):
  `list_events`, `list_alarms`, `list_neighboring_aps` (`30e0801`/#144), `list_client_rf_health` (`16be1f2`/#149),
  `get_historical_stats` (the read half of `0a07b34`/#146) and `get_smart_queue_status` (the read half of
  `7a7aee9`/#141). Live: events 1000 (the default limit, so large), alarms 0, neighbouring APs 268, RF health
  for 28 wireless clients, 50 historical rows, Smart Queue disabled on Internet 1.
- **Two write tools came with them and are hidden in read-only mode**: `start_spectrum_scan` (#146) and
  `configure_smart_queue` (#141). Both need `confirm`; neither was run against the controller.
  `7a7aee9` needs `first_response_item` from enuno `68630e0`/#138, which is added to `src/utils/helpers.py`
  (only the helper; that commit's other call-site changes were not taken).

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

### Fixed (batch 6: ported from enuno, after a gap analysis of the 151 upstream commits since `14cf53e`)

Checked against this fork's code before porting; the unit tests pass (1596) but **none of these paths was run
against a controller**: no controller credentials were available in the session that ported them.

- **`audit.log` recorded secrets in the clear** (enuno `7e2e6c5`/#154): `AuditLogger.log_operation` persisted
  tool parameters verbatim, so RADIUS shared secrets, WLAN passphrases and IPsec PSKs reached the file, created
  with the umask default (0644). Credentials are now redacted centrally (`sanitize_credentials`; identifiers
  such as `site_id`, `name` and `mac` are kept), the file is created `0600`, `UNIFI_AUDIT_LOG_PATH` is honoured
  (the old code read a settings field that did not exist) and `UNIFI_AUDIT_LOG_ENABLED` now actually switches
  auditing off. Smoke: `auth_secret` and `x_passphrase` are written as `***`, mode `0600`.
- **`dry_run="false"` silently returned a preview** (fork-wide; upstream only fixed `network_config.py`, `fb79ef4`):
  tools declare `dry_run: bool | str`, and about 19 tool files test `if dry_run:` on the raw value, so a client
  that serializes booleans as strings never wrote anything. The registry wrapper now converts string
  `dry_run`/`confirm` to booleans before the tool runs; an unrecognized `dry_run` string is refused rather than
  read as `False`. Reproduced on `main` through the MCP client (`create_network`, `dry_run="false"` returned
  `{"dry_run": true}`); after the change it attempts the write.
- **Retries could burn about 127 s per request** (enuno `2377218`/#124): with a 30 s timeout and 3 retries, one
  request plus backoff outlasts most MCP client tool-call timeouts, and a tool that authenticates first doubles
  it. Retries now also stop at a wall-clock budget, `UNIFI_RETRY_TOTAL_TIMEOUT` (default 60 s), and fail with a
  message naming it. One change beyond upstream: `NetworkError` is re-raised from `_request`, because a 429 whose
  `Retry-After` exceeds the budget is raised inside the `try` block and was being wrapped as
  `APIError: Unexpected error` (regression test added). `.env.example` now names `UNIFI_REQUEST_TIMEOUT`
  (`UNIFI_TIMEOUT` was never read).
- **`adopt_device`, `execute_port_action`, `authorize_guest` called routes that do not exist** (enuno
  `9cc005d`, hardware-verified upstream on 2026-09-27 against Network 10.x: the legacy routes answer 404, the
  spec routes answer with validation errors). **Breaking:** `adopt_device(site_id, mac, ignore_device_limit)` takes
  a MAC and POSTs `/sites/{id}/devices`; `authorize_guest` takes `client_id` and posts the spec's
  `AUTHORIZE_GUEST_ACCESS` body to `.../clients/{id}/actions`, plus `data_usage_limit_mbytes`;
  `execute_port_action` accepts only `power_cycle` (the one action in the spec) on `.../interfaces/ports/{idx}/actions`;
  `limit_bandwidth` now raises `NotImplementedError` because the Integration API has no equivalent (use
  `authorize_guest` with rate limits). Upstream's evidence is on its hardware, not this controller (10.5.67).
- **`set_ap_radio_channel` reported success for changes the controller dropped** (enuno `a711327`/#142): it PUT
  the whole `stat/device` operational record back, which the controller answers with 200 while ignoring the
  change. It now fetches the config record, PUTs only `radio_table`, compares the echo field by field and
  returns `success: false` with `warnings` (and audits `unconfirmed`) when the stored value differs.
- **`create_wlan` rejected WPA3 and 6 GHz SSIDs** (enuno `6f63573`/#79): `wpa_mode="wpa3"` went to the controller
  literally. It is now sent as `wpa2` plus `wpa3_support=true`, 6 GHz implies WPA3 and PMF `required`, and
  `wpa3_support`, `wpa3_transition` and `pmf_mode` are parameters. `update_wlan` still sends `wpa_mode` as given.
- **`update_dhcp_reservation` never activated a fixed IP, and `create_dhcp_reservation` failed for known clients**
  (enuno `cf712f0`/#95, `6257236`/#132): the controller ignores `fixed_ip` unless `use_fixedip` is set, and a
  POST for a MAC it has already seen answers `api.err.MacUsed`, which is the usual case. Update now sets
  `use_fixedip`; create looks the MAC up and merges into the existing record.
- **A firewall policy with a `WEB` matching target made every policy unreadable** (enuno `3ce10db`/#107): the
  enum lacked `WEB`.
- Not taken from upstream, on purpose: fleet mode (phases 0-7), Protect v7, Mobility/InnerSpace/Carrier Fabric,
  A2A, Cloud Connector, audit encryption, global dry-run and `/metrics`, and the HTTP-transport fixes
  (#157, #169, #177), none of which apply to a stdio, local-controller deployment.

### Fixed (fork-only, found by sweeping every tool against the controller)

- **Write tools, found by live reversible round trips against the UDM** (create, read back, change, read back,
  delete; 9 of 12 passed first time: firewall group, disabled port forward, DHCP reservation, voucher, RADIUS
  profile, disabled firewall policy, port profile, locate LED, hotspot package refused by the controller as
  documented). Fixed here:
  - `update_traffic_matching_list` sent the fetched record's `id` back in the PUT body and got
    `400 Unknown request body property '$.id'`; it now sends only `type`, `name`, `items`.
  - `update_radius_account` failed parsing the controller's empty PUT reply after the write had landed; it now
    reads the account back. The controller keeps only name, password, VLAN and tunnel attributes, so `note` and
    `enabled` are dropped; create and update now return `warnings: ["the controller did not store: ..."]`
    instead of model defaults presented as stored values (and `create_radius_account` never sent `enabled`).
  - `download_backup` always 404'd: the controller serves scheduled backups from `/dl/autobackup/<file>` and manual
    ones (the `trigger_backup` `download_url`) from `/dl/backup/<file>`, not `/data/backup/<file>` (kept as the last
    fallback). Live: the latest autobackup downloads at exactly its listed size (104000 bytes), mode `0600`;
    `output_path="../../tmp/x"` is written inside `UNIFI_BACKUP_DOWNLOAD_DIR` under its bare name and nothing
    escapes; four hostile `backup_filename` values are rejected.
  - `delete_backup` used a site-less route that answers `api.err.NoSiteContext` (HTTP 401, reported as an
    authentication failure); it now uses the site-scoped backup command like `list_backups`. **Not verified end
    to end:** the only file available to try it on was a manual export, which the command answers with 404, and
    scheduled backups were not touched.
- **`trigger_backup` leaves an export on the controller**: a network-only backup (10.7 MB here) is written to
  `/dl/backup/<version>.unf`, which `list_backups` does not show and `delete_backup` cannot remove. It is
  overwritten by the next export, the same file the UI's "Download backup" produces. One was left behind by
  the test run (`10.5.67.unf`).
- Not bugs: `start_spectrum_scan` needs an explicit `ap_mac` (the AP's radios go offline, so there is no
  all-APs default; the empty-value error is just terse).
- **`get_firewall_policy` answered "not found" for predefined policies** (81 of 127 here): the controller itself
  returns 404 on the detail route for their synthetic ids (`<24hex><24hex><index>`) although the list returns
  them. On a 404 the tool now looks the id up in the list. Live: "Allow All Traffic" is found.
- **`get_device_connections`/`get_port_mappings` rejected the legacy ObjectId** that `search_devices` and
  `list_devices_by_type` return as `id`. It is now mapped to a MAC through the legacy device list. Live: the
  ObjectId of a switch resolves to its topology node.
- **`get_site_statistics` counted only wireless bytes** (wired clients report `wired-tx_bytes`/`wired-rx_bytes`):
  same fallback as the per-network statistics. Live: 187 GB became 5.3 TB, in line with the per-network sums.
- Checked and not a bug: `list_port_profiles` returns `[]` because the controller's `rest/portconf` is empty for
  this API key.

### Fixed

- **`site_id` reached request paths unvalidated** (ported from enuno `cf9bace`/#155): the endpoint translation
  matches `^/ea/sites/([^/]+)/(.+)$`, so a `site_id` carrying `/`, `..`, `?` or `#` moved the capture boundary
  and sent the request to a different controller path than the tool name implies (for example a POST to a
  firewall-policies route from `create_radius_profile`). Every tool now calls `validate_site_id` first
  (`site_manager` and `connector` stay exempt, as upstream). `test_site_id_validation.py` checks this
  statically over all of `src/tools`. Live: `default/../../../v2/api/site/default/firewall-policies` and
  `default?x=1` are rejected with `Invalid site ID format` before any request is made; `default` still works.
  The merge dropped three hunks silently (imports in `qos.py` and `wans.py`, the `get_zone_statistics` stub);
  `ruff` and that test caught them. `get_zone_policy_matrix` does not exist in this fork, so its hunk was dropped.
- **`download_backup` could write any file the server could** (ported from enuno `64d5209`/#158): `output_path` was
  used as given, and `backup_filename` was put into the request path unvalidated. `backup_filename` must now be
  one plain path component and is URL-encoded; `download_backup` uses only the filename of `output_path` and
  writes it inside `UNIFI_BACKUP_DOWNLOAD_DIR` (default: the current directory) with `O_NOFOLLOW` and mode
  `0600`. **Breaking:** `output_path` is now a filename. Covered by unit tests only; the download itself was
  not run against the controller.
- **The topology had no device-to-device links, no uplinks and depth 0** (cherry-picked from enuno, in order:
  `d83cefa`/#105, `9557286`/#135, `83919bb`/#136): device uplinks, online state and hop depth are resolved,
  every host behind a switch port is reported, and `get_device_connections`/`get_port_mappings` resolve their
  device id instead of silently returning nothing. They accept the integration UUID (what the topology
  returns) or a MAC; the legacy ObjectId that `search_devices` returns is now a loud "not found" rather than an
  empty result. Live: connections 46 to 53 (7 device uplinks with ports and 1000 Mbps full duplex), `max_depth`
  0 to 3, device `state` 1 for the 7 online devices, `get_port_mappings` of the 8-port switch lists 7 ports with
  the neighbour on each, `get_device_connections` 8/1/12 items for the switch, AP and Nano HD.
- **`get_dpi_statistics` returned an empty result that looked like "no traffic"** (enuno `78c61e6`/#129): it
  reads `stat/sitedpi` and, when the controller reports no site DPI counters, says so in a `note` and points at
  `get_top_flows`/`get_flow_analytics`. Live: this controller (Network 10.5.67) reports none, so the result is
  still empty but now explained; no counters were gained.
- **Speed tests, spectrum and backups errored on every call** (cherry-picked from enuno, in this order):
  `2440987`/#127 speed-test history from the archive report; `1ebd932`/#128 spectrum data from the per-AP
  route (`stat/spectrum-scan/{ap_mac}`, the site-wide path never existed); `a2a15c3`/#140 speed-test status from
  the gateway device record; `77dfdbb`/#126 backups listed via the backup command and the schedule
  read from the `auto_backup` setting; `11cec2f`/#191 the schedule from `super_mgmt` on UniFi OS consoles.
  Live on this controller: `get_speed_test_history` (empty, no tests run), `get_speed_test_status` (`Idle`),
  `get_spectrum_scan` (both radios of the AP, no scan results yet), `list_spectrum_interference` (empty),
  `list_backups` (real autobackups) and `get_backup_schedule` (monthly cron) now succeed. Only reads were run;
  speed-test trigger, backup create/restore and the other write paths were not exercised.
  One typing fix on top: `_spectrum_scan_targets` returns `str(d["mac"])` so mypy 2.4 accepts it.
- **Per-network and per-WLAN statistics reported the site total for every row** (enuno `5547125`/#118): the
  VLAN match paired `None == None`, so every untagged client counted against every network. Matching is now by
  network id. Live: LAN 29 + IoT 11 + Infra 6 = the 46 clients, WLANs 18 + 10 = the 28 wireless clients.
- **Wired clients reported null/0 traffic** (enuno `a8a5584`/#119): reads the `wired-tx_bytes`/`wired-rx_bytes`
  keys wired clients actually report. Live: a wired client went from 0 to 6.5 GB tx.
- **`get_device_details` failed for every identifier** (ported by hand from enuno `8a771e0`/#183 and `7c8d52e`/#109):
  the integration UUID path failed model validation (legacy `Device` model on an integration reply), a legacy
  ObjectId (what `search_devices` returns) was never matched, and a MAC was rejected. It now accepts all three
  and returns the new `IntegrationDevice` model (`src/models/integration_api.py`, a subset of upstream's file).
  The firewall-policy enum relaxation from #183 was not taken: policy reads work here. Not taken either:
  `abf317e`/#189, which moves device search to the integration API for API-key access; the legacy route
  already accepts the key on this controller.
- **`list_wlans` returned WPA passphrases in cleartext** (enuno `3c96943`/#185): `x_passphrase`, `x_iapp_key`
  and private pre-shared key passwords are now `***REDACTED***` in `list_wlans`, `create_wlan` and `update_wlan`.
  A scan of every id-free `list_*`/`get_*`/`search_*` tool for secret-looking field names found no other leak.
- **Integration API paths rejected the short site name** (`'default' is not a valid 'siteId' value`,
  `400 api.request.argument-type-mismatch`). `UniFiClient._request` now rewrites a non-UUID site segment in
  local `/integration/v1/sites/{site}/...` paths to the site UUID (`_resolve_integration_site`, reusing
  `resolve_site_id` and its cache), so every tool that builds those paths by hand works with `site_id="default"`.
  Verified live: `list_pending_devices`, `list_wan_connections`, `list_site_to_site_vpns`, `list_vpn_servers`,
  `list_device_tags`, `list_radius_profiles`, `list_switch_stacks`, `list_lags` and `list_mclag_domains` now
  succeed with `default`; an unknown name raises a clear `site 'x' not found`.
- **Vouchers, hotspot packages and the guest portal called endpoints that do not exist** (404 on every
  controller). Cherry-picked from enuno/unifi-mcp-server; the list/get calls were verified live on this fork's
  controller (empty vouchers and packages, guest portal config returned), the create/update/delete paths were
  only exercised by the unit tests that came with the upstream commits:
  - `24e2d41` (#122): vouchers use `/v1/sites/{siteId}/hotspot/vouchers` with the documented shape.
    `create_vouchers` now takes the documented `name` and `timeLimitMinutes` (the old `duration`/`qos_*`
    parameters were never accepted by the controller); `bulk_delete_vouchers` refuses an empty filter.
  - `52827e9` (#123): hotspot packages use the classic `rest/hotspotpackage` surface; the bandwidth, quota and
    enabled parameters the controller ignored are removed.
  - `44d299b` (#130): `get_guest_portal_config`/`configure_guest_portal` read and write `setting/guest_access`,
    secrets (`x_*`) stripped; new `portal_enabled` switch.
  - The a2a playbook hunks of those commits were dropped (this fork has no a2a).
- **`list_wan_connections` padded its output with values the controller never sent** (`dns_servers: []`,
  `is_backup: false`, 20 null keys). Unreported fields now default to `None` and are omitted from the result
  (same as enuno `8130851`/#103, reimplemented because the fork already had the optional-fields half).

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
