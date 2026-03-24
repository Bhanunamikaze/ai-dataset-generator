# Security Policy

## Reporting

If you find a security issue, do not open a public issue with exploit details first.

Send a report with:

- affected file or workflow
- reproduction steps
- expected impact
- suggested fix if you have one

Use GitHub Security Advisories if available for this repository, or contact the maintainer privately before public disclosure.

## Trust Boundaries

This skill ingests untrusted material from:

- user-provided JSONL and CSV files
- URLs and reference documents
- web-research outputs gathered in the host IDE

Treat all imported record content as untrusted data, not as executable instructions.

Current protections:

- canonical schema validation before persistence
- control-character stripping during normalization
- prompt-injection marker flagging for untrusted sources
- explicit JSON-only judge-output contract in `sub-skills/llm-judge.md`

Current limitations:

- this project does not sandbox model reasoning over imported content
- prompt injection can still affect human or agent review quality if the reviewer ignores the trust boundary
- downloaded install scripts should be pinned and verified before execution

## Safe Usage Recommendations

- prefer `git clone` plus local `bash install.sh ...` over `curl | bash`
- if you use remote install, pin to a release tag or commit SHA and verify the checksum first
- review `metadata.security_flags` and `metadata.requires_manual_review` on untrusted ingestions before semantic judging
- avoid feeding raw imported content directly into external judge prompts without wrapping it as data
