# Security Policy

## Supported Versions

Security updates are applied to the current version maintained on the `main` branch.

| Version | Supported |
|---|---|
| Current `main` branch | Yes |
| Latest tagged release | Yes |
| Older releases | No |

## Reporting a Vulnerability

Do not publicly disclose a suspected security vulnerability in a GitHub issue, discussion, pull request, or source-code comment.

Use GitHub's private **Report a vulnerability** function in the repository Security area when that option is available.

A vulnerability report should include:

- A concise description of the issue
- The affected file, module, dependency, or workflow
- Reproduction steps
- The potential security impact
- Relevant logs or screenshots with credentials removed
- A proposed mitigation, when available

If private vulnerability reporting is unavailable, create a public issue containing no sensitive technical details and request a private communication channel.

## Response Process

Reported vulnerabilities will be evaluated based on reproducibility, severity, exploitability, impact on data integrity or confidentiality, impact on model results or validation evidence, and available mitigating controls.

Confirmed vulnerabilities may result in:

- A corrective commit
- A dependency update
- A revised release
- A security advisory
- Additional automated tests
- Updated documentation
- A model-risk or data-quality finding

## Security-Sensitive Information

Do not commit or disclose:

- API keys
- Passwords
- Access tokens
- Authentication cookies
- Private keys
- Personal or confidential data
- Proprietary clearing-agency data
- Restricted market data
- Machine-specific credentials
- Unredacted system logs containing sensitive information

Local secrets should be stored in environment variables or an untracked `.env` file.

## Dependency Security

Contributors should review dependency changes carefully and avoid unnecessary packages.

Before submitting dependency changes, run:

```powershell
python -m pip check
python -m pytest -v
```

Dependency alerts and automated security updates should be reviewed before merging.

## Model and Data Integrity

For this repository, security also includes protection against changes that could silently alter validation conclusions.

Changes affecting model calculations, validation statistics, configuration files, evidence files, or reports should be reproducible, tested, documented, traceable through version control, and reviewed for unintended result changes.

Failed validation tests must not be hidden, deleted, or replaced without explanation.

## Disclaimer

This repository is an independent educational and portfolio implementation using public and synthetic data. It is not intended for production margining, regulatory compliance, trading, investment, or operational risk-management decisions.
