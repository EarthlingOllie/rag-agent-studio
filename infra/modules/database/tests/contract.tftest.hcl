# Module contract for the database module (ticket 09-03), at the module seam, with a mocked AWS provider.
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

run "runs_postgres_16_encrypted_private_with_backups" {
  command = plan

  assert {
    condition     = aws_db_instance.this.engine == "postgres" && startswith(aws_db_instance.this.engine_version, "16")
    error_message = "The database must be RDS Postgres 16."
  }

  assert {
    condition     = aws_db_instance.this.storage_encrypted && aws_db_instance.this.kms_key_id == var.kms_key_arn
    error_message = "Storage must be encrypted with the platform's data key."
  }

  assert {
    condition     = aws_db_instance.this.publicly_accessible == false
    error_message = "The database must not be publicly accessible."
  }

  assert {
    condition     = aws_db_subnet_group.this.subnet_ids == toset(var.subnet_ids)
    error_message = "The database must live only in the private subnets it is given."
  }

  assert {
    condition     = aws_db_instance.this.backup_retention_period == 7
    error_message = "Automated backups must be kept for 7 days by default."
  }
}

run "requires_tls_and_admits_only_listed_clients" {
  command = apply

  variables {
    client_security_group_ids = { api = "sg-0aaaaaaaaaaaaaaa1", worker = "sg-0bbbbbbbbbbbbbbb2" }
  }

  assert {
    condition     = aws_db_instance.this.parameter_group_name == aws_db_parameter_group.this.name
    error_message = "The instance must use the module's parameter group."
  }

  assert {
    condition     = aws_db_parameter_group.this.family == "postgres16" && [for p in aws_db_parameter_group.this.parameter : [p.name, p.value]] == [["rds.force_ssl", "1"]]
    error_message = "The parameter group must require TLS and change nothing else."
  }

  assert {
    condition     = aws_db_instance.this.vpc_security_group_ids == toset([aws_security_group.this.id]) && output.security_group_id == aws_security_group.this.id
    error_message = "The instance must sit behind only the module's security group."
  }

  assert {
    condition     = length(aws_security_group.this.egress) == 0 && length(aws_security_group.this.ingress) == 0
    error_message = "The security group must have no inline rules and no egress."
  }

  assert {
    condition = { for k, r in aws_vpc_security_group_ingress_rule.clients : k => r.referenced_security_group_id } == {
      api    = "sg-0aaaaaaaaaaaaaaa1"
      worker = "sg-0bbbbbbbbbbbbbbb2"
    }
    error_message = "There must be one ingress rule per listed client security group."
  }

  assert {
    condition = alltrue([for r in aws_vpc_security_group_ingress_rule.clients :
      r.ip_protocol == "tcp" && r.from_port == 5432 && r.to_port == 5432 && r.cidr_ipv4 == null && r.cidr_ipv6 == null && r.security_group_id == aws_security_group.this.id
    ])
    error_message = "Ingress must be Postgres from each listed client security group only, never from a CIDR."
  }

  assert {
    condition     = aws_db_subnet_group.this.vpc_id == null || aws_security_group.this.vpc_id == var.vpc_id
    error_message = "The security group must be in the given VPC."
  }
}

run "admits_no_one_without_clients" {
  command = plan

  assert {
    condition     = length(aws_vpc_security_group_ingress_rule.clients) == 0
    error_message = "With no clients listed, nothing may connect."
  }
}

run "keeps_the_password_out_of_state_and_in_secrets_manager" {
  command = apply

  assert {
    condition     = aws_db_instance.this.password == null && aws_db_instance.this.password_wo == null
    error_message = "The master password must never be stored in state."
  }

  assert {
    condition     = aws_secretsmanager_secret_version.master_password.secret_string == "" || aws_secretsmanager_secret_version.master_password.secret_string == null
    error_message = "The secret value must never be stored in state."
  }

  assert {
    condition     = aws_db_instance.this.password_wo_version == 1 && aws_secretsmanager_secret_version.master_password.secret_string_wo_version == 1
    error_message = "RDS and Secrets Manager must be written with the same password version."
  }

  assert {
    condition     = aws_secretsmanager_secret.master_password.kms_key_id == var.kms_key_arn
    error_message = "The password secret must be encrypted with the data key."
  }

  assert {
    condition     = aws_secretsmanager_secret_version.master_password.secret_id == aws_secretsmanager_secret.master_password.id && output.password_secret_arn == aws_secretsmanager_secret.master_password.arn
    error_message = "The module must write and output the password secret."
  }

  assert {
    condition     = aws_db_instance.this.manage_master_user_password == null || aws_db_instance.this.manage_master_user_password == false
    error_message = "RDS-managed rotation would break running tasks, so the module manages the secret itself."
  }
}

run "password_version_bumps_both_writes" {
  command = plan

  variables {
    password_version = 2
  }

  assert {
    condition     = aws_db_instance.this.password_wo_version == 2
    error_message = "password_version must reach RDS."
  }

  assert {
    condition     = aws_secretsmanager_secret_version.master_password.secret_string_wo_version == 2
    error_message = "password_version must reach Secrets Manager."
  }
}

