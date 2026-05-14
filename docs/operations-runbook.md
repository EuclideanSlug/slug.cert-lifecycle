# Operations Runbook

Use this runbook to issue or renew certificates, respond to SNS alerts, verify Secrets Manager versions, and troubleshoot failures.

## Alert response

| Alert | Meaning | Action |
| --- | --- | --- |
| `[CERT RENEWAL NEEDED]` | 15-30 days remaining | confirm the auto-triggered Jenkins renewal completes, or run Jenkins manually if the trigger failed or was skipped unexpectedly |
| `[CERT P1 - ACTION REQUIRED] ... expires in N days` | 1-14 days remaining | renew today |
| `[CERT P1 - ACTION REQUIRED] ... expired N days ago` | expired | renew immediately and escalate if blocked |

The alert body includes the application name, account, expiry date, Jenkins job details, `PRODUCT_TEAM`, `ENVIRONMENT`, and `APP_NAME` values. Renewal-needed alerts also include the Jenkins auto-trigger status.

## Scheduled renewal trigger

EventBridge Scheduler invokes the expiry checker Lambda once per day at 07:30 `Europe/London`.

The Lambda remains the component that iterates through catalogues, assumes spoke roles, reads `/slug/certs/{app.name}`, parses the actual PEM expiry, and applies the threshold rules:

| Days remaining | Action |
| --- | --- |
| `> 30` | log only |
| `15..30` | trigger Jenkins renewal and publish `[CERT RENEWAL NEEDED]` |
| `<= 14` | publish `[CERT P1 - ACTION REQUIRED]` |

For Jenkins auto-renewal, the Lambda derives `PRODUCT_TEAM` and `ENVIRONMENT` from the catalogue filename and passes `APP_NAME=<catalogue app name>`. Before triggering, it checks Jenkins queue and running builds for the same parameters. If a matching build is already in flight, it skips the duplicate trigger and logs the skip.

Failed Jenkins trigger attempts are not durably suppressed. If the certificate still has 15-30 days remaining on the next daily run, the Lambda tries again. The SNS renewal-needed notification is still sent so operators can intervene.

## Issue or renew one certificate

Manual Jenkins execution remains supported for initial certificate creation, manual renewal, and break-glass use.

1. Open the Jenkins certificate issuance job.
2. Select:

| Parameter | Value |
| --- | --- |
| `PRODUCT_TEAM` | Product team prefix from the catalogue filename, for example `PT2` |
| `ENVIRONMENT` | `dev`, `test`, `preprod`, or `prod` |
| `APP_NAME` | Full catalogue `name`, for example `payments-api-preprodc` |

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
  --secret-id /slug/certs/payments-api-preprodc \
  --region eu-west-2 \
  --query 'VersionIdsToStages'
```

Expected result: the latest version has `AWSCURRENT`; the previous version usually has `AWSPREVIOUS`.

To check the certificate expiry without printing the private key:

```bash
aws secretsmanager get-secret-value \
  --secret-id /slug/certs/payments-api-preprodc \
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

Certificate renewal updates Secrets Manager only. It does not restart applications.

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
/aws/lambda/slug-cert-expiry-checker
```

Run in the shared-services account:

```bash
aws logs describe-log-streams \
  --log-group-name /aws/lambda/slug-cert-expiry-checker \
  --region eu-west-2 \
  --order-by LastEventTime \
  --descending \
  --max-items 5
```

Healthy app log:

```json
{"status": "ok", "app_name": "payments-api-preprodc", "account_name": "preprodc", "days_left": 45, "expiry_date": "2026-06-30T12:00:00Z"}
```

Run summary:

```json
{"summary": {"checked": 4, "ok": 2, "renewal_needed": 1, "p1_action_required": 0, "jenkins_triggered": 1, "jenkins_skipped": 0, "jenkins_trigger_failed": 0, "errors": 1}}
```

The Lambda must not log PEM bodies, private keys, Bitbucket tokens, Jenkins tokens, AWS credentials, or full `SecretString` values.

## Jenkins trigger credential

The Lambda reads Jenkins trigger credentials from Secrets Manager:

```text
/slug/cert-lifecycle/jenkins-trigger
```

Expected secret value:

```json
{"username":"<jenkins-user>","api_token":"<jenkins-api-token>"}
```

The Jenkins identity should have permission to read the job state, inspect queue/running builds, and trigger the certificate issuance job with parameters. Do not put this credential in Terraform variables, Jenkinsfiles, shell history, or tickets.

## Roll back a bad certificate

Only roll back when the newly issued certificate is wrong. The previous version may be closer to expiry.

1. List versions:

   ```bash
   aws secretsmanager list-secret-version-ids \
     --secret-id /slug/certs/payments-api-preprodc \
     --region eu-west-2 \
     --query 'Versions[*].{VersionId:VersionId,Labels:VersionStages}'
   ```

2. Confirm the previous version's common name and expiry without printing the key.
3. Promote the previous version:

   ```bash
   aws secretsmanager update-secret-version-stage \
     --secret-id /slug/certs/payments-api-preprodc \
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
| `APP_NAME ... not found` | Wrong product team, environment, or app name | Search `slug/cert-lifecycle/certs/` for the exact `name` |
| Duplicate app names | Catalogue contains repeated `name` | Rename or remove duplicate and run the validator |
| Account mismatch from Ansible | `deployment.account_id` is wrong or Jenkins assumed the wrong account | Correct the catalogue or role assumption |
| STS `AccessDenied` assuming `jagent-ec2-role` | Missing role or trust policy in spoke | Fix `jagent-ec2-role` trust |
| Secrets Manager `AccessDenied` during issuance | Missing jagent write policy | Apply `spoke-account-jagent-policy.json` or enable Terraform issuer permissions where appropriate |
| Lambda `Secret not found` | Certificate has not been issued yet | Run the Jenkins issuance job |
| Lambda KMS decrypt error | Secret uses a customer-managed key without role decrypt access | Add the KMS addon policy or `kms_key_arns` in spoke Terraform |
| Lambda Bitbucket 401 | Token missing, expired, or wrong secret format | Update `/slug/cert-lifecycle/bitbucket-token` with `{"token":"..."}` |
| Lambda invocation fails with no apps loaded | All configured catalogue URLs failed or returned no `apps` list | Check `BITBUCKET_CATALOGUE_URLS`, token access, and catalogue file paths |
| SNS publish failure | Wrong topic ARN or missing Lambda permission | Check Lambda env vars and execution-role policy |
| Jenkins trigger failed | Jenkins credential missing/expired, job URL wrong, network blocked, CSRF crumb failure, or Jenkins rejected the build | Check `/slug/cert-lifecycle/jenkins-trigger`, `JENKINS_JOB_URL`, Lambda logs, and Jenkins access logs; the next daily run retries if still in the renewal window |
| Jenkins trigger skipped | Matching queued or running build already exists | Confirm the existing Jenkins build completes and updates the secret |
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
- Jenkins usernames or tokens
- AWS temporary credentials

If secret material appears in logs, treat it as a security incident.
