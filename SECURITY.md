# Security Policy

## Scope

Stackwise Skills ships Markdown instructions and one Python validation script.
It runs no services and handles no user data, so the realistic risks are:

- A code sample in a skill that teaches an insecure pattern (hardcoded
  credentials, disabled TLS verification, SQL built by string concatenation,
  a permissive CORS or IAM policy).
- Text in a skill crafted to steer an agent into unsafe actions.
- A supply-chain issue in the GitHub Actions workflow.

## Reporting

Report suspected vulnerabilities privately through
[GitHub Security Advisories](https://github.com/Aarvion-AI/stackwise-skills/security/advisories/new),
or by email to **security@aarvion.ai**. Please do not open a public issue for a
security report.

Include the affected file and line, why the pattern is unsafe, and a suggested
correction. We aim to acknowledge within 5 working days.

An insecure code sample that is simply a mistake is fine to report as a normal
[issue](https://github.com/Aarvion-AI/stackwise-skills/issues) instead.

## Supported versions

Fixes land on `main` and ship in the next release. Older tags are not patched.
