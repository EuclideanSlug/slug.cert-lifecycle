# Statement of Need — Phase 1 Certificate Lifecycle Automation

## 1. Purpose

The organisation requires a controlled, repeatable, and auditable certificate lifecycle process for applications deployed across multiple AWS spoke accounts.

At present, certificate issuance and renewal contains too much manual coordination: engineers must identify the correct application, account, Vault parameters, Ansible role invocation, and AWS target account before updating certificate material. This creates operational risk, especially as certificates approach expiry.

Phase 1 will introduce a version-controlled certificate catalogue, a reusable Jenkins shared-library helper, a thin parameter-driven Jenkins issuance pipeline, an extension to the existing Ansible Vault certificate issuer role, and an expiry checker Lambda that reads real certificate expiry from AWS Secrets Manager and notifies the team before certificates expire.

The design goal is:

```text
One catalogue entry defines the application.
One Jenkins job can issue or renew it.
One Secrets Manager path stores the active certificate.
One Lambda checks expiry and routes alerts.
```

Phase 1 does **not** include automatic service restarts, application-specific certificate format conversion, live endpoint validation, or automatic Jenkins triggering.

---

# 2. High-level outcome

By the end of Phase 1:

1. Every enrolled application has a YAML catalogue entry.
2. Jenkins can issue or renew a certificate for one app, or all apps in a selected catalogue file.
3. The certificate is issued from Vault using the existing `universal-vault-cert-issuer` Ansible role.
4. The issued certificate material is written into the correct spoke account AWS Secrets Manager secret.
5. Existing Secrets Manager secrets are updated with new versions during renewal, not deleted and recreated.
6. A shared-account Lambda checks actual certificate expiry by parsing the PEM certificate stored in Secrets Manager.
7. The Lambda logs healthy certificates, sends renewal-required notifications for certificates approaching expiry, and sends P1 notifications for urgent or expired certificates.
8. Private keys, certificates, Vault tokens, Bitbucket tokens, AWS credentials, and full secret payloads are never printed to Jenkins, Ansible, Lambda, or CloudWatch logs.

---

# 3. Architecture overview

## 3.1 Components

```text
Bitbucket
  └── scip/cert-lifecycle/certs/PTx-<env>-certs.yml
        |
        | read by Jenkins issuance pipeline
        | read by expiry checker Lambda
        v

Jenkins cert-issuance pipeline
  └── reads catalogue
  └── filters by APP_NAME
  └── calls issueCertificate(app)
        |
        v

scip-platform-lib shared library
  └── vars/issueCertificate.groovy
        |
        | assumes jagent-ec2-role into spoke account
        | invokes universal-vault-cert-issuer Ansible role
        v

Ansible universal-vault-cert-issuer role
  └── issues PEM certificate from Vault
  └── writes structured JSON to spoke account Secrets Manager
        |
        v

Spoke account AWS Secrets Manager
  └── /scip/certs/{app_name}
        |
        | read by app startup script / init container
        | read by expiry checker Lambda
        v

Shared account expiry checker Lambda
  └── reads cert catalogue
  └── assumes CertLifecycleRole into each spoke account
  └── reads /scip/certs/{app_name}
  └── parses real PEM expiry using Python cryptography
  └── routes notifications through SNS
```

---

# 4. Key design decisions

## 4.1 Certificate TTL

Certificates use a TTL of:

```text
2160h = 90 days
```

Expiry routing is based on this lifecycle:

```text
> 30 days remaining      Log only
15–30 days remaining    Renewal-required notification
<= 14 days remaining    P1 action-required notification
Expired                 P1 action-required notification
```

The Lambda must parse expiry from the actual PEM certificate stored in Secrets Manager. The `expiry_epoch` field in the secret is retained for human reference only and must not be treated as the source of truth.

---

## 4.2 Source of truth

The certificate catalogue is the source of truth for enrolled applications.

Catalogue files are stored in Bitbucket under:

```text
scip/cert-lifecycle/certs/
```

Files are named:

```text
PTx-<env>-certs.yml
```

Where:

```text
PTx = product team identifier, for example PT2, PT3, PT5
env = dev, test, preprod, prod
```

Examples:

```text
PT2-dev-certs.yml
PT2-test-certs.yml
PT2-preprod-certs.yml
PT2-prod-certs.yml
PT5-preprod-certs.yml
```

---

## 4.3 Application naming convention

Each enrolled application entry must use a globally unique name.

The `name` field must follow:

```text
{application}-{account_name}
```

Examples:

```text
b2bi-devc
b2bi-preprodc
datapower-high-preprodc
ibm-b2bi-prodc
```

The `deployment.account_name` value must match the suffix of the `name`.

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

---

## 4.4 Secrets Manager path convention

The certificate secret is stored in the target spoke account under:

```text
/scip/certs/{app_name}
```

Where `{app_name}` is the `name` field from the catalogue.

Example:

```yaml
name: b2bi-preprodc
```

Creates or updates this spoke account secret:

```text
/scip/certs/b2bi-preprodc
```

Do not append the account name a second time.

Incorrect:

```text
/scip/certs/b2bi-preprodc-preprodc
```

---

## 4.5 Secret payload format

The Secrets Manager secret must contain structured JSON with exactly these required fields:

```json
{
  "certificate": "-----BEGIN CERTIFICATE-----\nMIID...\n-----END CERTIFICATE-----",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----",
  "ca_chain": "-----BEGIN CERTIFICATE-----\nMIID...\n-----END CERTIFICATE-----",
  "full_chain": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
  "expiry_epoch": "1780000000",
  "common_name": "b2bi.c0081-devc.local"
}
```

