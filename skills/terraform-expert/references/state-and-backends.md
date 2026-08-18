# State and Backends (Terraform 1.9+ / OpenTofu)

State maps config addresses to real infrastructure. Every state mistake is an
outage risk, so all state changes must go through plan/apply - never direct
CLI mutation.

## Remote backend: S3 with native lockfile

Since Terraform 1.10 (GA in 1.11) the S3 backend locks state with a native
S3 lock object. DynamoDB-based locking still works but is legacy - do not add
a DynamoDB table to new configs.

```hcl
terraform {
  backend "s3" {
    bucket       = "acme-tfstate-prod"
    key          = "network/prod/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true   # native S3 locking; no DynamoDB table needed
    encrypt      = true   # SSE on the state object
  }
}
```

Bucket requirements:

- Versioning **enabled** (state history is your undo button)
- Default encryption (SSE-KMS with a CMK for prod)
- Block Public Access on; bucket policy restricted to the CI role and admins
- The locking IAM permissions: `s3:PutObject`/`s3:DeleteObject`/`s3:GetObject`
  on both `<key>` and `<key>.tflock`

Migrating from DynamoDB locking: add `use_lockfile = true`, run
`terraform init -reconfigure`, confirm a plan acquires the `.tflock` object,
then remove `dynamodb_table` from the backend block and re-init.

## Partial configuration per environment

Keep the backend block minimal and inject environment specifics at init, so
one config serves dev/stage/prod:

```hcl
terraform {
  backend "s3" {}
}
```

```bash
terraform init -backend-config=backends/prod.s3.tfbackend
# backends/prod.s3.tfbackend:
#   bucket       = "acme-tfstate-prod"
#   key          = "network/terraform.tfstate"
#   region       = "us-east-1"
#   use_lockfile = true
#   encrypt      = true
```

Changing any backend setting requires `terraform init -migrate-state`
(copies state to the new backend) or `-reconfigure` (points at it without
copying - only when the state already lives there).

## Workspaces: use sparingly

CLI workspaces share one backend and one config; they are fine for ephemeral
review environments but a poor fit for dev/prod isolation (same credentials,
same blast radius, easy to apply to the wrong one). Prefer separate state
keys/root modules per environment. If workspaces are used, gate on
`terraform workspace show` in CI before every plan.

## State surgery: config-driven blocks, not CLI

The CLI commands `terraform state mv`, `terraform state rm`, and legacy
`terraform import` mutate state immediately, skip plan review, and leave no
trace in the PR. Use the declarative blocks instead - they show up in
`terraform plan` and are reviewed like any other change.

### Rename / restructure: `moved`

```hcl
# Resource renamed
moved {
  from = aws_security_group.web
  to   = aws_security_group.frontend
}

# Resource moved into a module
moved {
  from = aws_cloudwatch_log_group.app
  to   = module.observability.aws_cloudwatch_log_group.app
}

# count -> for_each conversion (one block per index)
moved {
  from = aws_instance.app[0]
  to   = aws_instance.app["primary"]
}
```

Plan output shows `# aws_security_group.frontend has moved to ...` with no
destroy. Keep `moved` blocks in the config for at least one release cycle so
every consumer of a shared module gets the migration; then delete them.

### Adopt existing infrastructure: `import` blocks

```hcl
import {
  to = aws_s3_bucket.logs
  id = "acme-prod-logs"
}

# Bulk import with for_each (Terraform 1.7+)
import {
  for_each = var.existing_zone_ids
  to       = aws_route53_zone.this[each.key]
  id       = each.value
}
```

Workflow: write the `import` block, run
`terraform plan -generate-config-out=generated.tf` if you need a starting
config, reconcile the generated HCL with your standards, then plan - the
import appears as `# ... will be imported` - and apply. Delete the `import`
block after it lands.

### Forget without destroying: `removed`

```hcl
removed {
  from = aws_iam_user.legacy
  lifecycle {
    destroy = false   # drop from state, keep the real resource
  }
}
```

With `destroy = false` the plan says "will no longer be managed"; without it,
removal from config schedules a real destroy. This replaces
`terraform state rm`.

## Reading state safely

Read-only commands are always allowed and useful during analysis:

```bash
terraform state list                       # all addresses in state
terraform state show aws_s3_bucket.logs    # one resource's attributes
terraform output -json                     # root outputs
```

Never hand-edit the state JSON. If state is corrupted, restore a previous
version from S3 bucket versioning, then reconcile with `import`/`removed`
blocks.

## Cross-state references

Prefer explicit data sources (`aws_vpc` by tag, SSM parameters written by the
producing stack) over `terraform_remote_state`, which couples consumers to
the producer's entire state file and requires read access to it. If
`terraform_remote_state` is already in use, treat its outputs as the contract
and never reach into resource attributes.

## OpenTofu divergences

- `tofu` CLI is command-compatible; `.tofu` file extension wins over `.tf`
  when both exist.
- OpenTofu supports client-side **state encryption**
  (`terraform { encryption { ... } }`) - key material from PBKDF2, AWS KMS,
  or GCP KMS; encrypts state and plan files at rest. Terraform has no
  equivalent; don't add the block to configs that must run on both.
- S3 `use_lockfile` is supported by both (OpenTofu 1.10+).
