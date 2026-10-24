# Contributing to BADIA AI

Thanks for helping make environmental decision-support tools more useful and transparent.

## Quick start

1. Fork this repository and create a branch for your change.
2. Follow the setup instructions in [README.md](README.md).
3. Keep changes small and focused. Add a test or reproducible check where possible.
4. Open a pull request explaining what changed and how you verified it.

## Good first contributions

- Improve Arabic and English accessibility, terminology, or mobile usability.
- Add tests for existing API responses and offline behavior.
- Improve documentation, data provenance, and source freshness indicators.
- Report reproducible bugs with steps to reproduce, expected behavior, and actual behavior.

## Scientific integrity

- The risk index is **not** a probability, validated drought diagnosis, or field observation.
- Do not describe bundled historical snapshots as live data.
- Do not silently overwrite model artifacts, baseline statistics, or provenance.
- State data sources, dates, licenses, and limitations when adding datasets.
- Do not include personal data or credentials in issues, commits, or example data.

## Checks

Pull requests run a lightweight GitHub Actions workflow which checks Python syntax and parses the committed JSON/GeoJSON. These checks do **not** establish predictive accuracy or replace the repository's functional tests.

## Licensing

Contributors retain responsibility for ensuring they have the right to share their contributions. Before reusing or redistributing any dataset, model, or third-party code, review its license and attribution requirements. A public GitHub repository is not automatically open-source licensed.