The `certificate` field is the leaf certificate.

The `private_key` field is the PEM private key.

The `ca_chain` field is the intermediate/root chain returned by Vault.

The `full_chain` field is the leaf certificate plus intermediates concatenated in PEM format.

The `expiry_epoch` field is retained for human reference and should match the actual PEM expiry, but monitoring must parse the real certificate.

The `common_name` field is the issued certificate common name.

---

## 4.6 Secret versioning

Existing secrets must be updated using a new Secrets Manager version.

Secrets must never be deleted and recreated during renewal.

Required behaviour:

```text
If secret does not exist:
  create /scip/certs/{app_name}

If secret exists:
  write a new AWSCURRENT version

Never:
  delete secret
  recreate secret
  replace ARN unnecessarily
```

This preserves:

```text
Secret ARN stability
previous versions
resource policies
tags
KMS configuration
audit history
rollback options
```

---

## 4.7 Security requirements

The private key and full secret payload must never appear in:

```text
Jenkins console output
Ansible logs
Ansible debug output
AWS CLI command output
Lambda CloudWatch logs
CloudTrail event request parameters where avoidable
temporary build artifacts
archived Jenkins workspace files
```

All Ansible tasks that handle certificate material, private keys, Vault responses, or Secrets Manager payloads must use:

```yaml
no_log: true
```

The Jenkins shared library and Jenkinsfile must not echo full app maps, Ansible variable payloads, cert material, secret values, or credentials.

The Lambda must not log:

```text
certificate
private_key
ca_chain
full_chain
SecretString
Bitbucket token
AWS temporary credentials
```

Safe logs may include:

```text
app_name
account_name
account_id
secret path
days_left
expiry date
status
error message without secret content
```

---

# 5. Phase 1 work packages

Phase 1 consists of six implementation areas:

1. Certificate catalogue schema and README.
2. Ansible role extension to write PEM material to Secrets Manager.
3. Jenkins shared library helper: `issueCertificate(app)`.
4. Jenkins certificate issuance pipeline.
5. Expiry checker Lambda with SNS threshold routing.
6. AWS infrastructure (Terraform).

---

# 6. Work package 1 — Certificate catalogue schema and README

## 6.1 Requirement

Create version-controlled YAML catalogue files defining every enrolled application, its certificate requirements, and its AWS spoke account.

Each catalogue file must be stored under:

```text
scip/cert-lifecycle/certs/
```

Using the file pattern:

```text
PTx-<env>-certs.yml
```

Examples:

```text
scip/cert-lifecycle/certs/PT2-dev-certs.yml
scip/cert-lifecycle/certs/PT2-preprod-certs.yml
scip/cert-lifecycle/certs/PT5-prod-certs.yml
```

---

## 6.2 Required YAML schema

Each file must contain a top-level `apps` list.

Example EC2 entry:

```yaml
apps:
  - name: b2bi-preprodc
    common_name: b2bi.c0081-preprodc.local
    sans: []
    ttl: 2160h
    deployment:
      type: ec2
      account_id: '302253067501'
      account_name: preprodc
    activation: maintenance-window
    maintenance_window: sun:02:00-04:00
```

Example ECS entry:

```yaml
apps:
  - name: datapower-high-preprodc
    common_name: dp-high.c0081-preprodc.local
    sans: []
    ttl: 2160h
    deployment:
      type: ecs
      account_id: '302253067501'
      account_name: preprodc
      cluster: c0081-preprodc-DP-high
      service: c0081-preprodc-DP-high-service
    activation: rolling
    maintenance_window: mon-fri:22:00-06:00
```

---

## 6.3 Required fields

Every app entry must contain:

```text
name
common_name
sans
ttl
deployment.type
deployment.account_id
deployment.account_name
activation
maintenance_window
```

For ECS entries, these are also required:

```text
deployment.cluster
deployment.service
```

Allowed deployment types:

```text
ec2
ecs
```

---

## 6.4 Field definitions

| Field                     | Description                                                                         |
| ------------------------- | ----------------------------------------------------------------------------------- |
| `name`                    | Globally unique enrolled app name. Must follow `{application}-{account_name}`.      |
| `common_name`             | Certificate common name requested from Vault.                                       |
| `sans`                    | List of subject alternative names. Can be empty.                                    |
| `ttl`                     | Certificate TTL. Default is `2160h`.                                                |
| `deployment.type`         | Either `ec2` or `ecs`.                                                              |
| `deployment.account_id`   | AWS spoke account ID as a quoted string.                                            |
| `deployment.account_name` | Human-readable account/environment suffix, for example `devc`, `preprodc`, `prodc`. |
| `deployment.cluster`      | ECS cluster name. Required only for ECS entries.                                    |
| `deployment.service`      | ECS service name. Required only for ECS entries.                                    |
| `activation`              | Future Phase 2 activation behaviour. Present in Phase 1 but not acted on.           |
| `maintenance_window`      | Future Phase 2 maintenance window. Present in Phase 1 but not acted on.             |

---

## 6.5 README requirement

Create or update:

```text
scip/cert-lifecycle/README.md
```

The README must document:

```text
Purpose of the certificate catalogue
File naming convention
Application naming convention
Secret path convention
Required fields
Deployment types
TTL standard
How to add a new app entry
How Jenkins uses the file
How the expiry checker Lambda uses the file
Phase 1 limitations
```

The README must clearly state:

```text
Secret path = /scip/certs/{name}
```

Where `{name}` is the app `name` field from the YAML.

---

