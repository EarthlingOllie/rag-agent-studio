# Module contract for the cache module (ticket 09-03), at the module seam, with a mocked AWS provider.
# Runs that compare resource IDs use `command = apply`: the mock provider only invents IDs at apply time,
# and it never calls AWS, so apply here creates nothing real.
mock_provider "aws" {}

variables {
  name_prefix = "studio-demo"
  tags        = { Environment = "demo", Project = "rag-agent-studio" }
  vpc_id      = "vpc-0123456789abcdef0"
  subnet_ids  = ["subnet-0aaaaaaaaaaaaaaa1", "subnet-0bbbbbbbbbbbbbbb2"]
  kms_key_arn = "arn:aws:kms:eu-west-2:123456789012:key/11111111-2222-3333-4444-555555555555"
}

run "encrypts_in_transit_and_at_rest_with_auth_on" {
  command = plan

  assert {
    condition     = aws_elasticache_replication_group.this.transit_encryption_enabled && aws_elasticache_replication_group.this.transit_encryption_mode == "required"
    error_message = "Redis must require TLS for every connection."
  }

  assert {
    condition     = aws_elasticache_replication_group.this.at_rest_encryption_enabled == "true" && aws_elasticache_replication_group.this.kms_key_id == var.kms_key_arn
    error_message = "Redis data and snapshots must be encrypted at rest with the platform's data key."
  }

  assert {
    condition     = aws_elasticache_replication_group.this.auth_token_wo_version == 1 && aws_elasticache_replication_group.this.auth_token == null
    error_message = "Redis AUTH must be on, with the token written only through the write-only argument."
  }

  assert {
    condition     = aws_elasticache_replication_group.this.engine == "redis" && startswith(aws_elasticache_replication_group.this.engine_version, "7")
    error_message = "The cache must be Redis 7."
  }
}

run "keeps_the_auth_token_out_of_state_and_in_secrets_manager" {
  command = apply

  assert {
    condition     = aws_elasticache_replication_group.this.auth_token == null && aws_elasticache_replication_group.this.auth_token_wo == null
    error_message = "The auth token must never be stored in state."
  }

  assert {
    condition     = aws_secretsmanager_secret_version.auth_token.secret_string == "" || aws_secretsmanager_secret_version.auth_token.secret_string == null
    error_message = "The secret value must never be stored in state."
  }

  assert {
    condition     = aws_secretsmanager_secret_version.auth_token.secret_string_wo_version == aws_elasticache_replication_group.this.auth_token_wo_version
    error_message = "ElastiCache and Secrets Manager must be written with the same token version."
  }

  assert {
    condition     = aws_secretsmanager_secret.auth_token.kms_key_id == var.kms_key_arn
    error_message = "The token secret must be encrypted with the data key."
  }

  assert {
    condition     = aws_secretsmanager_secret_version.auth_token.secret_id == aws_secretsmanager_secret.auth_token.id && output.auth_token_secret_arn == aws_secretsmanager_secret.auth_token.arn
    error_message = "The module must write and output the token secret."
  }

  assert {
    condition     = aws_elasticache_replication_group.this.auth_token_update_strategy == "ROTATE"
    error_message = "A new token must be added alongside the old one, so running tasks keep working while they pick it up."
  }
}

run "auth_token_version_bumps_both_writes" {
  command = plan

  variables {
    auth_token_version = 2
  }

  assert {
    condition     = aws_elasticache_replication_group.this.auth_token_wo_version == 2
    error_message = "auth_token_version must reach ElastiCache."
  }

  assert {
    condition     = aws_secretsmanager_secret_version.auth_token.secret_string_wo_version == 2
    error_message = "auth_token_version must reach Secrets Manager."
  }
}

run "is_private_and_admits_only_listed_clients" {
  command = apply

  variables {
    client_security_group_ids = { api = "sg-0aaaaaaaaaaaaaaa1", worker = "sg-0bbbbbbbbbbbbbbb2", beat = "sg-0ccccccccccccccc3" }
  }

  assert {
    condition     = aws_elasticache_subnet_group.this.subnet_ids == toset(var.subnet_ids) && aws_elasticache_replication_group.this.subnet_group_name == aws_elasticache_subnet_group.this.name
    error_message = "Redis must live only in the private subnets it is given."
  }

  assert {
    condition     = aws_elasticache_replication_group.this.security_group_ids == toset([aws_security_group.this.id]) && output.security_group_id == aws_security_group.this.id
    error_message = "Redis must sit behind only the module's security group."
  }

  assert {
    condition     = length(aws_security_group.this.egress) == 0 && length(aws_security_group.this.ingress) == 0 && aws_security_group.this.vpc_id == var.vpc_id
    error_message = "The security group must be in the given VPC, with no inline rules and no egress."
  }

  assert {
    condition = { for k, r in aws_vpc_security_group_ingress_rule.clients : k => r.referenced_security_group_id } == {
      api    = "sg-0aaaaaaaaaaaaaaa1"
      worker = "sg-0bbbbbbbbbbbbbbb2"
      beat   = "sg-0ccccccccccccccc3"
    }
    error_message = "There must be one ingress rule per listed client security group."
  }

  assert {
    condition = alltrue([for r in aws_vpc_security_group_ingress_rule.clients :
      r.ip_protocol == "tcp" && r.from_port == 6379 && r.to_port == 6379 && r.cidr_ipv4 == null && r.cidr_ipv6 == null && r.security_group_id == aws_security_group.this.id
    ])
    error_message = "Ingress must be Redis from each listed client security group only, never from a CIDR."
  }

  assert {
    condition     = output.primary_endpoint_address == aws_elasticache_replication_group.this.primary_endpoint_address && output.port == 6379
    error_message = "The module must output where to connect."
  }
}