run "demo_defaults_are_cheap_and_destroyable" {
  command = plan

  assert {
    condition     = aws_db_instance.this.instance_class == "db.t4g.micro" && aws_db_instance.this.multi_az == false && aws_db_instance.this.storage_type == "gp3"
    error_message = "The demo runs on a single-AZ db.t4g.micro with gp3 storage."
  }

  assert {
    condition     = aws_db_instance.this.deletion_protection == false && aws_db_instance.this.skip_final_snapshot && aws_db_instance.this.final_snapshot_identifier == null
    error_message = "The demo must be destroyable in one run without a final snapshot."
  }

  assert {
    condition     = aws_db_instance.this.copy_tags_to_snapshot && aws_db_instance.this.auto_minor_version_upgrade && aws_db_instance.this.iam_database_authentication_enabled
    error_message = "Snapshots carry tags, minor versions patch themselves and IAM authentication is available."
  }

  assert {
    condition     = aws_db_instance.this.db_name == "studio" && aws_db_instance.this.username == "studio" && aws_db_instance.this.port == 5432
    error_message = "The application database and user default to studio on port 5432."
  }
}

run "production_toggles_turn_on_protection" {
  command = plan

  variables {
    multi_az              = true
    deletion_protection   = true
    final_snapshot        = true
    backup_retention_days = 35
    engine_version        = "16.6"
  }

  assert {
    condition     = aws_db_instance.this.multi_az && aws_db_instance.this.deletion_protection
    error_message = "multi_az and deletion_protection must reach the instance."
  }

  assert {
    condition     = aws_db_instance.this.skip_final_snapshot == false && aws_db_instance.this.final_snapshot_identifier == "studio-demo-database-final" && aws_db_instance.this.delete_automated_backups == false
    error_message = "final_snapshot must keep a final snapshot and the automated backups."
  }

  assert {
    condition     = aws_db_instance.this.backup_retention_period == 35 && aws_db_instance.this.engine_version == "16.6"
    error_message = "Backup retention and the pinned minor version must reach the instance."
  }
}

run "outputs_the_connection_details" {
  command = apply

  assert {
    condition     = output.address == aws_db_instance.this.address && output.port == aws_db_instance.this.port
    error_message = "The module must output where to connect."
  }

  assert {
    condition     = output.database_name == "studio" && output.master_username == "studio"
    error_message = "The module must output the database and user names."
  }
}

run "every_resource_carries_the_standard_tags" {
  command = plan

  variables {
    client_security_group_ids = { api = "sg-0aaaaaaaaaaaaaaa1" }
  }

  assert {
    condition     = output.tags == { Environment = "demo", Project = "rag-agent-studio", Module = "database", ManagedBy = "terraform" }
    error_message = "Tags must merge the caller's tags with the module's own."
  }

  assert {
    condition = alltrue([for tags in concat(
      [aws_db_subnet_group.this.tags, aws_security_group.this.tags, aws_db_parameter_group.this.tags, aws_secretsmanager_secret.master_password.tags, aws_db_instance.this.tags],
      [for r in aws_vpc_security_group_ingress_rule.clients : r.tags],
    ) : alltrue([for key, value in output.tags : lookup(tags, key, null) == value])])
    error_message = "Every taggable resource must carry the standard tags."
  }

  assert {
    condition     = output.name == "studio-demo-database" && aws_db_instance.this.identifier == "studio-demo-database"
    error_message = "Resources must be named from name_prefix."
  }
}

run "rejects_postgres_15" {
  command = plan

  variables {
    engine_version = "15.8"
  }

  expect_failures = [var.engine_version]
}

run "rejects_turning_backups_off" {
  command = plan

  variables {
    backup_retention_days = 0
  }

  expect_failures = [var.backup_retention_days]
}

run "rejects_backup_retention_over_35_days" {
  command = plan

  variables {
    backup_retention_days = 36
  }

  expect_failures = [var.backup_retention_days]
}

run "rejects_a_single_subnet" {
  command = plan

  variables {
    subnet_ids = ["subnet-0aaaaaaaaaaaaaaa1", "subnet-0aaaaaaaaaaaaaaa1"]
  }

  expect_failures = [var.subnet_ids]
}

run "rejects_a_key_that_is_not_a_kms_arn" {
  command = plan

  variables {
    kms_key_arn = "alias/aws/rds"
  }

  expect_failures = [var.kms_key_arn]
}

run "rejects_a_non_rds_instance_class" {
  command = plan

  variables {
    instance_class = "t4g.micro"
  }

  expect_failures = [var.instance_class]
}

run "rejects_storage_under_the_gp3_minimum" {
  command = plan

  variables {
    allocated_storage_gb = 19
  }

  expect_failures = [var.allocated_storage_gb]
}

run "rejects_an_invalid_database_name" {
  command = plan

  variables {
    database_name = "Studio-DB"
  }

  expect_failures = [var.database_name]
}

run "rejects_a_reserved_master_username" {
  command = plan

  variables {
    master_username = "rdsadmin"
  }

  expect_failures = [var.master_username]
}

run "rejects_a_malformed_master_username" {
  command = plan

  variables {
    master_username = "1studio"
  }

  expect_failures = [var.master_username]
}

run "rejects_a_fractional_password_version" {
  command = plan

  variables {
    password_version = 1.5
  }

  expect_failures = [var.password_version]
}

run "rejects_a_zero_password_version" {
  command = plan

  variables {
    password_version = 0
  }

  expect_failures = [var.password_version]
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
