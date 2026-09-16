# Security Policy

## Scope

Security-sensitive reports include sandbox escapes, unauthorized tool execution, credential exposure, prompt-to-host privilege escalation, and memory isolation failures.

## Reporting

Do not publish exploitable details in a public issue. Contact the repository maintainers privately through GitHub with a concise description, affected component, reproduction steps, and impact assessment.

## Security design principles

- Tool access is explicit and allow-listed.
- Filesystem access is rooted in an injected sandbox directory.
- Git integration in the baseline platform is read-only.
- Outbound HTTP can be restricted to explicit hosts.
- Secrets are never stored in repository configuration.
- Arbitrary code execution is not enabled by the core runtime.