run "admits_no_one_without_clients" {
  command = plan

  assert {
    condition     = length(aws_vpc_security_group_ingress_rule.clients) == 0
    error_message = "With no clients listed, nothing may connect."
  }
}

run "demo_runs_one_cheap_node_with_snapshots" {
  command = plan

  assert {
    condition     = aws_elasticache_replication_group.this.node_type == "cache.t4g.micro" && aws_elasticache_replication_group.this.num_cache_clusters == 1
    error_message = "The demo runs a single cache.t4g.micro node."
  }

  assert {
    condition     = aws_elasticache_replication_group.this.automatic_failover_enabled == false && aws_elasticache_replication_group.this.multi_az_enabled == false
    error_message = "A single node cannot fail over."
  }

  assert {
    condition     = aws_elasticache_replication_group.this.snapshot_retention_limit == 1
    error_message = "Daily snapshots must be kept for a day by default."
  }
}

run "replicas_turn_on_failover" {
  command = plan

  variables {
    replicas                = 1
    snapshot_retention_days = 7
    engine_version          = "7.0"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.num_cache_clusters == 2
    error_message = "A replica adds a second node."
  }

  assert {
    condition     = aws_elasticache_replication_group.this.automatic_failover_enabled && aws_elasticache_replication_group.this.multi_az_enabled
    error_message = "With a replica, failover must be automatic and across AZs."
  }

  assert {
    condition     = aws_elasticache_replication_group.this.snapshot_retention_limit == 7 && aws_elasticache_replication_group.this.engine_version == "7.0"
    error_message = "Snapshot retention and the engine version must reach the replication group."
  }
}

run "every_resource_carries_the_standard_tags" {
  command = plan

  variables {
    client_security_group_ids = { api = "sg-0aaaaaaaaaaaaaaa1" }
  }

  assert {
    condition     = output.tags == { Environment = "demo", Project = "rag-agent-studio", Module = "cache", ManagedBy = "terraform" }
    error_message = "Tags must merge the caller's tags with the module's own."
  }

  assert {
    condition = alltrue([for tags in concat(
      [aws_elasticache_subnet_group.this.tags, aws_security_group.this.tags, aws_secretsmanager_secret.auth_token.tags, aws_elasticache_replication_group.this.tags],
      [for r in aws_vpc_security_group_ingress_rule.clients : r.tags],
    ) : alltrue([for key, value in output.tags : lookup(tags, key, null) == value])])
    error_message = "Every taggable resource must carry the standard tags."
  }

  assert {
    condition     = output.name == "studio-demo-cache" && aws_elasticache_replication_group.this.replication_group_id == "studio-demo-cache"
    error_message = "Resources must be named from name_prefix."
  }
}

run "rejects_redis_6" {
  command = plan

  variables {
    engine_version = "6.2"
  }

  expect_failures = [var.engine_version]
}

run "rejects_a_non_elasticache_node_type" {
  command = plan

  variables {
    node_type = "t4g.micro"
  }

  expect_failures = [var.node_type]
}

run "rejects_negative_replicas" {
  command = plan

  variables {
    replicas = -1
  }

  expect_failures = [var.replicas]
}

run "rejects_more_than_five_replicas" {
  command = plan

  variables {
    replicas = 6
  }

  expect_failures = [var.replicas]
}

run "rejects_turning_snapshots_off" {
  command = plan

  variables {
    snapshot_retention_days = 0
  }

  expect_failures = [var.snapshot_retention_days]
}

run "rejects_snapshot_retention_over_35_days" {
  command = plan

  variables {
    snapshot_retention_days = 36
  }

  expect_failures = [var.snapshot_retention_days]
}

run "rejects_a_single_subnet" {
  command = plan

  variables {
    subnet_ids = ["subnet-0aaaaaaaaaaaaaaa1"]
  }

  expect_failures = [var.subnet_ids]
}

run "rejects_a_key_that_is_not_a_kms_arn" {
  command = plan

  variables {
    kms_key_arn = "alias/aws/elasticache"
  }

  expect_failures = [var.kms_key_arn]
}

run "rejects_a_zero_auth_token_version" {
  command = plan

  variables {
    auth_token_version = 0
  }

  expect_failures = [var.auth_token_version]
}

run "rejects_tags_without_project_and_environment" {
  command = plan

  variables {
    tags = { Project = "rag-agent-studio" }
  }

  expect_failures = [var.tags]
}

run "rejects_an_invalid_prefix" {
  command = plan

  variables {
    name_prefix = "Studio_Demo"
  }

  expect_failures = [var.name_prefix]
}
