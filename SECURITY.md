# Security Policy

Do not open public issues containing vulnerability details, credentials, private keys, certificate bodies, account IDs, or sensitive deployment information.

Report security issues privately through GitHub private vulnerability reporting if it is enabled for this repository. If it is not enabled, contact the repository owner outside the public issue tracker.

Before deploying a fork or copy:

- replace all `slug` example prefixes with your platform prefix
- replace example account suffixes, Jenkins labels, and product-team names
- keep real `.tfvars`, backend files, Terraform state, certificate material, and tokens out of Git
- set Bitbucket token values manually in Secrets Manager, not in Terraform
- review IAM trust relationships and resource ARNs for your own AWS accounts
