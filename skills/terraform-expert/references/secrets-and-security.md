# Secrets and Security in Terraform

Baseline fact: **anything a resource argument or output touches is written to
state in plaintext** (and often to plan files). `sensitive = true` only
redacts CLI output - it does not encrypt anything. Design so secrets either
never enter state or enter it as references, not values.

## The hierarchy (best first)

1. **Never in Terraform at all** - the app fetches the secret at runtime
   from a secret store by name/ARN; Terraform only manages the store entry's
   *shell* and IAM access to it.
2. **Ephemeral / write-only** (Terraform 1.10/1.11+) - secret flows through
   an apply without persisting in state or plan.
3. **Sensitive-marked, state-resident** - acceptable only with an encrypted,
   access-controlled backend; the secret is in state, plan accordingly.
4. **Plaintext in .tf / .tfvars / VCS** - never. This is an incident.

## sensitive variables and outputs

```hcl
variable "db_password" {
  type      = string
  sensitive = true
  nullable  = false
}

output "connection_string" {
  value     = "postgres://app:${var.db_password}@${aws_db_instance.main.address}/app"
  sensitive = true   # required: derived values inherit sensitivity
}
```

- Sensitivity propagates: any expression using a sensitive value is
  sensitive; outputs exposing one must declare `sensitive = true` or
  validation fails.
- Redaction covers plan/apply display only. `terraform output -json` and the
  raw state still show the value - restrict who can read state.
- Feed values via environment (`TF_VAR_db_password`) or CI-injected
  variables, never a committed `.tfvars`. Add `*.tfvars` with secrets and
  `*.tfstate*` to `.gitignore` unconditionally.

## Ephemeral values and write-only arguments (1.10/1.11+)

Ephemeral constructs exist during a single run and are never persisted:

```hcl
variable "db_password" {
  type      = string
  ephemeral = true          # cannot be stored in state or plan
}

# Ephemeral resource: fetched fresh each run, not recorded in state
ephemeral "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
}

# Write-only argument (provider-specific *_wo pairs): sent to the API,
# never written to state; bump the version to rotate.
resource "aws_db_instance" "main" {
  # ...
  password_wo         = ephemeral.aws_secretsmanager_secret_version.db.secret_string
  password_wo_version = 1
}
```

Rules: ephemeral values may only flow into other ephemeral contexts or
write-only (`*_wo`) arguments - assigning one to a normal argument is an
error. OpenTofu 1.8 does not support ephemerals; check the target runtime
before using them in dual-runtime modules.

## External secret stores

Manage the container, not the secret value:

```hcl
resource "aws_secretsmanager_secret" "db" {
  name = "prod/app/db"
}

# Value is set out-of-band (console, rotation lambda, CI step) - NOT via
# aws_secretsmanager_secret_version with a literal, which would put the
# secret in both config and state.

data "aws_iam_policy_document" "read_db_secret" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.db.arn]
  }
}
```

If a `data "aws_secretsmanager_secret_version"` (or Vault `vault_generic_secret`)
must be read in-config, know that the fetched value lands in state; prefer
the ephemeral form above on Terraform 1.10+, or pass the secret's ARN/name
to the consumer (ECS `secrets`, Lambda env via SSM reference) so resolution
happens at runtime, outside Terraform.

Generated secrets: `random_password` stores its result in state. Acceptable
for bootstrap only if state is encrypted and tightly scoped; write it
straight into the secret store and rotate after creation.

## Protecting state itself

- S3 backend: `encrypt = true`, SSE-KMS with a customer-managed key,
  versioning on, Block Public Access, bucket policy allowing only the CI
  role and break-glass admins. State read access == secret read access.
- OpenTofu: add client-side state encryption for defense in depth:

```hcl
terraform {
  encryption {
    key_provider "aws_kms" "main" {
      kms_key_id = "arn:aws:kms:us-east-1:111111111111:key/..."
      key_spec   = "AES_256"
    }
    method "aes_gcm" "main" { keys = key_provider.aws_kms.main }
    state { method = method.aes_gcm.main }
    plan  { method = method.aes_gcm.main }
  }
}
```

- Plan files (`-out=tfplan`) contain every sensitive value unencrypted.
  Treat plan artifacts in CI as secrets: short retention, restricted
  download, never in logs.

## Provider credentials

- Never put `access_key`/`secret_key`/`token` in provider blocks. Use
  ambient auth: OIDC federation in CI (short-lived, no stored keys),
  instance/task roles on compute, SSO profiles locally.
- Scope the CI role to what the config manages; separate plan (read-mostly)
  and apply roles where the platform supports it.

## Scanning and hygiene

- Run `tflint` plus a policy scanner (`trivy config` or `checkov -d .`) in
  CI; fix or explicitly waive findings with a reason - no blanket skips.
- Add a secret scanner (gitleaks/trufflehog) to pre-commit and CI: catches
  the literal-in-tfvars mistake before it lands in history.
- If a secret ever reaches state or VCS: **rotate it first**, then clean up
  history/state. Deleting the file does not un-leak the value.
