# Release Process

This document describes the release process for the UniFi MCP Server project.

## Overview

The project uses automated releases via GitHub Actions with some manual steps for package registries.

## Release Workflow

### 1. Tag the Release

Create and push a version tag:

```bash
git tag -a v0.2.0 -m "Release v0.2.0"
git push origin v0.2.0
```

**Tag Format:**
- Use semantic versioning: `vMAJOR.MINOR.PATCH`
- Example: `v0.2.0`, `v1.0.0`, `v1.2.3`
- Always prefix with `v`

### 2. Automated GitHub Actions

Once you push the tag, GitHub Actions automatically:

1. **Runs full test suite** - Ensures all 990 tests pass
2. **Performs security scans** - CodeQL, Trivy, Bandit, Safety, OSV Scanner
3. **Builds multi-arch Docker images**:
   - `linux/amd64`
   - `linux/arm64`
   - `linux/arm/v7` (32-bit ARM)
   - `linux/arm64/v8`
4. **Pushes images to GitHub Container Registry**:
   - `ghcr.io/enuno/unifi-mcp-server:latest`
   - `ghcr.io/enuno/unifi-mcp-server:0.2.0`
   - `ghcr.io/enuno/unifi-mcp-server:0.2`
5. **Creates GitHub release**:
   - Generates release notes from commits
   - Attaches build artifacts
   - Tags the release
6. **Generates changelog** - Automatic changelog from conventional commits

**GitHub Actions Workflows:**
- `.github/workflows/ci.yml` - Test suite and quality checks
- `.github/workflows/security.yml` - Security scanning
- `.github/workflows/release.yml` - Release automation (triggered on tag push)
- `.github/workflows/docker-build.yml` - Multi-arch Docker builds

### 3. Manual Post-Release Steps

After the automated workflow completes, perform these manual steps:

#### 3.1 Publish to PyPI

**Prerequisites:**
- PyPI account with API token
- Project registered on PyPI
- Trusted publisher configured (optional)

**Steps:**

```bash
# Build Python package
python -m build

# Check the distribution
twine check dist/*

# Upload to PyPI (requires PyPI token)
twine upload dist/*

# Or upload to Test PyPI first
twine upload --repository testpypi dist/*
```

**Automated Publishing (Optional):**
- Configure PyPI trusted publisher in GitHub repository settings
- Add workflow to publish automatically on tag push

#### 3.2 Publish npm Metadata Package

The npm package is a metadata wrapper pointing to the Python package.

**Prerequisites:**
- npm account
- Logged in via `npm login`

**Steps:**

```bash
# Ensure package.json version matches release
cat package.json | grep version

# Publish to npm
npm publish --access public

# Verify publication
npm view unifi-mcp-server
```

**Package Contents:**
- `package.json` - Metadata and version
- `README.md` - Documentation
- `LICENSE` - Apache 2.0 license
- `server.json` - MCP registry manifest

#### 3.3 Submit to MCP Registry

Register the server with the Model Context Protocol registry.

**Prerequisites:**
- `mcp-publisher` CLI tool installed
- GitHub authentication (for `io.github.enuno` namespace)
- npm package published (required first)

**Installation:**

```bash
# macOS/Linux
brew install mcp-publisher

# Or download binary
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" | tar xz mcp-publisher
sudo mv mcp-publisher /usr/local/bin/
```

**Steps:**

```bash
# Authenticate with GitHub (required for io.github.enuno namespace)
mcp-publisher login github

# Publish to MCP registry
# Note: Requires npm package published first
mcp-publisher publish

# Verify registration
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.enuno/unifi-mcp-server"
```

**Registry Entry:**
- **Namespace**: `io.github.enuno`
- **Package**: `unifi-mcp-server`
- **Source**: npm package
- **Manifest**: `server.json` in npm package root

## Pre-Release Checklist

Before creating a release tag, ensure:

### Code Quality
- [ ] All tests passing locally (`pytest tests/unit/`)
- [ ] Coverage meets target (≥78%)
- [ ] No linting errors (`ruff check src/ tests/`)
- [ ] Code formatted (`black src/ tests/`)
- [ ] Type checking clean (`mypy src/`)
- [ ] Pre-commit hooks passing (`pre-commit run --all-files`)

### Security
- [ ] No security vulnerabilities (`bandit -r src/`)
- [ ] Dependency scan clean (`safety check`)
- [ ] Secrets detection clean (`detect-secrets scan`)
- [ ] Docker image scan clean (Trivy)

### Documentation
- [ ] `README.md` updated with new features
- [ ] `CHANGELOG.md` updated with release notes
- [ ] `API.md` updated with new tools/resources
- [ ] Version numbers updated:
  - `pyproject.toml`
  - `package.json`
  - `src/__init__.py` (if versioned)
  - `docs/conf.py` (if applicable)

### Testing
- [ ] Integration tests passing (if applicable)
- [ ] Docker build successful locally
- [ ] MCP Inspector working with new features
- [ ] Manual testing on real UniFi hardware

