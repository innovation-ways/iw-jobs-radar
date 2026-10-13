# Security policy

Jobs Radar is a local-first, single-user application. Version 1 has **no authentication**: run it on
loopback (the default) or on a trusted network only, never on the public internet.

## Supported versions

Only the latest release on `main` receives security fixes.

## Reporting a vulnerability

Please do **not** open a public issue for a security problem.

- Use GitHub's private vulnerability reporting ("Report a vulnerability" under the Security tab), or
- email **info@innovation-ways.com** with the subject "Jobs Radar security".

Include what you found, how to reproduce it and the version or commit. We aim to acknowledge a report
within 5 working days and to tell you the outcome or a fix plan within 30 days. Reports of the
following are especially welcome: leaks of stored credentials or personal data, bypasses of the
outbound URL guard (SSRF), unsafe handling of uploaded CVs, and anything that exposes the API beyond
the configured bind address.
