# SCIP Certificate Lifecycle — Terraform helper targets
#
# Usage:
#   make tf-help
#   make tf-plan    TARGET_TYPE=shared ENVIRONMENT=preprod
#   make tf-plan    TARGET_TYPE=spoke  ENVIRONMENT=dev     SPOKE_ACCOUNT_NAME=devc
#   make tf-plan    TARGET_TYPE=spoke  ENVIRONMENT=test    SPOKE_ACCOUNT_NAME=testc
#   make tf-plan    TARGET_TYPE=spoke  ENVIRONMENT=preprod SPOKE_ACCOUNT_NAME=preprodc
#   make tf-plan    TARGET_TYPE=spoke  ENVIRONMENT=prod    SPOKE_ACCOUNT_NAME=prodd
#   make tf-apply   TARGET_TYPE=spoke  ENVIRONMENT=preprod SPOKE_ACCOUNT_NAME=preprodc
#   make tf-destroy TARGET_TYPE=spoke  ENVIRONMENT=dev     SPOKE_ACCOUNT_NAME=devc CONFIRM_DESTROY=true
#
# AWS credentials must already be active in the shell (instance profile, aws-vault, etc.).
# Do not hardcode credentials here.
#
# Valid spoke accounts per environment:
#   dev:     Dev deva devb devc devd deve devf devg
#   test:    testa testb testc testd teste testf testg
#   preprod: preproda preprodb preprodc preprodd preprode preprodf preprodg
#   prod:    prodd prode prodf prodg prodh prodi prodj
#
# Shared-services accounts (TARGET_TYPE=shared):
#   preprod: preprod
#   prod:    prodc
#
# Note: dev and test have no shared-services account.
#       TARGET_TYPE=shared is only valid with ENVIRONMENT=preprod or prod.

TARGET_TYPE        ?= shared
ENVIRONMENT        ?= dev
SPOKE_ACCOUNT_NAME ?=
AUTO_APPROVE       ?= false
CONFIRM_DESTROY    ?= false

# ── Terraform root ────────────────────────────────────────────────────────────

ifeq ($(TARGET_TYPE),shared)
  _TF_ROOT := terraform/shared-services
else ifeq ($(TARGET_TYPE),spoke)
  _TF_ROOT := terraform/spoke
else
  $(error TARGET_TYPE must be 'shared' or 'spoke'. Got: '$(TARGET_TYPE)')
endif

TF_ROOT ?= $(_TF_ROOT)

# ── Var file (relative to TF_ROOT; override with an absolute path) ────────────

ifeq ($(TARGET_TYPE),shared)
  _DEFAULT_VAR_FILE := envs/$(ENVIRONMENT).tfvars
else
  _DEFAULT_VAR_FILE := envs/$(ENVIRONMENT)-$(SPOKE_ACCOUNT_NAME).tfvars
endif

TF_VAR_FILE ?= $(_DEFAULT_VAR_FILE)

# ── Backend config (relative to TF_ROOT; operator-created, not committed) ─────

ifeq ($(TARGET_TYPE),shared)
  _DEFAULT_BACKEND_CFG := envs/$(ENVIRONMENT)-backend.hcl
else
  _DEFAULT_BACKEND_CFG := envs/$(ENVIRONMENT)-$(SPOKE_ACCOUNT_NAME)-backend.hcl
endif

BACKEND_CFG ?= $(_DEFAULT_BACKEND_CFG)

# ── Auto-approve ──────────────────────────────────────────────────────────────

ifeq ($(AUTO_APPROVE),true)
  _AUTO_APPROVE_FLAG := -auto-approve
else
  _AUTO_APPROVE_FLAG :=
endif

.PHONY: tf-help tf-fmt tf-fmt-check tf-init tf-validate tf-plan tf-apply tf-destroy tf-clean