### Release Artifacts
- [ ] `VERIFICATION_REPORT.md` updated (for major releases)
- [ ] `RELEASE_COMPLETION_GUIDE.md` reviewed
- [ ] Example prompts updated in `docs/examples/`

## Post-Release Verification

After publishing, verify the release:

### Docker Images
```bash
# Pull latest image
docker pull ghcr.io/enuno/unifi-mcp-server:latest

# Verify version
docker run --rm ghcr.io/enuno/unifi-mcp-server:latest python -c "import src; print(src.__version__)"

# Test basic functionality
docker run -i --rm \
  -e UNIFI_API_KEY=test-key \
  -e UNIFI_API_TYPE=cloud \
  ghcr.io/enuno/unifi-mcp-server:latest
```

### PyPI Package
```bash
# Install from PyPI
pip install unifi-mcp-server==0.2.0

# Verify installation
python -c "import unifi_mcp_server; print(unifi_mcp_server.__version__)"
```

### npm Package
```bash
# Check npm package
npm view unifi-mcp-server

# Verify version
npm view unifi-mcp-server version
```

### MCP Registry
```bash
# Search registry
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=unifi-mcp-server"

# Get server details
curl "https://registry.modelcontextprotocol.io/v0.1/servers/io.github.enuno/unifi-mcp-server"
```

### GitHub Release
- [ ] Release notes accurate
- [ ] Changelog generated correctly
- [ ] Docker images tagged properly
- [ ] Release artifacts attached

## Rollback Procedures

If issues are discovered after release:

### 1. Delete Bad Tag (If Not Published)

```bash
# Delete local tag
git tag -d v0.2.0

# Delete remote tag (if not published)
git push --delete origin v0.2.0
```

### 2. Yank PyPI Package (If Published)

```bash
# Yank bad release (keeps it installed but hides from pip)
pip install twine
twine yank unifi-mcp-server -v 0.2.0 -r pypi
```

### 3. Unpublish npm Package (If Published)

```bash
# Unpublish version (within 72 hours)
npm unpublish unifi-mcp-server@0.2.0

# Or deprecate (after 72 hours)
npm deprecate unifi-mcp-server@0.2.0 "This version has been deprecated"
```

### 4. Delete Docker Images

```bash
# Delete from GitHub Container Registry
# (requires GitHub CLI and appropriate permissions)
gh api -X DELETE /user/packages/container/unifi-mcp-server/versions/VERSION_ID
```

### 5. Create Hotfix Release

1. Fix the issue on `main` branch
2. Create new patch version tag (e.g., `v0.2.1`)
3. Follow normal release process
4. Update release notes to mention hotfix

## Release Schedule

### Versioning Strategy

- **Major Releases (x.0.0)**: Breaking changes, major new features (e.g., v1.0.0 multi-application platform)
- **Minor Releases (0.x.0)**: New features, backward-compatible (e.g., v0.2.0 ZBF + Traffic Flows)
- **Patch Releases (0.0.x)**: Bug fixes, security patches (e.g., v0.2.1 bug fixes)

### Planned Releases

- **v0.2.0** (Q1 2025): Modern firewall & monitoring
- **v0.3.0** (Q2 2025): Policy automation & SD-WAN
- **v1.0.0** (H2 2025): Multi-application platform

### Release Cadence

- **Major/Minor**: Quarterly (when features complete)
- **Patch**: As needed for critical bugs
- **Security**: Immediate for CVEs

## Troubleshooting

### GitHub Actions Failing

1. Check workflow logs in GitHub Actions tab
2. Verify test suite passes locally
3. Ensure all secrets configured (PyPI token, etc.)
4. Check Docker build locally

### PyPI Upload Failing

1. Verify PyPI token is valid
2. Check package version not already published
3. Ensure `twine check dist/*` passes
4. Verify project name not taken

### npm Publish Failing

1. Check you're logged in (`npm whoami`)
2. Verify package.json version incremented
3. Ensure package name available
4. Check npm access permissions

### MCP Registry Submission Failing

1. Verify npm package published first
2. Check GitHub authentication (`mcp-publisher login github`)
3. Ensure `server.json` valid
4. Verify namespace ownership

## Resources

- **GitHub Releases**: https://github.com/enuno/unifi-mcp-server/releases
- **Docker Registry**: https://ghcr.io/enuno/unifi-mcp-server
- **PyPI Package**: https://pypi.org/project/unifi-mcp-server/
- **npm Package**: https://www.npmjs.com/package/unifi-mcp-server
- **MCP Registry**: Search for `io.github.enuno/unifi-mcp-server`

## Additional Documentation

- [RELEASE_COMPLETION_GUIDE.md](../RELEASE_COMPLETION_GUIDE.md) - Detailed release checklist
- [VERIFICATION_REPORT.md](../VERIFICATION_REPORT.md) - Quality verification for major releases
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution guidelines
- [CHANGELOG.md](../CHANGELOG.md) - Version history

---

**Last Updated**: 2026-01-25
**Maintained By**: Development Team
