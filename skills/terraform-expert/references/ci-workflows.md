# CI/CD for Terraform: plan on PR, apply on merge

The delivery invariant: **every apply executes a saved plan file that a human
reviewed on the PR.** No pipeline runs `apply -auto-approve` on a fresh plan.

## Pipeline shape

```
PR opened/updated:
  fmt -check  ->  init  ->  validate  ->  tflint  ->  plan -out=tfplan
                                              plan text posted to PR
                                              tfplan uploaded as artifact
Merge to main:
  init  ->  download tfplan  ->  apply tfplan
            (environment gate = the human approval step)
Nightly:
  init  ->  plan -detailed-exitcode        # drift detection
```

If the merge commit differs from the planned commit (other PRs landed in
between), the saved plan is stale - `apply tfplan` fails with a changed
dependency lock or state serial, or worse, applies outdated intent. Either
re-plan + re-approve on main via an environment gate, or enforce a merge
queue so plans are always computed on the final commit.

## GitHub Actions: plan on PR

```yaml
name: terraform-plan
on:
  pull_request:
    paths: ["infra/**"]

permissions:
  id-token: write        # OIDC - no stored cloud keys
  contents: read
  pull-requests: write

concurrency:
  group: tf-${{ github.ref }}
  cancel-in-progress: false   # never cancel a run holding the state lock

jobs:
  plan:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: infra } }
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with: { terraform_version: "1.11.4" }
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::111111111111:role/tf-plan
          aws-region: us-east-1
      - run: terraform fmt -check -recursive
      - run: terraform init -backend-config=backends/prod.s3.tfbackend
      - run: terraform validate
      - uses: terraform-linters/setup-tflint@v4
      - run: tflint --init && tflint --recursive
      - run: terraform plan -input=false -out=tfplan
      - run: terraform show -no-color tfplan > plan.txt
      - uses: actions/upload-artifact@v4
        with: { name: tfplan-${{ github.sha }}, path: infra/tfplan, retention-days: 5 }
      - name: Comment plan on PR
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const plan = fs.readFileSync('infra/plan.txt', 'utf8');
            const body = '```hcl\n' + plan.slice(0, 60000) + '\n```';
            await github.rest.issues.createComment({
              ...context.repo, issue_number: context.issue.number, body });
```

Reviewers approve the PR only after reading the plan comment - destroy and
replace (`-/+`) lines require explicit acknowledgement in review. The plan
artifact is sensitive (contains unredacted values): short retention,
restricted repo access.

## GitHub Actions: apply on merge

```yaml
name: terraform-apply
on:
  push:
    branches: [main]
    paths: ["infra/**"]

permissions: { id-token: write, contents: read }
concurrency: { group: tf-apply-prod, cancel-in-progress: false }

jobs:
  apply:
    runs-on: ubuntu-latest
    environment: prod          # required-reviewers gate lives here
    defaults: { run: { working-directory: infra } }
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with: { terraform_version: "1.11.4" }
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::111111111111:role/tf-apply
          aws-region: us-east-1
      - run: terraform init -backend-config=backends/prod.s3.tfbackend
      - run: terraform plan -input=false -out=tfplan   # re-plan on final commit
      - run: terraform show -no-color tfplan
      - run: terraform apply -input=false tfplan       # the reviewed artifact
```

Notes:

- Re-planning on main + an `environment` approval gate is the simplest safe
  pattern; the approver compares the main plan against the PR plan.
- Separate IAM roles: `tf-plan` (read + state read/lock) for PRs - critical
  because PR code executes with these credentials - and `tf-apply` (write)
  only on the protected branch/environment.
- Pin the Terraform version in CI to the same version developers use;
  commit `.terraform.lock.hcl` and run `terraform providers lock
  -platform=linux_amd64 -platform=darwin_arm64` when adding providers so
  init verifies checksums on every platform.

## Drift detection

`-detailed-exitcode` makes plan exit 2 when changes exist:

```yaml
on:
  schedule: [{ cron: "0 5 * * *" }]
jobs:
  drift:
    steps:
      # ...init as above...
      - id: plan
        run: terraform plan -input=false -detailed-exitcode -no-color
        continue-on-error: true
      - if: steps.plan.outputs.exitcode == '2'
        run: ./notify-drift.sh    # page/Slack; never auto-apply drift
```

Exit 0 = clean, 1 = error, 2 = drift. Drift response is human triage:
either someone changed infra out-of-band (revert or codify it) or a provider
default shifted (update config). Auto-applying a drift plan can revert a
legitimate emergency fix at 3 a.m.

## Multi-environment layout

- One state key and one pipeline per environment
  (`infra/envs/{dev,stage,prod}` or one root + per-env
  `-backend-config`/`-var-file`).
- Promote by merging the same module version bump through dev -> stage ->
  prod PRs; never point two environments at one state file.
- Matrix the plan job over changed environments (detect with
  `dorny/paths-filter` or `git diff --name-only`).

## OpenTofu / other CI systems

- Swap `hashicorp/setup-terraform` for `opentofu/setup-opentofu` and
  `terraform` for `tofu`; flags above are identical.
- GitLab CI: same shape - `plan` job saves `tfplan` as an artifact,
  `apply` job is `when: manual` on the default branch with
  `resource_group: tf-prod` for locking.
- Atlantis/Terraform Cloud/Spacelift implement plan-comment + apply-gate
  natively; keep the same invariant (reviewed plan == applied plan) when
  adopting them.