tf-help: ## Print targets, examples, and current variable values
	@printf '\nSCIP Cert Lifecycle — Terraform targets\n\n'
	@printf 'Examples:\n'
	@printf '  make tf-fmt-check\n'
	@printf '  make tf-plan    TARGET_TYPE=shared ENVIRONMENT=preprod\n'
	@printf '  make tf-plan    TARGET_TYPE=shared ENVIRONMENT=prod\n'
	@printf '  make tf-plan    TARGET_TYPE=spoke  ENVIRONMENT=dev     SPOKE_ACCOUNT_NAME=devc\n'
	@printf '  make tf-plan    TARGET_TYPE=spoke  ENVIRONMENT=test    SPOKE_ACCOUNT_NAME=testc\n'
	@printf '  make tf-plan    TARGET_TYPE=spoke  ENVIRONMENT=preprod SPOKE_ACCOUNT_NAME=preprodc\n'
	@printf '  make tf-plan    TARGET_TYPE=spoke  ENVIRONMENT=prod    SPOKE_ACCOUNT_NAME=prodd\n'
	@printf '  make tf-apply   TARGET_TYPE=spoke  ENVIRONMENT=preprod SPOKE_ACCOUNT_NAME=preprodc\n'
	@printf '  make tf-destroy TARGET_TYPE=spoke  ENVIRONMENT=dev     SPOKE_ACCOUNT_NAME=devc CONFIRM_DESTROY=true\n'
	@printf '\nShared-services accounts (TARGET_TYPE=shared):\n'
	@printf '  preprod: preprod account    prod: prodc account\n'
	@printf '  (dev and test have no shared-services account)\n'
	@printf '\nValid spoke accounts per environment:\n'
	@printf '  dev:     Dev deva devb devc devd deve devf devg\n'
	@printf '  test:    testa testb testc testd teste testf testg\n'
	@printf '  preprod: preproda preprodb preprodc preprodd preprode preprodf preprodg\n'
	@printf '  prod:    prodd prode prodf prodg prodh prodi prodj\n'
	@printf '\nTargets:\n'
	@printf '  %-20s %s\n' tf-help          'Print this help'
	@printf '  %-20s %s\n' tf-fmt           'Format all Terraform files recursively'
	@printf '  %-20s %s\n' tf-fmt-check     'Check Terraform formatting (no changes written)'
	@printf '  %-20s %s\n' tf-init          'Initialise Terraform with backend config'
	@printf '  %-20s %s\n' tf-validate      'Validate Terraform configuration'
	@printf '  %-20s %s\n' tf-plan          'Plan changes and save to tfplan'
	@printf '  %-20s %s\n' tf-apply         'Apply the saved tfplan (run tf-plan first)'
	@printf '  %-20s %s\n' tf-destroy       'Plan and apply a destroy (requires CONFIRM_DESTROY=true)'
	@printf '  %-20s %s\n' tf-clean         'Remove plan files and .terraform/ from TF_ROOT'
	@printf '\nCurrent values:\n'
	@printf '  %-22s = %s\n' TARGET_TYPE        '$(TARGET_TYPE)'
	@printf '  %-22s = %s\n' ENVIRONMENT        '$(ENVIRONMENT)'
	@printf '  %-22s = %s\n' SPOKE_ACCOUNT_NAME '$(SPOKE_ACCOUNT_NAME)'
	@printf '  %-22s = %s\n' TF_ROOT            '$(TF_ROOT)'
	@printf '  %-22s = %s  (relative to TF_ROOT)\n' TF_VAR_FILE  '$(TF_VAR_FILE)'
	@printf '  %-22s = %s  (relative to TF_ROOT)\n' BACKEND_CFG  '$(BACKEND_CFG)'
	@printf '  %-22s = %s\n' AUTO_APPROVE       '$(AUTO_APPROVE)'
	@printf '  %-22s = %s\n' CONFIRM_DESTROY    '$(CONFIRM_DESTROY)'
	@printf '\n'