## 6.6 Acceptance criteria

```text
- Catalogue files exist under scip/cert-lifecycle/certs/.
- Files use the naming pattern PTx-<env>-certs.yml.
- Each file has a top-level apps list.
- Every app entry contains deployment.account_id and deployment.account_name.
- Every app name follows {application}-{account_name}.
- Every app name is globally unique within its catalogue file.
- deployment.type is either ec2 or ecs.
- ECS entries include deployment.cluster and deployment.service.
- activation and maintenance_window are present for all entries.
- README documents the schema, secret path convention, and new-entry process.
```

---

# 7. Work package 2 — Extend Ansible role to write certificate to Secrets Manager

## 7.1 Requirement

Extend the existing `universal-vault-cert-issuer` Ansible role so that, after issuing a PEM certificate from Vault, it writes the issued certificate material into the correct spoke account Secrets Manager secret.

The Jenkins shared library will assume into the target spoke account before invoking the role. The Ansible role must still validate that the current AWS account matches the expected `account_id`.

---

## 7.2 Inputs to the role

The role must accept, at minimum:

```yaml
app_name: b2bi-preprodc
common_name: b2bi.c0081-preprodc.local
sans: []
ttl: 2160h
aws_region: eu-west-2
account_id: '302253067501'
account_name: preprodc
secret_name: /scip/certs/b2bi-preprodc
```

The role will already receive or produce the following from Vault issuance:

```yaml
certificate: "<PEM leaf certificate>"
private_key: "<PEM private key>"
ca_chain: "<PEM CA chain>"
full_chain: "<PEM full chain>"
expiry_epoch: "1780000000"
```

---

## 7.3 Required behaviour

The role must:

1. Issue the certificate from Vault using the existing process.
2. Build the required JSON secret payload.
3. Check the active AWS caller identity.
4. Confirm the current account matches `account_id`.
5. Create the secret if it does not exist.
6. Update the existing secret with a new version if it already exists.
7. Ensure the secret has these tags:

```text
managed-by = cert-lifecycle
app_name   = {app_name}
```

8. Never delete and recreate an existing secret.
9. Never print private key or certificate payloads.

---

## 7.4 Recommended account guardrail

Before writing to Secrets Manager, run an STS caller identity check.

The role should fail if:

```text
current AWS account != account_id from certs.yml
```

This protects against Jenkins assuming the wrong account or failing to assume the intended account.

---

## 7.5 Secret creation and update logic

Required logic:

```text
If /scip/certs/{app_name} does not exist:
  create secret with JSON payload and required tags

If /scip/certs/{app_name} exists:
  put new secret value
  ensure required tags exist

Never:
  delete secret
  recreate secret
```

The AWS API equivalent is:

```text
create-secret       for first creation
put-secret-value    for renewal/update
tag-resource        to apply/repair tags
```

---

## 7.6 Security requirements

All Ansible tasks touching any of the following must use `no_log: true`:

```text
Vault response
certificate
private_key
ca_chain
full_chain
expiry_epoch payload
SecretString
Secrets Manager write result
temporary payload files, if any
```

Avoid writing secret payloads to disk. If temporary files are unavoidable, they must be:

```text
created with restrictive permissions
not printed
not archived
deleted immediately in an always/finally cleanup step
```

Preferred implementation is to use an Ansible AWS module or a small boto3 helper that passes payloads in memory/stdin rather than command-line arguments.

Do not pass secret JSON directly in shell command arguments.

---

## 7.7 Required IAM permissions for Jenkins assumed role in spoke account

