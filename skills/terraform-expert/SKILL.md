---
name: terraform-expert
description: Use when working with .tf/.tofu/.tfvars files, HCL, terraform or tofu CLI commands, providers, modules, remote state/backends, tfstate, or plan/apply pipelines. Writes and refactors Terraform 1.9+/OpenTofu configurations, designs reusable modules, performs safe state surgery, and wires CI plan/apply workflows. Invoke for authoring resources or modules, migrating backends or state, converting count to for_each, importing existing infrastructure, handling secrets in IaC, or setting up PR-plan/merge-apply pipelines.
license: MIT
metadata:
  version: "0.1.0"
  category: infra
  frameworks: "Terraform 1.9+, OpenTofu 1.8+"
  triggers: terraform, opentofu, tofu, hcl, tfstate, tfvars, provider, module, backend, remote state, plan, apply, for_each, count, lifecycle, moved block, import block, tflint, drift
  related: nestjs-expert, fastapi-expert
---

# Terraform Expert

Turns Claude into a senior platform engineer who ships Terraform 1.9+/OpenTofu-compatible HCL with safe state management, contract-driven modules, and plan-gated delivery.

## When to Use This Skill

- Author or refactor resources, data sources, and variables in `.tf` files
- Design reusable modules with typed variable/output contracts and version pinning
- Configure or migrate remote state backends (S3 with native lockfile, HTTP, cloud)
- Rename/move/import resources without destroying them (`moved`, `import`, `removed` blocks)
- Convert `count` to `for_each` or restructure collections without replacement
- Keep secrets out of state and plaintext (sensitive/ephemeral values, external stores)
- Set up CI: fmt/validate/tflint gates, plan-on-PR, apply-on-merge, drift detection

## Core Workflow

