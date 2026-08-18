# for_each, count, and lifecycle Meta-Arguments

The most common way Terraform destroys production by accident is a changed
resource *address*, not a changed resource. Addresses come from how you
iterate; control them deliberately.

## for_each vs count

| | `count` | `for_each` |
|---|---|---|
| Address | `aws_x.y[0]`, `[1]` | `aws_x.y["key"]` |
| Remove middle element | **shifts every later index → destroy/recreate cascade** | removes only that key |
| Accepts | number | `map` or `set(string)` (keys known at plan time) |
| Use for | "N identical copies", conditional single resource | any named collection |

Default to `for_each` with meaningful string keys. Reserve `count` for
genuinely fungible replicas and the enable/disable idiom:

```hcl
resource "aws_cloudwatch_log_group" "audit" {
  count = var.enable_audit ? 1 : 0
  name  = "/acme/audit"
}
```

### Stable keys are the contract

```hcl
# BAD: keyed by list index - inserting an AZ renumbers everything after it
resource "aws_subnet" "this" {
  count      = length(var.cidrs)
  cidr_block = var.cidrs[count.index]
}

# GOOD: keyed by name - order-insensitive, additions/removals are surgical
variable "subnets" {
  type = map(object({ cidr = string, az = string }))
}
resource "aws_subnet" "this" {
  for_each          = var.subnets
  cidr_block        = each.value.cidr
  availability_zone = each.value.az
}
```

Never key `for_each` on values unknown until apply (e.g., a resource's `id`)
- plan fails with "Invalid for_each argument". Key on input names, derive
values inside.

### Reshaping data for for_each

```hcl
# list(string) -> set
for_each = toset(var.user_names)            # each.key == each.value

# flatten nested structure -> map keyed by composite name
locals {
  rules = merge([
    for sg_name, sg in var.security_groups : {
      for idx, rule in sg.rules :
      "${sg_name}-${rule.protocol}-${rule.port}" => merge(rule, { sg = sg_name })
    }
  ]...)
}
resource "aws_vpc_security_group_ingress_rule" "this" {
  for_each = local.rules
  # ...
}
```

Composite keys must be stable: build them from user-supplied names/ports,
never from `idx`.

## Switching count -> for_each without destroying

Changing the iteration style changes every address, so the plan reads
"destroy `[0]`, create `["primary"]`" even though nothing real changed.
Bridge with `moved` blocks - one per existing index:

```hcl
resource "aws_instance" "app" {
  for_each = var.instances          # was: count = 2
  # ...
}

moved {
  from = aws_instance.app[0]
  to   = aws_instance.app["primary"]
}
moved {
  from = aws_instance.app[1]
  to   = aws_instance.app["replica"]
}
```

Verify: `terraform plan` must show only "has moved" annotations and **zero**
destroy/replace lines before applying. The same applies to module blocks
(`moved { from = module.svc, to = module.svc["api"] }`).

## lifecycle meta-arguments

```hcl
resource "aws_launch_template" "app" {
  # ...
  lifecycle {
    create_before_destroy = true
  }
}
```

- **create_before_destroy** - build the replacement before tearing down the
  old resource; required for anything referenced by an autoscaling group or
  serving live traffic. Caveat: names must not collide - use `name_prefix`
  or generated names, and note the flag propagates to dependencies.

- **prevent_destroy** - hard error if a plan would destroy the resource.
  Put it on stateful crown jewels (databases, state buckets, KMS keys):

```hcl
resource "aws_db_instance" "main" {
  # ...
  lifecycle { prevent_destroy = true }
}
```

  It does not survive the resource block being deleted from config, and it
  blocks legitimate replaces too - expect to temporarily lift it during
  planned migrations.

- **ignore_changes** - exclude specific arguments from diffs when an outside
  system legitimately mutates them:

```hcl
resource "aws_ecs_service" "app" {
  desired_count = 2
  lifecycle {
    ignore_changes = [desired_count]   # autoscaling owns this after creation
  }
}
```

  Only list arguments with a named external owner. `ignore_changes = all` is
  almost always a bug: it turns the resource into unmanaged drift. Never use
  it to "make the plan clean" - that hides real divergence.

- **replace_triggered_by** - force replacement when a related resource or
  value changes (for resources that don't notice upstream changes):

```hcl
resource "aws_appautoscaling_target" "ecs" {
  # ...
  lifecycle {
    replace_triggered_by = [aws_ecs_service.app.id]
  }
}
```

  Takes resource addresses or `terraform_data.x.output`; pair with
  `terraform_data` + `triggers_replace` to key replacement on arbitrary
  values (this replaces the legacy `null_resource` + `triggers` idiom).

- **precondition / postcondition** - assertions checked during plan/apply,
  with access to `self` in postconditions:

```hcl
resource "aws_instance" "app" {
  # ...
  lifecycle {
    precondition {
      condition     = data.aws_ami.selected.architecture == "arm64"
      error_message = "Selected AMI must be arm64."
    }
  }
}
```

## Reading destroy/replace plan lines

Every plan line prefixed `-` (destroy) or `-/+` (replace, "must be
replaced") is a stop-and-review gate. For replaces, the plan marks the
guilty argument with `# forces replacement`. Triage in order:

1. **Address change?** (renamed resource, count->for_each, moved into a
   module) → add `moved` blocks; re-plan until zero destroys.
2. **Immutable argument change?** (e.g., subnet CIDR, RDS engine) → decide
   if replacement is truly intended; if yes, add `create_before_destroy`
   where downtime matters and get explicit human approval.
3. **Externally mutated field?** → `ignore_changes` on that field only, with
   a comment naming the mutating system.

Apply only when the remaining destroy/replace set is exactly what a human
reviewer approved.