The assumed `jagent-ec2-role` must have, at minimum:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CreateAndUpdateCertSecrets",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:CreateSecret",
        "secretsmanager:DescribeSecret",
        "secretsmanager:PutSecretValue",
        "secretsmanager:TagResource"
      ],
      "Resource": "arn:aws:secretsmanager:eu-west-2:<account-id>:secret:/scip/certs/*"
    }
  ]
}
```

If using a customer-managed KMS key, include appropriate KMS permissions constrained via `kms:ViaService` for Secrets Manager.

---

## 7.8 Acceptance criteria

```text
- Role writes certificate JSON to /scip/certs/{app_name} in the spoke account.
- JSON contains certificate, private_key, ca_chain, full_chain, expiry_epoch, and common_name.
- Role creates the secret if it does not exist.
- Role updates existing secrets as new versions using put-secret-value behaviour.
- Role never deletes and recreates existing secrets.
- Secret is tagged with managed-by=cert-lifecycle and app_name={app_name}.
- Role validates current AWS account matches account_id before writing.
- Private key and secret payload never appear in Ansible or Jenkins logs.
- Role is safe to rerun for the same app.
```

---

# 8. Work package 3 — Jenkins shared library helper `issueCertificate(app)`

## 8.1 Requirement

Add a reusable Jenkins shared library step:

```text
vars/issueCertificate.groovy
```

in `scip-platform-lib`.

The helper must encapsulate all Jenkins-side orchestration needed to issue or renew one certificate.

Calling pipelines should be able to do:

```groovy
issueCertificate(app)
```

Where `app` is one application entry from the YAML catalogue.

---

## 8.2 Responsibilities

The helper must:

1. Accept a single `Map app`.
2. Validate required fields.
3. Read `account_id` and `account_name` from `app.deployment`.
4. Derive the secret path:

```text
/scip/certs/{app.name}
```

5. Assume `jagent-ec2-role` in the spoke account using `withAWS`.
6. Invoke the `universal-vault-cert-issuer` Ansible role with the correct variables.
7. Fail fast on validation, account assumption, or Ansible errors.
8. Avoid printing secret/cert material or full app maps.
9. Clean up temporary variable files.

---

## 8.3 Required validation

The helper must validate that these fields exist:

```text
app.name
app.common_name
app.ttl
app.deployment
app.deployment.type
app.deployment.account_id
app.deployment.account_name
```

It must validate:

```text
deployment.type is either ec2 or ecs
app.name ends with "-" + app.deployment.account_name
```

For example:

```groovy
if (!app.name.endsWith("-${app.deployment.account_name}")) {
    error("Certificate app name '${app.name}' must end with account_name '${app.deployment.account_name}'")
}
```

---

## 8.4 Safe Ansible invocation

The helper should not pass many variables directly on the shell command line.

Preferred approach:

1. Build a temporary JSON/YAML vars file containing non-secret input variables.
2. Call Ansible with:

```bash
ansible-playbook playbooks/issue-certificate.yml --extra-vars @vars-file.json
```

3. Delete the vars file in a `finally` block.

The vars file must not contain private key or issued certificate material.

The shell block must include:

```bash
set +x
```

The helper must not echo the contents of the vars file.

---

## 8.5 Variables to pass to Ansible

At minimum:

```yaml
app_name: "{app.name}"
common_name: "{app.common_name}"
sans: "{app.sans}"
ttl: "{app.ttl}"
deployment_type: "{app.deployment.type}"
account_id: "{app.deployment.account_id}"
account_name: "{app.deployment.account_name}"
secret_name: "/scip/certs/{app.name}"
aws_region: "eu-west-2"
activation: "{app.activation}"
maintenance_window: "{app.maintenance_window}"
```

If the application is ECS, pass through:

```yaml
ecs_cluster: "{app.deployment.cluster}"
ecs_service: "{app.deployment.service}"
```

---

## 8.6 Acceptance criteria

```text
- vars/issueCertificate.groovy exists in scip-platform-lib.
- Step accepts a single Map representing one certs.yml app entry.
- Step reads account_id and account_name from app.deployment.
- No separate account parameter is required.
- Step validates required app fields.
- Step validates deployment.type is ec2 or ecs.
- Step validates app.name suffix matches deployment.account_name.
- Step derives secret_name as /scip/certs/{app.name}.
- Step assumes jagent-ec2-role in app.deployment.account_id using withAWS.
- Step invokes the universal-vault-cert-issuer Ansible role.
- Step throws/fails on Ansible failure.
- Step does not print full app map, cert content, private key, or secret payload.
- Temporary variable file is removed after execution.
- Shared library version is bumped.
- CHANGELOG is updated.
- PR is reviewed by at least one other team member before merge.
```

---

# 9. Work package 4 — Jenkins certificate issuance pipeline

## 9.1 Requirement

Create a thin Jenkins pipeline that reads `PTx-<env>-certs.yml`, resolves target application entries, and calls:

```groovy
issueCertificate(app)
```

The Jenkinsfile must not contain inline Ansible, Vault, AWS Secrets Manager write logic, or custom account switching beyond what is already encapsulated by the shared library helper.

---

## 9.2 Required parameters

The pipeline should expose:

```text
PRODUCT_TEAM
ENVIRONMENT
APP_NAME
```

Suggested parameter definitions:

```groovy
parameters {
    choice(
        name: 'PRODUCT_TEAM',
        choices: ['PT2', 'PT3', 'PT4', 'PT5'],
        description: 'Product team certificate catalogue to use'
    )

    choice(
        name: 'ENVIRONMENT',
        choices: ['dev', 'test', 'preprod', 'prod'],
        description: 'Environment certificate catalogue to use'
    )

    string(
        name: 'APP_NAME',
        defaultValue: '',
        description: 'Optional. If set, only this app is issued/renewed. If empty, all apps in the catalogue are processed sequentially.'
    )
}
```

The catalogue path is derived as:

```groovy
scip/cert-lifecycle/certs/${PRODUCT_TEAM}-${ENVIRONMENT}-certs.yml
```

Example:

```text
scip/cert-lifecycle/certs/PT2-preprod-certs.yml
```

---

## 9.3 Required behaviour

At the start of every run, the pipeline must:

1. Check out the latest Bitbucket repository content.
2. Read the selected YAML file.
3. Validate that it contains a top-level `apps` list.
4. Detect duplicate app names in the selected catalogue.
5. If `APP_NAME` is provided:

   * find exactly one matching app entry;
   * fail clearly if not found;
   * fail clearly if duplicate matches exist.
6. If `APP_NAME` is empty:

   * process every app in the selected catalogue sequentially.
7. For each selected app:

   * call `issueCertificate(app)`;
   * fail fast if it fails;
   * report which `app.name` failed.
8. Clean the workspace after execution.

---

## 9.4 Processing mode

Single app mode:

```text
PRODUCT_TEAM = PT2
ENVIRONMENT  = preprod
APP_NAME     = b2bi-preprodc
```

Pipeline reads:

```text
PT2-preprod-certs.yml
```

Then runs:

```groovy
issueCertificate(app)
```

for only:

```text
b2bi-preprodc
```

Bulk mode:

```text
PRODUCT_TEAM = PT2
ENVIRONMENT  = preprod
APP_NAME     = ""
```

Pipeline reads:

```text
PT2-preprod-certs.yml
```

Then runs all apps sequentially:

```groovy
for (app in apps) {
    issueCertificate(app)
}
```

Do not process apps in parallel in Phase 1.

---

## 9.5 Acceptance criteria

```text
- Pipeline reads the selected PTx-<env>-certs.yml file from Bitbucket at the start of every run.
- PRODUCT_TEAM and ENVIRONMENT parameters derive the catalogue filename.
- APP_NAME filters to a single app when supplied.
- Clear error is raised if APP_NAME is not found.
- Available app names are shown in the not-found error.
- Duplicate app names in a catalogue cause pipeline failure.
- All apps run sequentially when APP_NAME is empty.
- Pipeline calls issueCertificate(app) from scip-platform-lib.
- Jenkinsfile contains no inline Ansible logic.
- Jenkinsfile contains no inline Vault issuance logic.
- Jenkinsfile contains no inline Secrets Manager write logic.
- Pipeline fails fast on the first issueCertificate(app) failure.
- Failure message includes the failed app_name.
- No secrets, tokens, private keys, certificates, or secret payloads appear in console logs.
- Workspace is cleaned after execution.
```

---

# 10. Work package 5 — Expiry checker Lambda

## 10.1 Requirement

Deploy a Lambda in the shared services account that checks certificate expiry for all enrolled applications.

The Lambda must:

1. Read certificate catalogue files from Bitbucket API using a token stored in shared-account Secrets Manager.
2. Iterate every enrolled application.
3. Assume `CertLifecycleRole` into the relevant spoke account.
4. Read `/scip/certs/{app.name}` from that spoke account’s Secrets Manager.
5. Extract the `certificate` field.
6. Parse the actual PEM expiry using the Python `cryptography` library.
7. Calculate `days_left`.
8. Route to log-only, renewal notification, or P1 notification based on thresholds.
9. Continue processing if an individual app fails.
10. Never log secret material.

---

## 10.2 Source of catalogue

The Lambda must read catalogue files from Bitbucket API.

The Bitbucket token is stored in shared-account Secrets Manager.

Example token secret:

```text
/scip/cert-lifecycle/bitbucket-token
```

Expected token secret format:

```json
{
  "token": "TOKEN_VALUE"
}
```

The Lambda must not log the token.

---

## 10.3 Lambda environment variables

Use environment variables similar to:

```text
AWS_REGION=eu-west-2
BITBUCKET_TOKEN_SECRET_ID=/scip/cert-lifecycle/bitbucket-token
BITBUCKET_CATALOGUE_URLS=<comma-separated raw Bitbucket URLs>
SPOKE_ROLE_NAME=CertLifecycleRole
CERT_RENEWAL_TOPIC_ARN=arn:aws:sns:eu-west-2:<shared-account-id>:scip-cert-renewal
CERT_P1_ALERT_TOPIC_ARN=arn:aws:sns:eu-west-2:<shared-account-id>:scip-cert-p1-alerts
JENKINS_JOB_NAME=scip-cert-issuance
JENKINS_JOB_URL=https://jenkins.example/job/scip-cert-issuance
RUNBOOK_URL=https://confluence.example/display/SCIP/Certificate+Lifecycle+Runbook
```

If catalogue URLs become too large for an environment variable, replace with a manifest file or repository path listing in a later story.

---

## 10.4 Spoke account role

Each spoke account must contain:

```text
CertLifecycleRole
```

The shared-account Lambda execution role must be allowed to assume it.

The spoke role must be read-only for certificate expiry checking.

Required permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadCertificateSecrets",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:eu-west-2:<spoke-account-id>:secret:/scip/certs/*"
    }
  ]
}
```