1. **Analyze** - read `versions.tf`/`terraform` blocks (required_version, provider constraints), the backend config, existing module structure, and naming/tagging conventions. Run `terraform providers` and `terraform state list` (read-only) to understand what exists. Determine whether the project uses Terraform or OpenTofu (`tofu` CLI, `.tofu` files) and match it.
2. **Implement** - write HCL matching the project's layout. Prefer `for_each` keyed on stable strings, pin provider versions with `~>` constraints, express refactors as `moved`/`import`/`removed` blocks instead of CLI state commands, and mark secret inputs `sensitive = true` (never literal secrets in `.tf` or `.tfvars`).
3. **Verify format** - run `terraform fmt -check -recursive` (or `tofu fmt`); if it reports files, run `terraform fmt -recursive`, fix all reported issues, and re-run until clean.
4. **Verify configuration** - run `terraform validate` (after `terraform init -backend=false` if init hasn't run); fix all reported errors and re-run until clean.
5. **Lint** - run `tflint --recursive` (init rulesets with `tflint --init` if needed); fix all reported issues and re-run until clean. Do not blanket-disable rules to silence findings.
6. **Plan - mandatory gate before any apply** - run `terraform plan -out=tfplan` and read the full plan output. Confirm every `create`/`update` is intended, and treat any **destroy** or **replace** (`-/+`, "must be replaced", "forced replacement") line as a stop: apply is blocked until a human explicitly reviews and approves those lines. If the plan shows unintended destroys/replacements, fix the config (usually a `moved` block, `lifecycle` argument, or restored `for_each` key) and re-plan until the plan contains only intended actions.
7. **Apply and prove it works** - only after the plan gate passes, run `terraform apply tfplan` (the saved plan, never a fresh auto-approved plan). Then verify reality: check outputs, query the created infrastructure, and run `terraform plan` again - a clean follow-up plan ("No changes") proves convergence; if it still shows diffs, fix the drift or config and re-run until clean.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Remote backends, state locking, state surgery | `references/state-and-backends.md` | Configuring/migrating a backend, S3 + lockfile setup, renaming/moving/importing/forgetting resources, workspaces, state file questions |
| Module design, variable/output contracts, versioning | `references/modules.md` | Creating or refactoring a module, typed variables with validation, optional() defaults, module sources and version pinning, provider passing |
| for_each vs count, lifecycle meta-arguments | `references/foreach-lifecycle.md` | Any resource collection, converting count to for_each, unwanted destroy/replace in plans, create_before_destroy, prevent_destroy, ignore_changes, replace_triggered_by |
| Secrets, sensitive values, security posture | `references/secrets-and-security.md` | Any credential/API key/password in config, secrets appearing in state or plan output, ephemeral values, write-only arguments, external secret stores |
| CI pipelines, plan review, drift detection | `references/ci-workflows.md` | Setting up plan-on-PR/apply-on-merge, GitHub Actions or GitLab CI for Terraform, OIDC cloud auth, scheduled drift detection, plan artifacts |

## Key Patterns

**Config-driven state surgery - never `terraform state mv` by hand:**

```hcl
moved {
  from = aws_instance.app
  to   = aws_instance.app["primary"]   # count -> for_each rename, no destroy
}

import {
  to = aws_s3_bucket.logs
  id = "acme-prod-logs"                # adopt existing infra via plan/apply
}

removed {
  from = aws_iam_user.legacy
  lifecycle { destroy = false }        # forget from state, keep the real resource
}
```

**for_each keyed on stable strings (indexes shift; keys don't):**

```hcl
variable "subnets" {
  type = map(object({ cidr = string, az = string }))
}

resource "aws_subnet" "this" {
  for_each          = var.subnets     # keys: "public-a", "private-a", ...
  vpc_id            = aws_vpc.main.id
  cidr_block        = each.value.cidr
  availability_zone = each.value.az
}
```

**Version pinning - providers get `~>`, modules get exact or `~>`:**

```hcl
terraform {
  required_version = ">= 1.9.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.0"                  # never unpinned registry modules
}
```

**Cross-variable validation (Terraform 1.9+):**

```hcl
variable "instance_count" {
  type = number
}

variable "azs" {
  type = list(string)
  validation {
    condition     = var.instance_count <= length(var.azs)
    error_message = "instance_count cannot exceed the number of AZs."
  }
}
```

## Common Mistakes

- **Applying without reviewing the plan** - `terraform apply -auto-approve` with no saved plan is how production gets destroyed. Always `plan -out=tfplan`, human-review every destroy/replace line, then `apply tfplan`.
- **Switching `count` to `for_each` (or reordering a list) without `moved` blocks** - the plan destroys `resource[1]` and creates `resource["name"]` because state addresses changed, not the infrastructure. Write one `moved` block per element before planning.
- **Editing state with CLI commands (`state mv`, `state rm`, `terraform import`)** - these mutate state immediately with no plan preview and don't survive code review. Use `moved`, `removed`, and `import` blocks so the change is visible in the plan and in the PR.
- **Treating a data source as a dependency-free lookup** - `data` blocks read existing infrastructure at plan time and fail if it doesn't exist yet; they do not create anything. If this config manages the object, reference the resource directly; never pair a resource with a data source for the same object in one config.
- **Secrets in `.tfvars`, locals, or resource arguments** - they land in plaintext state and plan files. Mark variables `sensitive = true`, prefer ephemeral values/write-only arguments (Terraform 1.10/1.11+), and fetch from a secret store at runtime; never commit them.
- **Unpinned providers or modules** - a missing `version` constraint means the next `init -upgrade` can pull a breaking major and the plan silently changes. Pin providers `~> MAJOR.MINOR` and commit `.terraform.lock.hcl`.
- **`ignore_changes` as a drift band-aid** - ignoring an argument hides real configuration divergence forever. Use it only for fields legitimately mutated outside Terraform (e.g., autoscaled `desired_count`), and document why.
- **Assuming DynamoDB is required for S3 state locking** - since Terraform 1.10/1.11, `use_lockfile = true` on the S3 backend provides native locking via a lock object; DynamoDB-based locking is legacy.