tf-fmt: ## Format all Terraform files recursively
	terraform fmt -recursive

tf-fmt-check: ## Check Terraform formatting without modifying files
	terraform fmt -check -recursive

tf-init: ## Initialise Terraform with backend config for the target environment
	@if [ "$(TARGET_TYPE)" = "spoke" ] && [ -z "$(SPOKE_ACCOUNT_NAME)" ]; then \
	  printf '\nError: SPOKE_ACCOUNT_NAME is required when TARGET_TYPE=spoke.\n\n'; \
	  exit 1; \
	fi
	terraform -chdir=$(TF_ROOT) init -backend-config=$(BACKEND_CFG)

tf-validate: ## Validate Terraform configuration (run tf-init first)
	@if [ "$(TARGET_TYPE)" = "spoke" ] && [ -z "$(SPOKE_ACCOUNT_NAME)" ]; then \
	  printf '\nError: SPOKE_ACCOUNT_NAME is required when TARGET_TYPE=spoke.\n\n'; \
	  exit 1; \
	fi
	terraform -chdir=$(TF_ROOT) validate

tf-plan: ## Plan Terraform changes and save output to tfplan
	@if [ "$(TARGET_TYPE)" = "spoke" ] && [ -z "$(SPOKE_ACCOUNT_NAME)" ]; then \
	  printf '\nError: SPOKE_ACCOUNT_NAME is required when TARGET_TYPE=spoke.\n\n'; \
	  exit 1; \
	fi
	terraform -chdir=$(TF_ROOT) plan \
	  -var-file=$(TF_VAR_FILE) \
	  -out=tfplan

tf-apply: ## Apply the saved tfplan (run tf-plan first)
	@if [ "$(TARGET_TYPE)" = "spoke" ] && [ -z "$(SPOKE_ACCOUNT_NAME)" ]; then \
	  printf '\nError: SPOKE_ACCOUNT_NAME is required when TARGET_TYPE=spoke.\n\n'; \
	  exit 1; \
	fi
	@if [ ! -f "$(TF_ROOT)/tfplan" ]; then \
	  printf '\nError: %s/tfplan not found. Run make tf-plan first.\n\n' '$(TF_ROOT)'; \
	  exit 1; \
	fi
	terraform -chdir=$(TF_ROOT) apply $(_AUTO_APPROVE_FLAG) tfplan

tf-destroy: ## Plan and apply a destroy. Requires CONFIRM_DESTROY=true.
	@if [ "$(TARGET_TYPE)" = "spoke" ] && [ -z "$(SPOKE_ACCOUNT_NAME)" ]; then \
	  printf '\nError: SPOKE_ACCOUNT_NAME is required when TARGET_TYPE=spoke.\n\n'; \
	  exit 1; \
	fi
	@if [ "$(CONFIRM_DESTROY)" != "true" ]; then \
	  printf '\nError: tf-destroy requires explicit confirmation.\n\n'; \
	  printf 'Rerun with CONFIRM_DESTROY=true:\n\n'; \
	  printf '  make tf-destroy TARGET_TYPE=%s ENVIRONMENT=%s%s CONFIRM_DESTROY=true\n\n' \
	    '$(TARGET_TYPE)' '$(ENVIRONMENT)' \
	    '$(if $(SPOKE_ACCOUNT_NAME), SPOKE_ACCOUNT_NAME=$(SPOKE_ACCOUNT_NAME))'; \
	  exit 1; \
	fi
	terraform -chdir=$(TF_ROOT) plan -destroy \
	  -var-file=$(TF_VAR_FILE) \
	  -out=tfdestroy
	terraform -chdir=$(TF_ROOT) apply $(_AUTO_APPROVE_FLAG) tfdestroy

tf-clean: ## Remove plan files and .terraform/ directory from the target root
	rm -f $(TF_ROOT)/tfplan $(TF_ROOT)/tfdestroy
	rm -rf $(TF_ROOT)/.terraform
