# Catalogue Reference

Certificate catalogues live in:

```text
slug/cert-lifecycle/certs/
```

`slug` is an example platform prefix. Replace it with the prefix that matches your platform before wiring catalogues, Jenkins jobs, Terraform variables, or Secrets Manager paths into a live environment.

File names use:

```text
PTx-<env>-certs.yml
```

Example templates may use the suffix `.yml.example`. Copy a template to `.yml` and replace all placeholders before first issuance.

Examples: `PT2-dev-certs.yml`, `PT2-preprod-certs.yml`, `PT2-prod-certs.yml`.

## Schema

Each file has a top-level `apps` list. Each app must include:

| Field | Notes |
| --- | --- |
| `name` | Globally unique enrolled app name. Must end with `-{deployment.account_name}`. |
| `common_name` | Common name requested from Vault. |
| `sans` | List of subject alternative names. Use `[]` when none. |
| `ttl` | Standard value is `2160h`. |
| `deployment.type` | `ec2` or `ecs`. |
| `deployment.account_id` | 12-digit AWS spoke account ID as a quoted string. |
| `deployment.account_name` | Account suffix, for example `devc`, `preprodc`, `prodc`. |
| `activation` | Future activation metadata. Present but not acted on in Phase 1. |
| `maintenance_window` | Future maintenance metadata. Present but not acted on in Phase 1. |

ECS apps must also include:

| Field | Notes |
| --- | --- |
| `deployment.cluster` | ECS cluster name. |
| `deployment.service` | ECS service name. |

## Examples

EC2:

```yaml
apps:
  - name: b2bi-preprodc
    common_name: b2bi.c0081-preprodc.local
    sans: []
    ttl: 2160h
    deployment:
      type: ec2
      account_id: '<account-id>'
      account_name: preprodc
    activation: maintenance-window
    maintenance_window: sun:02:00-04:00
```

ECS:

```yaml
apps:
  - name: datapower-high-preprodc
    common_name: dp-high.c0081-preprodc.local
    sans: []
    ttl: 2160h
    deployment:
      type: ecs
      account_id: '<account-id>'
      account_name: preprodc
      cluster: c0081-preprodc-DP-high
      service: c0081-preprodc-DP-high-service
    activation: rolling
    maintenance_window: mon-fri:22:00-06:00
```

## Naming

Use:

```text
{application}-{account_name}
```

Valid:

```yaml
name: b2bi-preprodc
deployment:
  account_name: preprodc
```

Invalid:

```yaml
name: b2bi-preprodc
deployment:
  account_name: devc
```

The validator checks duplicate app names across all catalogue files, not just within one file.

## Secret path

The secret is stored in the target spoke account under:

```text
/slug/certs/{name}
```

For `name: b2bi-preprodc`, the path is:

```text
/slug/certs/b2bi-preprodc
```

## Secret payload

Ansible writes structured JSON:

```json
{
  "certificate": "<leaf-certificate-pem>",
  "private_key": "<private-key-pem>",
  "ca_chain": "<ca-chain-pem>",
  "full_chain": "<full-chain-pem>",
  "expiry_epoch": "1780000000",
  "common_name": "b2bi.c0081-preprodc.local"
}
```

Do not print this payload in logs or tickets. It contains private key material.

## Add an app

1. Pick or create the correct `PTx-<env>-certs.yml` file. If a `.yml.example` template exists, copy it to `.yml` first.
2. Add an app entry using the schema above.
3. Replace `deployment.account_id` with the real 12-digit spoke account ID.
4. Confirm `name` ends with `-{deployment.account_name}`.
5. For ECS, include `deployment.cluster` and `deployment.service`.
6. Run:

   ```bash
   python3 slug/cert-lifecycle/scripts/validate-catalogues.py
   ```

7. Raise a pull request.
8. After merge, run Jenkins with `PRODUCT_TEAM`, `ENVIRONMENT`, and `APP_NAME`.

Committed `.yml.example` catalogues may contain placeholder account IDs. Active `.yml` catalogues must contain real 12-digit AWS account IDs.