If the cert secrets use a customer-managed KMS key, add:

```json
{
  "Sid": "DecryptCertificateSecretsViaSecretsManager",
  "Effect": "Allow",
  "Action": [
    "kms:Decrypt"
  ],
  "Resource": "arn:aws:kms:eu-west-2:<spoke-account-id>:key/<key-id>",
  "Condition": {
    "StringEquals": {
      "kms:ViaService": "secretsmanager.eu-west-2.amazonaws.com"
    }
  }
}
```

The Lambda should not write back to spoke account Secrets Manager in Phase 1.

---

## 10.5 Expiry parsing

The Lambda must parse expiry from the actual PEM certificate.

Required Python library:

```text
cryptography
```

Expected logic:

```python
from cryptography import x509

def parse_pem_expiry_epoch(certificate_pem: str) -> int:
    cert = x509.load_pem_x509_certificate(certificate_pem.encode("utf-8"))
    return int(cert.not_valid_after_utc.timestamp())
```

Do not rely on:

```json
"expiry_epoch"
```

for alerting decisions.

The Lambda may log `expiry_epoch` for comparison/reference but must route based on the parsed PEM expiry.

---

## 10.6 Threshold routing

After calculating `days_left`, route as follows:

```text
days_left > 30
  Log only
  No SNS publish

15 <= days_left <= 30
  Publish to cert-renewal SNS
  Subject: [CERT RENEWAL NEEDED]

days_left <= 14
  Publish to cert-p1-alerts SNS
  Subject: [CERT P1 - ACTION REQUIRED]
```

Expired certificates are included in the P1 route.

Example:

```text
days_left = -2
  P1 action required
```

---

## 10.7 Notification body requirements

Both renewal and P1 notifications must include:

```text
app_name
account_name
account_id
days_left
expiry_date
Jenkins job name
APP_NAME parameter value
runbook link
```

Suggested renewal subject:

```text
[CERT RENEWAL NEEDED] b2bi-preprodc expires in 22 days
```

Suggested P1 subject:

```text
[CERT P1 - ACTION REQUIRED] b2bi-preprodc expires in 6 days
```

Suggested expired subject:

```text
[CERT P1 - ACTION REQUIRED] b2bi-preprodc certificate expired 2 days ago
```

