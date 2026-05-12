# SCIP Certificate Lifecycle — Phase 1 Operator Runbook

**Audience:** DevOps engineers and application support teams responding to certificate alerts or performing certificate issuance and renewal.

**Scope:** Phase 1 — the SCIP cert-lifecycle automation that covers catalogue-driven issuance via Jenkins and expiry monitoring via Lambda.

**Related resources:**

| Resource | Location |
| --- | --- |
| Certificate catalogue | `scip/cert-lifecycle/certs/` in this repository |
| Jenkins issuance pipeline | `https://jenkins.<your-org>/job/scip-cert-issuance` |
| Lambda CloudWatch logs | `/aws/lambda/scip-cert-expiry-checker` (shared services account) |
| Bitbucket repository | `https://bitbucket.<your-org>/projects/SCIP/repos/slug.cert-lifecycle` |
| Confluence space | `https://confluence.<your-org>/display/SCIP/` |

---

## Contents

1. [Purpose and scope](#1-purpose-and-scope)
2. [Phase 1 capabilities](#2-phase-1-capabilities)
3. [Phase 1 exclusions](#3-phase-1-exclusions)
4. [Architecture overview](#4-architecture-overview)
5. [Certificate catalogue](#5-certificate-catalogue)
6. [Naming conventions](#6-naming-conventions)
7. [Secrets Manager path convention](#7-secrets-manager-path-convention)
8. [How to add a new application](#8-how-to-add-a-new-application)
9. [How to issue a certificate for one app](#9-how-to-issue-a-certificate-for-one-app)
10. [How to issue certificates for all apps in a catalogue](#10-how-to-issue-certificates-for-all-apps-in-a-catalogue)
11. [How to respond to a CERT RENEWAL NEEDED alert](#11-how-to-respond-to-a-cert-renewal-needed-alert)
12. [How to respond to a CERT P1 ACTION REQUIRED alert](#12-how-to-respond-to-a-cert-p1-action-required-alert)
13. [How to verify Secrets Manager has a new version](#13-how-to-verify-secrets-manager-has-a-new-version)
14. [How to coordinate app restart and reload](#14-how-to-coordinate-app-restart-and-reload)
15. [How to check Lambda logs](#15-how-to-check-lambda-logs)
16. [Troubleshooting](#16-troubleshooting)
17. [Security notes](#17-security-notes)
18. [Rollback using previous secret versions](#18-rollback-using-previous-secret-versions)
19. [Support and escalation](#19-support-and-escalation)
20. [Appendix](#20-appendix)

---

## 1. Purpose and scope

The SCIP certificate lifecycle automation provides a controlled, repeatable, and auditable process for issuing and monitoring TLS certificates for applications deployed across multiple AWS spoke accounts.

Without this automation, certificate renewal requires manual coordination across Vault, Ansible, AWS, and each application team. Phase 1 replaces that process with:

- A version-controlled YAML catalogue as the single source of truth for enrolled applications.
- A Jenkins pipeline that issues or renews a certificate by reading a catalogue entry and invoking the `universal-vault-cert-issuer` Ansible role.
- A Lambda that reads actual PEM expiry from Secrets Manager and routes SNS alerts before certificates expire.

**What this runbook covers:**

Everything an operator needs to issue certificates, respond to alerts, verify renewal outcomes, and troubleshoot failures — without reading the implementation code.

**What this runbook does not cover:**

Application-specific startup configuration, Vault PKI role management, AWS account onboarding, SNS subscription management, or EventBridge schedule management. Those are covered in the Confluence space.

---

## 2. Phase 1 capabilities

| Capability | Supported |
| --- | --- |
| Issue a certificate for a single enrolled app | Yes |
| Renew a certificate for a single enrolled app | Yes |
| Issue or renew all apps in a catalogue file in one pipeline run | Yes |
| Check certificate expiry by parsing the real PEM certificate | Yes |
| Send a renewal-required SNS notification (15–30 days remaining) | Yes |
| Send a P1 SNS notification (≤14 days remaining, including expired) | Yes |
| Roll back to a previous certificate version via Secrets Manager | Yes (manual, see section 18) |

---

## 3. Phase 1 exclusions

The following are **not** available in Phase 1. Do not expect, attempt, or implement them as part of cert-lifecycle automation:

- Automatic application restart or reload after certificate renewal
- Automatic triggering of Jenkins by the Lambda (the Lambda alerts; a human runs Jenkins)
- Live application endpoint certificate checking
- Detection of whether a running application has loaded the renewed certificate
- Certificate format conversion (JKS, KDB, PKCS12)
- Parallel bulk renewal (all renewals are sequential)
- Alert deduplication (the Lambda will re-alert on every scheduled run until the certificate is renewed)

---

## 4. Architecture overview

```
Bitbucket
  └── scip/cert-lifecycle/certs/PTx-<env>-certs.yml
        │
        ├── read at pipeline start by Jenkins
        └── read at each Lambda invocation via Bitbucket API

Jenkins cert-issuance pipeline
  └── Checks out repository
  └── Reads selected catalogue file (PRODUCT_TEAM + ENVIRONMENT)
  └── Filters by APP_NAME (optional)
  └── Calls issueCertificate(app) from scip-platform-lib
        │
        ▼
scip-platform-lib: issueCertificate(app)
  └── Validates app fields
  └── Assumes jagent-ec2-role in spoke account (via withAWS)
  └── Writes a temporary non-secret Ansible vars file
  └── Runs ansible-playbook universal-vault-cert-issuer
  └── Deletes the vars file
        │
        ▼
Ansible role: universal-vault-cert-issuer
  └── Issues PEM certificate from Vault
  └── Verifies current AWS account matches expected account_id
  └── Writes structured JSON to spoke account Secrets Manager
        │
        ▼
Spoke account: AWS Secrets Manager
  └── /scip/certs/{app_name}
        │
        ├── read by application at startup / container init
        └── read by expiry checker Lambda

Shared services account: expiry checker Lambda (EventBridge scheduled)
  └── Reads Bitbucket token from shared-account Secrets Manager
  └── Fetches catalogue YAMLs from Bitbucket API
  └── For each enrolled app:
        └── Assumes CertLifecycleRole in spoke account
        └── Reads /scip/certs/{app_name}
        └── Parses PEM expiry with Python cryptography library
        └── Routes: log-only / renewal SNS / P1 SNS
```

**Key IAM roles:**

| Role | Account | Purpose |
| --- | --- | --- |
| `jagent-ec2-role` | Spoke account | Assumed by Jenkins to write certificates to Secrets Manager |
| `CertLifecycleRole` | Spoke account | Assumed by the Lambda to read certificates from Secrets Manager |
| Lambda execution role | Shared services account | Allows Lambda to read Bitbucket token, assume spoke roles, publish SNS |

**SNS topics (shared services account):**

| Topic | Trigger condition |
| --- | --- |
| `scip-cert-renewal` | 15–30 days remaining |
| `scip-cert-p1-alerts` | ≤14 days remaining, or expired |

---

## 5. Certificate catalogue

### 5.1 Location

All catalogue files live under:

```
scip/cert-lifecycle/certs/
```

### 5.2 File naming

```
PTx-<env>-certs.yml
```

Where `PTx` is the product team identifier (`PT2`, `PT3`, `PT5`, …) and `env` is one of `dev`, `test`, `preprod`, `prod`.

Examples:

```
PT2-dev-certs.yml
PT2-preprod-certs.yml
PT2-prod-certs.yml
PT5-preprod-certs.yml
```

### 5.3 Schema

Each file contains a top-level `apps` list. Every item represents one enrolled application.

**Required fields for all deployment types:**

| Field | Description |
| --- | --- |
| `name` | Globally unique enrolled app name. Must follow `{application}-{account_name}`. |
| `common_name` | Certificate common name issued from Vault. |
| `sans` | List of subject alternative names. Use `[]` if none. |
| `ttl` | Certificate TTL. Standard value is `2160h` (90 days). |
| `deployment.type` | `ec2` or `ecs`. |
| `deployment.account_id` | AWS spoke account ID as a quoted string. |
| `deployment.account_name` | Account suffix, e.g. `devc`, `preprodc`, `prodc`. |
| `activation` | Phase 2 field. Required in Phase 1 but not acted on. |
| `maintenance_window` | Phase 2 field. Required in Phase 1 but not acted on. |

**Additional required fields for ECS entries:**

| Field | Description |
| --- | --- |
| `deployment.cluster` | ECS cluster name. |
| `deployment.service` | ECS service name. |

### 5.4 Secret payload format

After a successful issuance, the Secrets Manager secret contains:

```json
{
  "certificate": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----",
  "ca_chain": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
  "full_chain": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
  "expiry_epoch": "1780000000",
  "common_name": "b2bi.c0081-preprodc.local"
}
```

> **Important:** `expiry_epoch` is for human reference only. The Lambda parses expiry from the actual PEM certificate — do not rely on `expiry_epoch` for alerting decisions.

---

## 6. Naming conventions

### 6.1 Application name

The `name` field must follow:

```
{application}-{account_name}
```

Examples:

| Application | Account name | Correct enrolled name |
| --- | --- | --- |
| b2bi | devc | `b2bi-devc` |
| b2bi | preprodc | `b2bi-preprodc` |
| datapower-high | preprodc | `datapower-high-preprodc` |
| ibm-b2bi | prodc | `ibm-b2bi-prodc` |

The `deployment.account_name` must match the suffix after the last `-` in `name`. The pipeline and Ansible role both enforce this.

### 6.2 Jenkins `APP_NAME` parameter

The `APP_NAME` pipeline parameter must be the full enrolled name from the `name` field — not the base application name.

Correct: `b2bi-preprodc`

Incorrect: `b2bi`

---

## 7. Secrets Manager path convention

Each certificate is stored in the **spoke account** Secrets Manager under:

```
/scip/certs/{name}
```

Where `{name}` is the `name` field from the catalogue entry.

| Catalogue `name` | Spoke account secret path |
| --- | --- |
| `b2bi-devc` | `/scip/certs/b2bi-devc` |
| `b2bi-preprodc` | `/scip/certs/b2bi-preprodc` |
| `datapower-high-preprodc` | `/scip/certs/datapower-high-preprodc` |
| `ibm-b2bi-prodc` | `/scip/certs/ibm-b2bi-prodc` |

> **Never** append the account name a second time. `/scip/certs/b2bi-preprodc-preprodc` is wrong.

---

## 8. How to add a new application

Raise a pull request with these changes. The PR must be reviewed and merged before the certificate can be issued.

**Step 1 — Identify the correct catalogue file.**

Find or create `scip/cert-lifecycle/certs/PTx-<env>-certs.yml` for the relevant product team and environment.

**Step 2 — Confirm the AWS account ID for the spoke account.**

Obtain the 12-digit AWS account ID for the target spoke account. This is not a placeholder — it must be the real account ID.

**Step 3 — Choose the enrolled app name.**

Follow the naming convention: `{application}-{account_name}`. Confirm the name is not already used anywhere in the repository.

To check for duplicates:

```bash
grep -r "name:" scip/cert-lifecycle/certs/ | grep -v "account_name\|common_name\|cluster\|service"
```

Or run the catalogue validator:

```bash
python3 scip/cert-lifecycle/scripts/validate-catalogues.py
```

**Step 4 — Add the entry to the catalogue file.**

For an EC2 application:

```yaml
  - name: myapp-preprodc
    common_name: myapp.c0081-preprodc.local
    sans: []
    ttl: 2160h
    deployment:
      type: ec2
      account_id: '<account-id>'
      account_name: preprodc
    activation: maintenance-window
    maintenance_window: sun:02:00-04:00
```

For an ECS application:

```yaml
  - name: myapp-preprodc
    common_name: myapp.c0081-preprodc.local
    sans: []
    ttl: 2160h
    deployment:
      type: ecs
      account_id: '<account-id>'
      account_name: preprodc
      cluster: c0081-preprodc-myapp
      service: c0081-preprodc-myapp-service
    activation: rolling
    maintenance_window: mon-fri:22:00-06:00
```

Replace `<account-id>` with the real 12-digit AWS account ID.

**Step 5 — Validate the catalogue.**

```bash
python3 scip/cert-lifecycle/scripts/validate-catalogues.py
```

Fix any errors before raising the PR.

**Step 6 — Raise a pull request.**

The PR must be reviewed by at least one other team member before merge.

**Step 7 — Confirm IAM prerequisites.**

Before running the issuance pipeline, confirm:

- `jagent-ec2-role` exists in the spoke account with the policy from `scip/cert-lifecycle/iam/spoke-account-jagent-policy.json`.
- `CertLifecycleRole` exists in the spoke account with the policy from `scip/cert-lifecycle/iam/spoke-account-certlifecycle-role-policy.json` and trust policy from `scip/cert-lifecycle/iam/spoke-account-certlifecycle-role-trust-policy.json`.
- The Lambda execution role's `AssumeSpokeCertLifecycleRoles` statement includes the new spoke account's ARN.

**Step 8 — Issue the first certificate.**

Follow section 9.

---

## 9. How to issue a certificate for one app

Use this procedure for first-time issuance or targeted renewal of a single application.

**Step 1 — Open the Jenkins issuance pipeline.**

Navigate to: `https://jenkins.<your-org>/job/scip-cert-issuance`

**Step 2 — Click "Build with Parameters".**

**Step 3 — Select parameters.**

| Parameter | Value |
| --- | --- |
| `PRODUCT_TEAM` | The product team prefix, e.g. `PT2` |
| `ENVIRONMENT` | The environment, e.g. `preprod` |
| `APP_NAME` | The full enrolled app name from the catalogue, e.g. `b2bi-preprodc` |

The pipeline reads the catalogue file:

```
scip/cert-lifecycle/certs/{PRODUCT_TEAM}-{ENVIRONMENT}-certs.yml
```

and finds the entry whose `name` matches `APP_NAME`.

**Step 4 — Run the pipeline.**

Click "Build". Monitor the console output.

**Step 5 — Confirm success.**

The pipeline console will print:

```
issueCertificate: app=b2bi-preprodc account=preprodc (<account-id>)
```

and end with a green build status.

**Step 6 — Verify the secret.**

See section 13 to confirm a new `AWSCURRENT` version exists in Secrets Manager.

**Step 7 — Coordinate application reload if needed.**

See section 14.

---

## 10. How to issue certificates for all apps in a catalogue

Use this procedure to bulk-issue or bulk-renew all applications in a single catalogue file. Apps are processed sequentially. A failure on one app stops the pipeline.

**Step 1 — Open the Jenkins issuance pipeline.**

Navigate to: `https://jenkins.<your-org>/job/scip-cert-issuance`

**Step 2 — Click "Build with Parameters".**

**Step 3 — Select parameters.**

| Parameter | Value |
| --- | --- |
| `PRODUCT_TEAM` | The product team prefix, e.g. `PT2` |
| `ENVIRONMENT` | The environment, e.g. `preprod` |
| `APP_NAME` | Leave **empty** |

**Step 4 — Run the pipeline.**

Click "Build". The pipeline will process all entries in `PT2-preprod-certs.yml` one by one.

**Step 5 — Monitor the console output.**

The pipeline prints progress for each app:

```
Processing app 1 of 2: b2bi-preprodc
Processing app 2 of 2: datapower-high-preprodc
```

**Step 6 — On failure, note the failed app name.**

The error message includes the `app.name` that failed. Fix the issue (see section 16) and re-run with `APP_NAME` set to just that app.

---

## 11. How to respond to a CERT RENEWAL NEEDED alert

A `[CERT RENEWAL NEEDED]` email or SNS notification means a certificate has 15–30 days remaining. This is the standard renewal window. Act within the current working week.

**Step 1 — Read the alert.**

The alert contains:

```
Application:         b2bi-preprodc
Account name:        preprodc
Account ID:          <account-id>
Current expiry date: 2026-06-15T12:00:00Z
Days remaining:      22

Jenkins renewal job: scip-cert-issuance
APP_NAME parameter:  b2bi-preprodc
```

**Step 2 — Open the Jenkins pipeline.**

Navigate to: `https://jenkins.<your-org>/job/scip-cert-issuance`

**Step 3 — Build with parameters.**

| Parameter | Value from alert |
| --- | --- |
| `PRODUCT_TEAM` | Identify from the app name suffix or catalogue file (e.g. `PT2`) |
| `ENVIRONMENT` | Identify from the account name (e.g. `preprodc` → `preprod`) |
| `APP_NAME` | Copy exactly from the alert: `b2bi-preprodc` |

> If you are unsure which `PRODUCT_TEAM` the app belongs to, search the catalogue files:
> ```bash
> grep -rl "name: b2bi-preprodc" scip/cert-lifecycle/certs/
> ```
> The filename tells you the product team and environment.

**Step 4 — Run the pipeline and confirm success.**

**Step 5 — Verify the new certificate version.**

See section 13.

**Step 6 — Coordinate application reload if needed.**

See section 14.

**Step 7 — Confirm the Lambda no longer alerts.**

The Lambda runs on a daily schedule. After the next run, the app should log as `ok` if more than 30 days remain on the new certificate. If you continue to receive alerts, the certificate may not have been renewed correctly — see section 13 to verify.

---

## 12. How to respond to a CERT P1 ACTION REQUIRED alert

A `[CERT P1 - ACTION REQUIRED]` notification means a certificate has 14 days or fewer remaining, or has already expired. **Act immediately.**

**Step 1 — Read the alert.**

The alert subject indicates the urgency:

- `expires in N days` — the certificate is still valid but critically close
- `certificate expired N days ago` — the certificate is already expired

The body contains the application name, account, expiry date, days remaining, Jenkins job name, and `APP_NAME` value.

**Step 2 — Open the Jenkins pipeline immediately.**

Navigate to: `https://jenkins.<your-org>/job/scip-cert-issuance`

**Step 3 — Build with parameters.**

| Parameter | Value from alert |
| --- | --- |
| `PRODUCT_TEAM` | Identify from catalogue (search as in section 11 step 3) |
| `ENVIRONMENT` | Identify from account name |
| `APP_NAME` | Copy exactly from the alert |

**Step 4 — Monitor the pipeline carefully.**

Check the console output for any errors. If the pipeline fails, go to section 16 for troubleshooting.

**Step 5 — Verify the new certificate in Secrets Manager.**

See section 13. Confirm `AWSCURRENT` exists and the new expiry date is correct.

**Step 6 — Coordinate application restart/reload immediately.**

For expired or near-expired certificates, coordinate with the application owner to restart or reload the application so it picks up the new certificate. See section 14.

**Step 7 — Confirm the certificate is in use.**

Ask the application owner to confirm the application is serving the renewed certificate. Phase 1 does not check this automatically.

**Step 8 — Escalate if issuance fails.**

If Jenkins fails and you cannot resolve the issue within 30 minutes, escalate to the SCIP platform team. See section 19.

---

## 13. How to verify Secrets Manager has a new version

After a certificate issuance or renewal, confirm the secret has been updated.

### Using the AWS console

1. Log in to the **spoke account** AWS console (the account in the alert, not the shared services account).
2. Navigate to **AWS Secrets Manager**.
3. Search for the secret path, e.g. `/scip/certs/b2bi-preprodc`.
4. Open the secret.
5. Under **Secret value**, click **Retrieve secret value**. The console shows the `common_name` and `expiry_epoch` fields (not the private key, which is masked in the console).
6. Under **Versions**, confirm a new version with label `AWSCURRENT` exists. The previous version will be labelled `AWSPREVIOUS`.

> The console does not show the full private key in plain text for customer-managed KMS encrypted secrets. This is expected.

### Using the AWS CLI

Run this in the **spoke account**:

```bash
aws secretsmanager describe-secret \
  --secret-id /scip/certs/b2bi-preprodc \
  --region eu-west-2 \
  --query 'VersionIdsToStages'
```

Expected output shows `AWSCURRENT` on the most recent version ID:

```json
{
  "abc12345-...": ["AWSCURRENT"],
  "def67890-...": ["AWSPREVIOUS"]
}
```

To confirm the new certificate's expiry without printing the private key:

```bash
aws secretsmanager get-secret-value \
  --secret-id /scip/certs/b2bi-preprodc \
  --region eu-west-2 \
  --query 'SecretString' \
  --output text | python3 -c "
import json, sys
from cryptography import x509
d = json.load(sys.stdin)
cert = x509.load_pem_x509_certificate(d['certificate'].encode())
print('Expiry:', cert.not_valid_after_utc.isoformat())
"
```

> This command prints only the expiry date. It does not print the private key or full secret payload.

---

## 14. How to coordinate app restart and reload

Phase 1 does not restart or reload applications automatically. After renewing a certificate, you must determine whether the application will pick it up automatically or requires a manual action.

**Step 1 — Identify the deployment type.**

Check the catalogue entry:

- `type: ec2` — the application reads the certificate at startup from Secrets Manager or a local path. It likely requires a restart or a certificate refresh.
- `type: ecs` — the container reads the certificate at container startup. A new task deployment or service update is typically required.

**Step 2 — Contact the application owner.**

Reach out to the team responsible for the application. Provide:

- The application name: e.g. `b2bi-preprodc`
- The secret path: e.g. `/scip/certs/b2bi-preprodc` in the `preprodc` spoke account
- The new expiry date (from section 13)

Ask them to confirm how their application reads the certificate and what action is needed.

**Step 3 — For EC2 applications.**

Typical actions (owned by the application team, not the SCIP platform team):

- Restart the application service
- Trigger a certificate refresh if the application has a reload endpoint
- Re-run the application startup script that reads from Secrets Manager

**Step 4 — For ECS applications.**

Typical actions (owned by the application team):

- Force a new deployment: `aws ecs update-service --cluster <cluster> --service <service> --force-new-deployment`
- Or trigger the standard application deployment process

**Step 5 — Confirm with the application owner.**

Ask the application owner to confirm the application is operating correctly on the new certificate. Phase 1 does not verify this automatically.

---

## 15. How to check Lambda logs

The expiry checker Lambda runs on a daily EventBridge schedule. Its logs are in CloudWatch in the **shared services account**.

### Find the log group

Log group name: `/aws/lambda/scip-cert-expiry-checker`

(Confirm the exact Lambda function name in the Lambda console if this differs.)

### Using the AWS console

1. Log in to the **shared services account** AWS console.
2. Navigate to **CloudWatch → Log groups**.
3. Search for `/aws/lambda/scip-cert-expiry-checker`.
4. Open the most recent log stream to see the latest run.

### Using the AWS CLI

List recent log streams:

```bash
aws logs describe-log-streams \
  --log-group-name /aws/lambda/scip-cert-expiry-checker \
  --region eu-west-2 \
  --order-by LastEventTime \
  --descending \
  --max-items 5
```

Read the most recent stream:

```bash
aws logs get-log-events \
  --log-group-name /aws/lambda/scip-cert-expiry-checker \
  --log-stream-name '<most-recent-stream-name>' \
  --region eu-west-2 \
  --output text
```

### What to look for

**Healthy apps** log as:

```json
{"status": "ok", "app_name": "b2bi-preprodc", "account_name": "preprodc", "days_left": 45, "expiry_date": "2026-06-30T12:00:00Z"}
```

**Renewal-needed apps** log as:

```json
{"status": "renewal_needed", "app_name": "b2bi-preprodc", "account_name": "preprodc", "days_left": 22, "expiry_date": "2026-06-03T12:00:00Z"}
```

**P1 apps** log as:

```json
{"status": "p1_action_required", "app_name": "b2bi-preprodc", "account_name": "preprodc", "days_left": 6, "expiry_date": "2026-05-18T12:00:00Z"}
```

**Errors** log as:

```json
{"status": "error", "app_name": "b2bi-preprodc", "error": "<description of error, without secret content>"}
```

**Run summary** (at the end of every invocation):

```json
{"summary": {"checked": 4, "ok": 2, "renewal_needed": 1, "p1_action_required": 0, "errors": 1}}
```

> The Lambda never logs private keys, PEM certificate bodies, Bitbucket tokens, AWS credentials, or full secret payloads. If you see anything like `-----BEGIN RSA PRIVATE KEY-----` or `SecretString` in the logs, raise a security incident immediately.

---

## 16. Troubleshooting

### 16.1 App not found in catalogue

**Symptom:** Pipeline error:

```
APP_NAME 'b2bi-preprod' not found in PT2-preprod-certs.yml.
Available apps: b2bi-preprodc, datapower-high-preprodc
```

**Cause:** The `APP_NAME` parameter does not exactly match any `name` field in the selected catalogue.

**Fix:**

- Check the exact spelling of the enrolled name in the catalogue file:
  ```bash
  grep "name:" scip/cert-lifecycle/certs/PT2-preprod-certs.yml
  ```
- Confirm you are selecting the correct `PRODUCT_TEAM` and `ENVIRONMENT` parameters.
- The `APP_NAME` must be the full enrolled name including the account suffix, e.g. `b2bi-preprodc` not `b2bi`.

---

### 16.2 Wrong account ID in catalogue

**Symptom:** The Ansible role fails with:

```
AWS account mismatch: current account 111122223333 does not match expected account_id 000000000000
```

**Cause:** The `deployment.account_id` in the catalogue is still the placeholder `000000000000` or has an incorrect value.

**Fix:**

1. Identify the correct 12-digit AWS account ID for the spoke account.
2. Update the catalogue entry's `deployment.account_id` with the real value (quoted string).
3. Run the validator: `python3 scip/cert-lifecycle/scripts/validate-catalogues.py`
4. Raise a PR, merge, and re-run the pipeline.

---

### 16.3 STS assume-role failure

**Symptom:** Pipeline fails with:

```
An error occurred (AccessDenied) when calling the AssumeRole operation:
User: arn:aws:iam::<shared-account-id>:role/jagent-ec2-instance-profile
is not authorized to assume role: arn:aws:iam::<spoke-account-id>:role/jagent-ec2-role
```

**Cause:** Either `jagent-ec2-role` does not exist in the spoke account, or its trust policy does not include the Jenkins agent's IAM role as a trusted principal.

**Fix:**

1. Confirm `jagent-ec2-role` exists in the spoke account.
2. Check the role's trust policy. It must allow the Jenkins agent's IAM identity to assume it. See `scip/cert-lifecycle/iam/spoke-account-jagent-role-trust-policy.json` for the required format.
3. If the role or trust policy is missing, raise an infrastructure ticket with the platform team to create or update it.
4. Re-run the pipeline after the role is corrected.

---

### 16.4 Secrets Manager AccessDenied during issuance

**Symptom:** Ansible fails with:

```
An error occurred (AccessDenied) when calling the CreateSecret or PutSecretValue operation
```

**Cause:** `jagent-ec2-role` in the spoke account is missing the required Secrets Manager permissions.

**Fix:**

1. Review the permissions on `jagent-ec2-role` in the spoke account.
2. The role must allow `secretsmanager:CreateSecret`, `secretsmanager:DescribeSecret`, `secretsmanager:PutSecretValue`, and `secretsmanager:TagResource` on the resource `arn:aws:secretsmanager:eu-west-2:<account-id>:secret:/scip/certs/*`. See `scip/cert-lifecycle/iam/spoke-account-jagent-policy.json`.
3. If the permissions are missing, raise an infrastructure ticket to update the role policy.

---

### 16.5 KMS decrypt failure during Lambda expiry check

**Symptom:** Lambda log error:

```json
{"status": "error", "app_name": "b2bi-preprodc", "error": "AccessDeniedException: ... kms:Decrypt ..."}
```

**Cause:** The certificate secret in the spoke account is encrypted with a customer-managed KMS key. `CertLifecycleRole` does not have permission to decrypt it.

**Fix:**

1. Identify the KMS key used to encrypt `/scip/certs/{app_name}` in the spoke account.
2. Apply the KMS addon policy to `CertLifecycleRole`. See `scip/cert-lifecycle/iam/spoke-account-certlifecycle-role-kms-addon.json`.
3. Replace `<spoke-account-id>` and `<kms-key-id>` with the correct values and attach the statement to the role.
4. Re-trigger or wait for the next Lambda schedule run.

---

### 16.6 Secret not found during Lambda expiry check

**Symptom:** Lambda log error:

```json
{"status": "error", "app_name": "b2bi-preprodc", "error": "ResourceNotFoundException: Secrets Manager can't find the specified secret."}
```

**Cause:** The certificate has not yet been issued for this application. The secret `/scip/certs/b2bi-preprodc` does not exist in the spoke account.

**Fix:**

Issue the certificate first using the Jenkins pipeline (see section 9). The Lambda will pick it up on the next scheduled run once the secret exists.

---

### 16.7 Invalid PEM during Lambda expiry check

**Symptom:** Lambda log error:

```json
{"status": "error", "app_name": "b2bi-preprodc", "error": "ValueError: Unable to load PEM certificate"}
```

**Cause:** The `certificate` field in the Secrets Manager secret is corrupt, truncated, or not a valid PEM certificate.

**Fix:**

1. Check when the secret was last updated (see section 13).
2. Re-issue the certificate using the Jenkins pipeline (section 9). This will write a fresh, valid certificate.
3. If the re-issue also fails, check the Vault PKI endpoint and the Ansible role output in Jenkins for errors.

---

### 16.8 Bitbucket token failure

**Symptom:** Lambda log error at the start of a run:

```
Failed to retrieve Bitbucket token from Secrets Manager: <error>
```

or HTTP errors when fetching catalogue URLs:

```json
{"status": "error", "message": "Failed to fetch catalogue", "url": "...", "error": "401 Client Error: Unauthorized"}
```

**Cause:** Either the Bitbucket token secret does not exist in the shared services account Secrets Manager, or the token has expired or been revoked.

**Fix:**

1. Confirm the secret exists:
   ```bash
   aws secretsmanager describe-secret \
     --secret-id /scip/cert-lifecycle/bitbucket-token \
     --region eu-west-2
   ```
2. If missing, create it with the format `{"token": "<bitbucket-api-token>"}`.
3. If the token has expired, generate a new Bitbucket API token and update the secret:
   ```bash
   aws secretsmanager put-secret-value \
     --secret-id /scip/cert-lifecycle/bitbucket-token \
     --secret-string '{"token":"<new-token>"}' \
     --region eu-west-2
   ```
4. Wait for the next Lambda scheduled run or invoke the Lambda manually from the console.

---

### 16.9 SNS publish failure

**Symptom:** Lambda log error:

```json
{"status": "error", "app_name": "b2bi-preprodc", "error": "AuthorizationErrorException: ... sns:Publish ..."}
```

**Cause:** The Lambda execution role does not have `sns:Publish` permission on the alert topic, or the topic ARN in the Lambda environment variables is incorrect.

**Fix:**

1. Confirm the SNS topic ARNs in the Lambda environment variables (`CERT_RENEWAL_TOPIC_ARN` and `CERT_P1_ALERT_TOPIC_ARN`) match the actual SNS topic ARNs in the shared services account.
2. Confirm the Lambda execution role policy includes `sns:Publish` on those topic ARNs. See `scip/cert-lifecycle/iam/shared-account-lambda-execution-policy.json`.
3. Update the Lambda environment variable or the IAM policy as needed.

---

### 16.10 Jenkins or Ansible failure

**Symptom:** Jenkins build fails with an Ansible error such as:

```
TASK [Validate required variables] *****
fatal: [localhost]: FAILED! => {"msg": "Missing required variable..."}
```

or:

```
TASK [Issue certificate from Vault PKI] *****
fatal: [localhost]: FAILED! => ...
```

**Cause:** Common causes:

| Ansible task | Likely cause |
| --- | --- |
| `Validate required variables` | A required field is missing from the catalogue entry |
| `Validate app_name ends with account_name` | The `name` field does not end with `-{account_name}` |
| `Validate deployment_type` | `deployment.type` is not `ec2` or `ecs` |
| `Validate secret_name matches expected path` | Secret name derivation is inconsistent — contact the platform team |
| `Issue certificate from Vault PKI` | Vault unreachable, invalid PKI role, or insufficient Vault permissions |
| `Get current AWS caller identity` | Jenkins assumed the wrong account or assume-role failed silently |
| `Validate AWS account matches expected account_id` | Wrong account ID in catalogue — see section 16.2 |
| `Write certificate to Secrets Manager` | Missing IAM permissions — see section 16.4 |

**General approach:**

1. Read the full Jenkins console output from top to bottom. The first `fatal` entry is the actual root cause.
2. Ansible tasks that handle secret material use `no_log: true`, so those specific task outputs are hidden. Error messages from these tasks are still shown.
3. If the Vault issuance task fails, confirm Vault is reachable from the Jenkins agent and that the PKI role allows the requested common name and SANs.
4. If you cannot determine the cause from the console output, collect the build URL and escalate to the SCIP platform team.

---

## 17. Security notes

**What is safe to share:**

- Application name (`app_name`)
- Account name (`account_name`)
- Account ID (`account_id`)
- Secret path (`/scip/certs/...`)
- Expiry date
- Days remaining
- Jenkins build URL and console output (after confirming no secret material is present)

**What must never be shared or logged:**

- Private keys (`private_key` field)
- Full certificate PEM (`certificate`, `ca_chain`, `full_chain` fields)
- Full Secrets Manager `SecretString` payloads
- Vault tokens
- Bitbucket API tokens
- AWS temporary credentials (access key, secret key, session token from `sts:AssumeRole`)

**If you see secret material in logs or console output:**

Treat it as a security incident. Do not share the log. Contact the security team and the SCIP platform team immediately.

**Secret versioning — never delete:**

Secrets Manager secrets are updated with new versions, never deleted and recreated. Deleting a secret destroys its ARN, tags, KMS configuration, and version history, and would break applications that reference the ARN directly. If you see a request to delete `/scip/certs/*` secrets, do not proceed without explicit sign-off.

**IAM least-privilege:**

- `jagent-ec2-role` (issuance): write-only for `/scip/certs/*` in the spoke account. It cannot read other secrets.
- `CertLifecycleRole` (expiry checking): read-only for `/scip/certs/*` in the spoke account. It cannot write.

---

## 18. Rollback using previous secret versions

If a certificate issuance produces a bad certificate (e.g. wrong common name or SANs) and you need to restore the previous certificate, use the Secrets Manager version history.

> **Warning:** Rolling back restores the previous certificate, which may be closer to expiry than the new one. Only roll back if the newly issued certificate is definitively incorrect. Plan to re-issue correctly as soon as possible.

**Step 1 — List available versions.**

Run this in the **spoke account**:

```bash
aws secretsmanager list-secret-version-ids \
  --secret-id /scip/certs/b2bi-preprodc \
  --region eu-west-2 \
  --query 'Versions[*].{VersionId:VersionId,Labels:VersionStages}'
```

You will see something like:

```json
[
  {"VersionId": "abc12345-...", "Labels": ["AWSCURRENT"]},
  {"VersionId": "def67890-...", "Labels": ["AWSPREVIOUS"]}
]
```

**Step 2 — Retrieve the previous version to confirm its content.**

```bash
aws secretsmanager get-secret-value \
  --secret-id /scip/certs/b2bi-preprodc \
  --version-id def67890-... \
  --region eu-west-2 \
  --query 'SecretString' \
  --output text | python3 -c "
import json, sys
from cryptography import x509
d = json.load(sys.stdin)
cert = x509.load_pem_x509_certificate(d['certificate'].encode())
print('Common name:', cert.subject.rfc4514_string())
print('Expiry:', cert.not_valid_after_utc.isoformat())
"
```

This confirms the common name and expiry without printing the private key.

**Step 3 — Promote the previous version to AWSCURRENT.**

```bash
aws secretsmanager update-secret-version-stage \
  --secret-id /scip/certs/b2bi-preprodc \
  --version-stage AWSCURRENT \
  --move-to-version-id def67890-... \
  --remove-from-version-id abc12345-... \
  --region eu-west-2
```

**Step 4 — Confirm the rollback.**

```bash
aws secretsmanager describe-secret \
  --secret-id /scip/certs/b2bi-preprodc \
  --region eu-west-2 \
  --query 'VersionIdsToStages'
```

Confirm `def67890-...` now has label `AWSCURRENT`.

**Step 5 — Coordinate application reload.**

See section 14.

**Step 6 — Re-issue correctly.**

Correct the catalogue entry or Vault configuration that caused the bad certificate, then re-run the Jenkins pipeline to issue a new correct certificate.

---

## 19. Support and escalation

### First response

| Situation | Action |
| --- | --- |
| `[CERT RENEWAL NEEDED]` alert received | Follow section 11. Act within current working week. |
| `[CERT P1 - ACTION REQUIRED]` alert received | Follow section 12. Act immediately. |
| Jenkins pipeline fails | Follow section 16.10. Escalate if unresolved within 30 minutes. |
| Lambda logs show all apps erroring | Likely a Bitbucket token or IAM issue. Follow sections 16.8, 16.3. |
| Secret material visible in logs | Security incident. Do not share. Contact security and platform team. |

### Escalation path

1. **Self-serve:** This runbook and the CloudWatch logs.
2. **SCIP platform team:** Raise a ticket in the SCIP Jira project or contact in the `#scip-platform` Slack channel.
3. **AWS support:** For confirmed AWS service issues (Secrets Manager, STS, SNS outages).
4. **Vault team:** For Vault PKI issuance failures or PKI role configuration.
5. **Security team:** For any suspected secret exposure.

---

## 20. Appendix

### A. Example catalogue entries

**EC2 application (PT2, preprod):**

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

**ECS application (PT2, preprod):**

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

**EC2 application with SANs:**

```yaml
apps:
  - name: ibm-b2bi-prodc
    common_name: ibm-b2bi.c0081-prodc.local
    sans:
      - ibm-b2bi-internal.c0081-prodc.local
    ttl: 2160h
    deployment:
      type: ec2
      account_id: '<account-id>'
      account_name: prodc
    activation: maintenance-window
    maintenance_window: sun:01:00-03:00
```

---

### B. Example alert emails

**Renewal-needed alert:**

```
Subject: [CERT RENEWAL NEEDED] b2bi-preprodc expires in 22 days

Certificate renewal is required.

Application:         b2bi-preprodc
Account name:        preprodc
Account ID:          <account-id>
Current expiry date: 2026-06-03T12:00:00Z
Days remaining:      22

Jenkins renewal job: scip-cert-issuance
Jenkins job URL:     https://jenkins.<your-org>/job/scip-cert-issuance
APP_NAME parameter:  b2bi-preprodc

Required action:
Run the Jenkins certificate issuance job using the APP_NAME value above.

Runbook:
https://confluence.<your-org>/display/SCIP/Certificate+Lifecycle+Runbook
```

**P1 alert (near expiry):**

```
Subject: [CERT P1 - ACTION REQUIRED] b2bi-preprodc expires in 6 days

P1 certificate action is required.

Application:         b2bi-preprodc
Account name:        preprodc
Account ID:          <account-id>
Current expiry date: 2026-05-18T12:00:00Z
Days remaining:      6

Jenkins renewal job: scip-cert-issuance
Jenkins job URL:     https://jenkins.<your-org>/job/scip-cert-issuance
APP_NAME parameter:  b2bi-preprodc

Required action:
1. Run the Jenkins certificate issuance job immediately.
2. Confirm the Secrets Manager secret has been updated.
3. Coordinate application restart/reload with the owning team if required.

Runbook:
https://confluence.<your-org>/display/SCIP/Certificate+Lifecycle+Runbook
```

**P1 alert (expired):**

```
Subject: [CERT P1 - ACTION REQUIRED] b2bi-preprodc certificate expired 2 days ago

P1 certificate action is required.

Application:         b2bi-preprodc
Account name:        preprodc
Account ID:          <account-id>
Current expiry date: 2026-05-10T12:00:00Z
Days remaining:      -2

Jenkins renewal job: scip-cert-issuance
Jenkins job URL:     https://jenkins.<your-org>/job/scip-cert-issuance
APP_NAME parameter:  b2bi-preprodc

Required action:
1. Run the Jenkins certificate issuance job immediately.
2. Confirm the Secrets Manager secret has been updated.
3. Coordinate application restart/reload with the owning team if required.

Runbook:
https://confluence.<your-org>/display/SCIP/Certificate+Lifecycle+Runbook
```

---

### C. Quick reference — alert response

| Alert subject prefix | Days remaining | Urgency | Section |
| --- | --- | --- | --- |
| `[CERT RENEWAL NEEDED]` | 15–30 | Standard — act this week | 11 |
| `[CERT P1 - ACTION REQUIRED] ... expires in N days` | 1–14 | Urgent — act today | 12 |
| `[CERT P1 - ACTION REQUIRED] ... expired N days ago` | Negative | Critical — act immediately | 12 |

### D. Quick reference — Jenkins parameters

| Parameter | What to enter |
| --- | --- |
| `PRODUCT_TEAM` | `PT2`, `PT3`, `PT5`, etc. (from catalogue filename) |
| `ENVIRONMENT` | `dev`, `test`, `preprod`, or `prod` (from catalogue filename or account name) |
| `APP_NAME` | Full enrolled name from the alert, e.g. `b2bi-preprodc`. Leave empty to process all apps. |

### E. Key file locations

| File | Purpose |
| --- | --- |
| `scip/cert-lifecycle/certs/PTx-<env>-certs.yml` | Certificate catalogue — source of truth |
| `scip/cert-lifecycle/README.md` | Catalogue schema reference |
| `scip/cert-lifecycle/iam/spoke-account-jagent-policy.json` | IAM policy for issuance role |
| `scip/cert-lifecycle/iam/spoke-account-certlifecycle-role-policy.json` | IAM policy for Lambda expiry-check role |
| `scip/cert-lifecycle/iam/spoke-account-certlifecycle-role-kms-addon.json` | KMS addon for customer-managed key secrets |
| `scip/cert-lifecycle/scripts/validate-catalogues.py` | Validate all catalogue files locally |
| `scip/cert-lifecycle/lambda/expiry_checker/handler.py` | Lambda source |
| `scip-platform-lib/vars/issueCertificate.groovy` | Jenkins shared library step |
| `Jenkinsfile` | Jenkins issuance pipeline |
