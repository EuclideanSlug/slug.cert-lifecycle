# Operations Runbook

Use this runbook to issue or renew certificates, respond to SNS alerts, verify Secrets Manager versions, and troubleshoot failures.

## Alert response

| Alert | Meaning | Action |
| --- | --- | --- |
| `[CERT RENEWAL NEEDED]` | 15-30 days remaining | renew within the current working week |
| `[CERT P1 - ACTION REQUIRED] ... expires in N days` | 1-14 days remaining | renew today |
| `[CERT P1 - ACTION REQUIRED] ... expired N days ago` | expired | renew immediately and escalate if blocked |

The alert body includes the application name, account, expiry date, Jenkins job details, and `APP_NAME` value.

## Issue or renew one certificate

1. Open the Jenkins certificate issuance job.
2. Select:

| Parameter | Value |
| --- | --- |
| `PRODUCT_TEAM` | Product team prefix from the catalogue filename, for example `PT2` |
| `ENVIRONMENT` | `dev`, `test`, `preprod`, or `prod` |
| `APP_NAME` | Full catalogue `name`, for example `b2bi-preprodc` |

3. Run the build.
4. Confirm the build completes successfully.
5. Verify the Secrets Manager version in the spoke account.
6. Coordinate application reload or restart with the owning team if required.

`APP_NAME` is the full enrolled app name. Do not use only the base application name.

## Issue all apps in one catalogue

Leave `APP_NAME` empty. Jenkins processes all apps in the selected catalogue sequentially and fails fast on the first error.

For large or risky renewals, prefer targeted `APP_NAME` runs.

## Verify a new secret version

Run in the spoke account:

```bash
aws secretsmanager describe-secret \
  --secret-id /scip/certs/b2bi-preprodc \
  --region eu-west-2 \
  --query 'VersionIdsToStages'
```

Expected result: the latest version has `AWSCURRENT`; the previous version usually has `AWSPREVIOUS`.

To check the certificate expiry without printing the private key:

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
print(cert.not_valid_after_utc.isoformat())
"
```

## Application reloads

Phase 1 updates Secrets Manager only. It does not restart applications.

After renewal, tell the application owner:

- app name
- spoke account
- secret path
- new expiry date

Typical follow-up:

| Deployment type | Likely action |
| --- | --- |
| `ec2` | restart service or run the app's certificate refresh process |
| `ecs` | force a new service deployment or use the standard app deployment process |

Application teams own reload and runtime verification.

## Check Lambda logs

The expiry checker log group is:

```text
/aws/lambda/scip-cert-expiry-checker
```

Run in the shared-services account:

```bash
aws logs describe-log-streams \
  --log-group-name /aws/lambda/scip-cert-expiry-checker \
  --region eu-west-2 \
  --order-by LastEventTime \
  --descending \
  --max-items 5
```

Healthy app log:

```json
{"status": "ok", "app_name": "b2bi-preprodc", "account_name": "preprodc", "days_left": 45, "expiry_date": "2026-06-30T12:00:00Z"}
```

Run summary:

```json
{"summary": {"checked": 4, "ok": 2, "renewal_needed": 1, "p1_action_required": 0, "errors": 1}}
```

The Lambda must not log PEM bodies, private keys, Bitbucket tokens, AWS credentials, or full `SecretString` values.

## Roll back a bad certificate

Only roll back when the newly issued certificate is wrong. The previous version may be closer to expiry.

1. List versions:

   ```bash
   aws secretsmanager list-secret-version-ids \
     --secret-id /scip/certs/b2bi-preprodc \
     --region eu-west-2 \
     --query 'Versions[*].{VersionId:VersionId,Labels:VersionStages}'
   ```

2. Confirm the previous version's common name and expiry without printing the key.
3. Promote the previous version:

   ```bash
   aws secretsmanager update-secret-version-stage \
     --secret-id /scip/certs/b2bi-preprodc \
     --version-stage AWSCURRENT \
     --move-to-version-id <previous-version-id> \
     --remove-from-version-id <current-version-id> \
     --region eu-west-2
   ```

4. Coordinate application reload.
5. Correct the catalogue or Vault configuration and re-issue.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `APP_NAME ... not found` | Wrong product team, environment, or app name | Search `scip/cert-lifecycle/certs/` for the exact `name` |
| Duplicate app names | Catalogue contains repeated `name` | Rename or remove duplicate and run the validator |
| Account mismatch from Ansible | `deployment.account_id` is wrong or Jenkins assumed the wrong account | Correct the catalogue or role assumption |
| STS `AccessDenied` assuming `jagent-ec2-role` | Missing role or trust policy in spoke | Fix `jagent-ec2-role` trust |
| Secrets Manager `AccessDenied` during issuance | Missing jagent write policy | Apply `spoke-account-jagent-policy.json` or enable Terraform issuer permissions where appropriate |
| Lambda `Secret not found` | Certificate has not been issued yet | Run the Jenkins issuance job |
| Lambda KMS decrypt error | Secret uses a customer-managed key without role decrypt access | Add the KMS addon policy or `kms_key_arns` in spoke Terraform |
| Lambda Bitbucket 401 | Token missing, expired, or wrong secret format | Update `/scip/cert-lifecycle/bitbucket-token` with `{"token":"..."}` |
| SNS publish failure | Wrong topic ARN or missing Lambda permission | Check Lambda env vars and execution-role policy |
| Invalid PEM | Secret payload is corrupt or not a PEM certificate | Re-issue the certificate |

## Security

Safe to share:

- app name
- account name and account ID
- secret path
- expiry date and days remaining
- Jenkins build URL after checking logs for secret material

Never share:

- private keys
- PEM certificate bodies
- full `SecretString` payloads
- Vault tokens
- Bitbucket tokens
- AWS temporary credentials

If secret material appears in logs, treat it as a security incident.