Suggested renewal body:

```text
Certificate renewal is required.

Application: b2bi-preprodc
Account name: preprodc
Account ID: 302253067501
Current expiry date: 2026-06-01T12:00:00Z
Days remaining: 22

Jenkins renewal job: scip-cert-issuance
Jenkins job URL: https://jenkins.example/job/scip-cert-issuance
APP_NAME parameter value: b2bi-preprodc

Required action:
Run the Jenkins certificate issuance job using the APP_NAME value above.

Runbook:
https://confluence.example/display/SCIP/Certificate+Lifecycle+Runbook
```

Suggested P1 body:

```text
P1 certificate action is required.

Application: b2bi-preprodc
Account name: preprodc
Account ID: 302253067501
Current expiry date: 2026-05-16T12:00:00Z
Days remaining: 6

Jenkins renewal job: scip-cert-issuance
Jenkins job URL: https://jenkins.example/job/scip-cert-issuance
APP_NAME parameter value: b2bi-preprodc

Required action:
1. Run the Jenkins certificate issuance job immediately.
2. Confirm the Secrets Manager secret has been updated.
3. Coordinate application restart/reload with the owning team if required.

Runbook:
https://confluence.example/display/SCIP/Certificate+Lifecycle+Runbook
```

---

## 10.8 Error handling

A failure for one app must not crash the entire Lambda.

For each app, catch and log exceptions such as:

```text
Invalid catalogue entry
STS assume-role failure
Secrets Manager AccessDenied
Secret not found
Invalid secret JSON
Missing certificate field
Invalid PEM certificate
SNS publish failure
```

The Lambda must continue to the next app.

At the end of the run, log a summary:

```json
{
  "checked": 20,
  "ok": 14,
  "renewal_needed": 4,
  "p1_action_required": 1,
  "errors": 1
}
```

If all apps fail due to a global issue such as Bitbucket token failure, the Lambda should log the error clearly and return a controlled failure or error summary. It must not leak secrets.

---

## 10.9 Lambda packaging

The Lambda deployment must include these Python dependencies:

```text
cryptography
PyYAML
requests
boto3 is available in Lambda runtime but can be pinned if packaged intentionally
```

Because `cryptography` includes native components, package it using one of:

```text
Lambda layer built in an Amazon Linux-compatible environment
Lambda container image
CI-built deployment package compatible with the Lambda runtime and architecture
```

Do not build `cryptography` on an incompatible workstation and upload it untested.

---

## 10.10 Lambda IAM permissions

