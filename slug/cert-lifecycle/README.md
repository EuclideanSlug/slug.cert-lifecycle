# Slug Certificate Lifecycle Catalogue

Catalogue files live here:

```text
slug/cert-lifecycle/certs/
```

`slug` is an example platform prefix. Replace it with the prefix used by your platform when adopting this repository.

Active catalogues use `*.yml`. Example templates use `*.yml.example`.

This directory-level README is intentionally short. The canonical documentation is:

- [Project overview](../../README.md)
- [Catalogue reference](../../docs/catalogue-reference.md)
- [Architecture](../../docs/architecture.md)
- [Operations runbook](../../docs/operations-runbook.md)
- [Deployment](../../docs/deployment.md)
- [Terraform](../../docs/terraform.md)

Quick validation:

```bash
python3 slug/cert-lifecycle/scripts/validate-catalogues.py
```
