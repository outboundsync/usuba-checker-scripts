# Contributing

Thanks for helping. This project is MIT-licensed; by contributing you agree your contribution is licensed under the same terms (sign-off with `git commit -s` is welcome, the Developer Certificate of Origin applies).

## Setup and tests
```sh
python3 -m pip install pytest
python3 -m pytest -q          # CPU only, no network, no model
python3 tools/scan_public.py  # must print "0 finding(s)" before you open a PR
```

## Adding a rule (Checker Scripts)
Add the rule to `functest/usuba/rules.py` (single source of truth), implement it in `functest/usuba/` with a test that has one failing and one passing example,
regenerate the standard (`cd functest && python3 -m usuba.rules > STANDARD.md`), and say which public plugin or thread motivated it.

## Never commit
- credentials of any kind, or strings shaped like them (tests must build fake tokens at runtime, not store them)
- private device data: home-directory paths, hostnames, hardware captures, run output from personal machines
  - exception, decided by Harris Kenny on 2026-10-16: the reference Dell's captures and images are **not** sensitive and are allowlisted (`functest/fixtures/hyprland-0.56.2/dell-capture/`, exempted in `tools/scan_public.py`). Do not add other device captures; ask first.
- answer keys, labels or the contents of the sealed holdout
- raw review text written by other people
- raw output of proprietary models (score tables are fine)
- third-party source code that has no MIT/Apache/ISC/BSD licence; reference it by URL + commit SHA instead
- model weights or datasets (use Hugging Face)
CI runs gitleaks and `tools/scan_public.py` on every push and pull request.

## Pull requests
Branch from `main`, keep PRs small, describe the evidence. Do not force-push shared branches.
