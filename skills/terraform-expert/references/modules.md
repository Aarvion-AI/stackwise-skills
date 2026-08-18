# Module Design (Terraform 1.9+ / OpenTofu)

A module is an API: typed variables in, outputs out, everything else private.
Design the contract first; resources are implementation detail.

## Standard layout

```
modules/vpc/
  main.tf         # resources
  variables.tf    # the input contract
  outputs.tf      # the output contract
  versions.tf     # required_version + required_providers
  README.md
```

Root modules (environments) compose child modules and own the backend,
provider configs, and tfvars. Child (reusable) modules own neither.

## Variable contracts

Every variable gets a type, a description, and - where inputs can be wrong -
validation. Use `optional()` with defaults for rich objects so callers pass
only what they care about:

```hcl
variable "service" {
  description = "Service definition."
  type = object({
    name          = string
    port          = number
    cpu           = optional(number, 256)
    memory        = optional(number, 512)
    public        = optional(bool, false)
    health_path   = optional(string, "/healthz")
  })

  validation {
    condition     = var.service.port > 0 && var.service.port < 65536
    error_message = "service.port must be a valid TCP port."
  }
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default     = {}
}
```

Rules:

- `nullable = false` on variables that must never be explicitly nulled -
  otherwise a caller passing `null` overrides your default.
- `sensitive = true` on secret inputs; it propagates into plan output
  redaction (state still stores the value - see secrets reference).
- Since Terraform 1.9, `validation` conditions may reference **other
  variables and data sources**, enabling cross-field checks:

```hcl
variable "enable_dns" { type = bool }
variable "zone_name" {
  type    = string
  default = null
  validation {
    condition     = !var.enable_dns || var.zone_name != null
    error_message = "zone_name is required when enable_dns is true."
  }
}
```

- Don't invent a variable for every attribute. Expose what varies between
  callers; hardcode organizational decisions (encryption on, public access
  off) so they cannot be turned off by omission.

## Output contracts

Outputs are the only thing callers may depend on. Export IDs/ARNs/names that
consumers wire into other resources, and mark secret outputs sensitive:

```hcl
output "vpc_id" {
  description = "ID of the created VPC."
  value       = aws_vpc.this.id
}

output "db_password" {
  description = "Generated admin password."
  value       = random_password.admin.result
  sensitive   = true
}
```

Add `precondition` blocks on outputs to fail fast when an invariant breaks
inside the module rather than at the caller.

## Provider handling in modules

Reusable modules must **not** contain `provider` blocks - only declare
requirements. Callers configure providers and pass aliases explicitly:

```hcl
# modules/dr-bucket/versions.tf
terraform {
  required_version = ">= 1.9.0"
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = "~> 6.0"
      configuration_aliases = [aws.replica]
    }
  }
}

# root
provider "aws" { region = "us-east-1" }
provider "aws" { alias = "replica" region = "us-west-2" }

module "dr_bucket" {
  source    = "./modules/dr-bucket"
  providers = { aws = aws, aws.replica = aws.replica }
}
```

A module with its own `provider` block cannot be used with `for_each`/`count`
and cannot be cleanly destroyed - this is a hard rule, not a preference.

## Sources and version pinning

```hcl
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.0"          # registry modules: always pin
}

module "network" {
  source = "git::https://github.com/acme/tf-modules.git//network?ref=v2.3.1"
}                              # git modules: pin a tag, never a branch

module "local_thing" {
  source = "../modules/thing"  # local paths: no version argument exists
}
```

- Registry/git modules without a pin are a supply-chain and stability bug.
- Bump module versions deliberately, one at a time, reading the module's
  changelog; review the plan diff for replacements before merging.
- Version modules you publish with semver: breaking variable/output changes
  are a major; keep `moved` blocks in the module for renamed internal
  resources so consumers upgrade without destroys.

## Composition over configuration

Prefer several small modules wired together in the root over one mega-module
with dozens of feature flags:

```hcl
module "cluster" {
  source     = "./modules/eks-cluster"
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids
}
```

Signals a module is too big: boolean flags that disable whole resource
groups, `count = var.create ? 1 : 0` on most resources, outputs that are
`try(...)` chains. Split it.

## Iterating modules

`for_each` works on module blocks; the same stable-key rules apply as for
resources (see the for_each reference):

```hcl
module "service" {
  source   = "./modules/ecs-service"
  for_each = var.services        # map keyed by service name
  name     = each.key
  config   = each.value
}
```

Refactoring a single module call into `for_each` requires
`moved { from = module.service, to = module.service["api"] }` or every
resource in it is destroyed and recreated.
