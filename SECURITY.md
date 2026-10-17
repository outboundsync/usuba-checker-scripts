# Security policy

## Reporting a vulnerability or a leaked secret
Please do **not** open a public issue. Email **harris@outboundsync.com** with the subject `usuba security`, or use GitHub's
private vulnerability reporting ("Security" tab, "Report a vulnerability") once it is enabled for this repository.
Include the file path and commit, what you found, and (for a leaked credential) which provider issued it. Never paste the secret itself.

We aim to acknowledge within 5 business days and to fix or remove the material within 14 days.

## In scope
- Credentials, tokens or private keys committed in any file or in history.
- Personal data (home paths, hostnames, e-mail addresses other than the maintainer's) that should not be public.
- Code that could execute untrusted plugin code outside the intended sandbox when running the Checker Scripts.

## Out of scope
- Findings the Checker Scripts report about third-party plugins (report those to the plugin's authors).
- Quality of model output.

## Rules for contributors
No secrets, no private device data, no raw output of proprietary models, no unlicensed third-party code. CI runs gitleaks on every push and PR.
