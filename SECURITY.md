# Security

Please report vulnerabilities privately through
[GitHub private vulnerability reporting](https://github.com/kwent/avers/security/advisories/new), not in public issues.

Secrets (gateway keys, `APP_TOKEN`) live in environment variables or git-ignored `.env*` files and must never be
committed; CI runs gitleaks and the repository has secret-scanning push protection enabled.
