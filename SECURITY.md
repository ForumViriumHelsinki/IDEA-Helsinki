# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability in this project, please report it through GitHub Security Advisories:

**https://github.com/ForumViriumHelsinki/IDEA-Helsinki/security/advisories/new**

Do not report security vulnerabilities through public GitHub issues, pull requests, or discussions.

## Response Timeline

- **Acknowledgment**: Within 48 hours of report submission
- **Assessment**: Initial severity assessment within 7 days
- **Fix timeline**: Depends on severity and complexity of the vulnerability

## Scope

The following are in scope for security reports:

- All code in this repository
- Docker images built from this repository
- Kubernetes configurations and manifests
- CI/CD pipelines and GitHub Actions workflows

## Out of Scope

- **Third-party dependencies**: Report vulnerabilities in upstream dependencies directly to those projects
- **Social engineering**: Attacks targeting people rather than software
- **Denial of Service (DoS)**: Volumetric or resource exhaustion attacks

## Supported Versions

Only the latest release on the `main` branch is supported with security updates. Older versions do not receive patches.

## Disclosure Policy

This project follows coordinated disclosure:

1. The vulnerability is reported privately via GitHub Security Advisories
2. The maintainers develop and test a fix
3. The fix is released
4. A public security advisory is published after the fix is available

Please allow reasonable time for a fix before any public disclosure.