The shared account Lambda execution role needs:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadBitbucketToken",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:eu-west-2:<shared-account-id>:secret:/scip/cert-lifecycle/bitbucket-token-*"
    },
    {
      "Sid": "AssumeSpokeCertLifecycleRoles",
      "Effect": "Allow",
      "Action": [
        "sts:AssumeRole"
      ],
      "Resource": [
        "arn:aws:iam::<spoke-account-id-1>:role/CertLifecycleRole",
        "arn:aws:iam::<spoke-account-id-2>:role/CertLifecycleRole"
      ]
    },
    {
      "Sid": "PublishCertificateNotifications",
      "Effect": "Allow",
      "Action": [
        "sns:Publish"
      ],
      "Resource": [
        "arn:aws:sns:eu-west-2:<shared-account-id>:scip-cert-renewal",
        "arn:aws:sns:eu-west-2:<shared-account-id>:scip-cert-p1-alerts"
      ]
    },
    {
      "Sid": "WriteLambdaLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

Restrict `sts:AssumeRole` to known spoke account role ARNs where possible.

Restrict `sns:Publish` to the exact SNS topic ARNs.

---

## 10.11 Acceptance criteria

```text
- Lambda is deployed in the shared services account.
- Lambda reads catalogue files from Bitbucket API using a token stored in shared-account Secrets Manager.
- Lambda iterates every enrolled app from the selected catalogue files.
- Lambda reads account_id and account_name from app.deployment.
- Lambda assumes CertLifecycleRole in each target spoke account.
- Lambda fetches /scip/certs/{app.name} from spoke account Secrets Manager.
- Lambda extracts only the certificate field from the secret payload for expiry parsing.
- Lambda parses actual PEM expiry using Python cryptography.
- Lambda routes based on actual PEM expiry, not expiry_epoch.
- days_left > 30 logs only and publishes no SNS message.
- 15 <= days_left <= 30 publishes to cert-renewal SNS with subject containing [CERT RENEWAL NEEDED].
- days_left <= 14, including expired, publishes to cert-p1-alerts SNS with subject containing [CERT P1 - ACTION REQUIRED].
- Renewal and P1 message bodies include app_name, account_name, account_id, days_left, expiry_date, Jenkins job name, APP_NAME parameter value, and runbook link.
- Failure on one app logs the error and continues to the next app.
- Lambda logs a final summary of checked, healthy, renewal-needed, P1, and failed entries.
- Lambda never logs private keys, certificate PEM bodies, full secret payloads, Bitbucket token, or AWS temporary credentials.
```

---

# 11. Work package 6 — AWS infrastructure (Terraform)

## 11.1 Requirement

Deploy and manage the AWS infrastructure required for Phase 1 certificate lifecycle automation using Terraform. Terraform must own durable AWS infrastructure in two areas:

1. The shared services account — expiry checker Lambda, IAM execution role, SNS topics, CloudWatch log group.
2. Each spoke application account — `CertLifecycleRole` cross-account trust role with read-only certificate access.

Terraform must **not** own certificate private keys, PEM certificate bodies, Vault-issued certificate material, or live Secrets Manager certificate secret values.

---

## 11.2 Shared services account resources

Terraform must create or manage:

- Expiry checker Lambda function
- Lambda execution IAM role and least-privilege policy
- CloudWatch log group with configurable retention (default 30 days)
- `scip-cert-renewal` SNS topic
- `scip-cert-p1-alerts` SNS topic
- Optional Bitbucket token Secrets Manager secret container (metadata only — value set manually after deployment)

---

## 11.3 Spoke account resources

Terraform must provide a reusable module that creates:

- `CertLifecycleRole` IAM role
- Trust policy allowing the shared-account Lambda execution role to assume it
- Read-only Secrets Manager policy scoped to `/scip/certs/*`
- Optional KMS decrypt policy constrained by `kms:ViaService` when customer-managed keys are in use

The spoke role must **not** have write access to Secrets Manager (`PutSecretValue`, `CreateSecret`, `DeleteSecret`, `UpdateSecret`).

---

## 11.4 IAM least privilege

### Lambda execution role

| Action | Scope |
| --- | --- |
| `secretsmanager:GetSecretValue` | Bitbucket token secret ARN only |
| `sts:AssumeRole` | Approved spoke `CertLifecycleRole` ARNs only |
| `sns:Publish` | cert-renewal and cert-p1-alerts topic ARNs only |
| `logs:CreateLogStream`, `logs:PutLogEvents` | Lambda CloudWatch log group ARN only |

### jagent-ec2-role (externally owned)

This role is owned outside this Terraform state. The required Secrets Manager write policy and optional KMS addon are documented in:

```text
scip/cert-lifecycle/iam/spoke-account-jagent-policy.json
scip/cert-lifecycle/iam/spoke-account-jagent-kms-addon.json
```

Apply these through whichever process owns the role.

---

## 11.5 Lambda environment variables managed by Terraform

```text
BITBUCKET_TOKEN_SECRET_ID  /scip/cert-lifecycle/bitbucket-token
BITBUCKET_CATALOGUE_URLS   <comma-separated raw Bitbucket file URLs>
SPOKE_ROLE_NAME            CertLifecycleRole
CERT_RENEWAL_TOPIC_ARN     <SNS topic ARN>
CERT_P1_ALERT_TOPIC_ARN    <SNS topic ARN>
JENKINS_JOB_NAME           <Jenkins job name>
JENKINS_JOB_URL            <Jenkins job URL>
RUNBOOK_URL                <runbook URL>
```

`AWS_REGION` is excluded — the Lambda runtime provides it automatically from the function's deployment region.

No environment variable may contain private keys, certificate bodies, or live secret values.

---

## 11.6 Critical state security rule

Terraform must never store certificate private keys or certificate bodies in state.

Do not create `aws_secretsmanager_secret_version` resources for live certificate material.

Terraform may create the Bitbucket token Secrets Manager secret container. The token value must be inserted manually:

```bash
aws secretsmanager put-secret-value \
  --secret-id "/scip/cert-lifecycle/bitbucket-token" \
  --secret-string '{"token":"<token>"}' \
  --region eu-west-2
```

---

## 11.7 Deployment model

Two root modules are applied independently:

```text
1. Apply terraform/shared-services/ in the shared services account.
   Note the lambda_execution_role_arn output for spoke applies.

2. Apply terraform/spoke/ once per spoke account, switching AWS credentials.
```

The shared services apply must precede spoke applies. See `terraform/shared-services/terraform.tfvars.example` and `terraform/spoke/terraform.tfvars.example` for full variable reference.

After both applies, complete these manual steps:

```text
1. Insert the Bitbucket token value into Secrets Manager.
2. Create an EventBridge schedule rule targeting the Lambda ARN.
3. Subscribe to the SNS topics.
```

---

## 11.8 Validation requirements

```text
terraform fmt -check -recursive
terraform validate  (shared-services root module)
terraform validate  (spoke root module)
```

---

## 11.9 Acceptance criteria

```text
- Terraform creates the shared-account expiry checker Lambda infrastructure.
- Terraform creates the Lambda CloudWatch log group with configurable retention.
- Terraform creates the Lambda execution role with least-privilege IAM.
- Lambda can only read the Bitbucket token secret, assume approved spoke
  CertLifecycleRole ARNs, publish to the cert lifecycle SNS topics, and
  write to its own CloudWatch log group.
- Terraform creates cert-renewal and cert-p1-alerts SNS topics.
- Terraform provides a reusable spoke module for CertLifecycleRole.
- CertLifecycleRole trusts only the shared-account Lambda execution role.
- CertLifecycleRole can read /scip/certs/* but cannot create, update, or delete secrets.
- KMS decrypt permissions are constrained to supplied CMK ARNs with kms:ViaService condition.
- Terraform does not manage live certificate secret values.
- Terraform state does not contain private keys, PEM bodies, Bitbucket token values,
  Vault tokens, or AWS credentials.
- Terraform exposes non-sensitive operational outputs (Lambda ARN, role ARN, SNS ARNs,
  log group name).
- terraform fmt -check passes.
- terraform validate passes for both root modules.
- Deployment guide explains shared-account and spoke-account deployment order.
```

---

# 12. Explicit Phase 1 exclusions

The following are not part of Phase 1:

```text
Application-specific startup scripts
Application-specific init containers
Application restart/reload automation
Automatic Jenkins triggering
Webhook integration
Post-renewal success notification Lambda
Live endpoint certificate checking
Restart-overdue detection
KDB conversion
JKS conversion
PKCS12 conversion
Creating new Vault PKI roles
Changing Vault certificate issuance policy
Changing application TLS configuration
DynamoDB alert deduplication
Advanced schema validation tooling
EventBridge scheduling, unless implemented as a separate story
```

Important clarification:

The Lambda cannot determine whether an application has restarted onto a renewed certificate unless it checks the live application endpoint or receives deployment state from the application. Therefore, this Phase 1 solution must not claim to detect:

```text
[CERT RENEWED - RESTART OVERDUE]
```

That can be added in a later phase by comparing the Secrets Manager certificate against the certificate served by the live endpoint.

---

# 13. Operational runbook expectations

A runbook link must be included in alert messages.

The runbook should explain:

```text
How to identify the affected app
How to open the Jenkins cert-issuance pipeline
Which parameters to select
How to set APP_NAME
How to confirm the Secrets Manager secret has a new AWSCURRENT version
How to coordinate restart/reload with the application team
How to verify the application is using the renewed certificate
How to escalate if renewal fails
```

Minimum operator flow after a renewal-needed email:

```text
1. Open Jenkins cert-issuance job.
2. Select PRODUCT_TEAM.
3. Select ENVIRONMENT.
4. Set APP_NAME to the value from the email.
5. Run the job.
6. Confirm Jenkins completes successfully.
7. Confirm /scip/certs/{APP_NAME} in the spoke account has a new AWSCURRENT version.
8. Coordinate application restart/reload if the app does not dynamically reload certificates.
```

---

# 14. Key implementation pitfalls to avoid

## 14.1 Confusing base app name with enrolled app name

Use the catalogue `name` field everywhere for secret paths and Jenkins `APP_NAME`.

Correct:

```text
/scip/certs/b2bi-preprodc
```

Incorrect:

```text
/scip/certs/b2bi
```

---

## 14.2 Deleting and recreating Secrets Manager secrets

Do not delete and recreate secrets during renewal.

Use new secret versions.

---

## 14.3 Logging secret payloads

Never log the JSON secret payload. It contains the private key.

---

## 14.4 Relying on `expiry_epoch`

Do not route alerts based on `expiry_epoch`.

Always parse the real PEM certificate.

---

## 14.5 Wrong account writes

The Ansible role must verify the current AWS account before writing to Secrets Manager.

---

## 14.6 Parallel bulk renewals

Do not run all apps in parallel in Phase 1.

Sequential processing is safer for Vault, STS, Secrets Manager, and auditability.

---

## 14.7 `cryptography` packaging failures

Package the Lambda dependencies in a Lambda-compatible build environment.

---

## 14.8 Claiming restart-overdue detection

Phase 1 does not check live application endpoints. It cannot know whether the running app has consumed the renewed secret.

---

# 15. Definition of Done

Phase 1 is complete when:

```text
- Catalogue files exist and are populated for all in-scope applications.
- README documents schema, naming, secret path, and onboarding process.
- Ansible role writes issued PEM material to spoke account Secrets Manager.
- Existing secrets are updated as new versions, not deleted/recreated.
- Private key does not appear in Jenkins or Ansible logs.
- issueCertificate(app) exists in scip-platform-lib.
- Jenkins cert-issuance pipeline can issue/renew one app using APP_NAME.
- Jenkins cert-issuance pipeline can issue/renew all apps in a catalogue sequentially.
- Expiry checker Lambda is deployed in shared services account.
- Lambda can read catalogue files from Bitbucket.
- Lambda can assume CertLifecycleRole into spoke accounts.
- Lambda can read certificate secrets and parse actual PEM expiry.
- Lambda logs healthy certs.
- Lambda publishes renewal-required SNS notifications for 15–30 days remaining.
- Lambda publishes P1 SNS notifications for <=14 days or expired certificates.
- Notifications contain all required operational fields.
- Per-app failures do not stop the whole Lambda run.
- No private keys, PEM bodies, tokens, credentials, or full secret payloads appear in logs.
- Terraform creates shared-account Lambda, IAM, SNS, and CloudWatch infrastructure.
- Terraform creates spoke-account CertLifecycleRole with correct trust and read-only Secrets Manager access.
- Terraform state does not contain certificate private keys, PEM bodies, or Bitbucket token values.
- terraform fmt and terraform validate pass for both root modules.
```

---

# 16. Recommended implementation order

Implement in this order:

```text
1.  Create catalogue schema and README.
2.  Populate initial PTx-<env>-certs.yml files.
3.  Extend Ansible role to write issued cert material to Secrets Manager.
4.  Add issueCertificate(app) to scip-platform-lib.
5.  Create Jenkins cert-issuance pipeline.
6.  Test single-app issuance into a non-prod spoke account.
7.  Test renewal of an existing secret and confirm new AWSCURRENT version.
8.  Apply shared-services Terraform (SNS topics, Lambda IAM, CloudWatch log group).
9.  Insert Bitbucket token into shared-account Secrets Manager.
10. Apply spoke Terraform (CertLifecycleRole) in each non-prod spoke account.
11. Deploy expiry checker Lambda via shared-services Terraform apply.
12. Configure EventBridge schedule targeting the Lambda.
13. Test Lambda against one catalogue and one non-prod app.
14. Test threshold routing using test certificates or mocked days_left.
15. Roll out to additional non-prod accounts (repeat step 10 per account).
16. Roll out to production after non-prod validation.
```

This order reduces risk because Jenkins issuance and Secrets Manager writing can be validated before the monitoring/alerting layer depends on them. Terraform steps (8–12) should be completed before Lambda testing begins.
