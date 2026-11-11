# Module contract for the network module (ticket 09-02), at the module seam, with a mocked AWS provider.
# Runs that compare resource IDs use `command = apply`: the mock provider only invents IDs at apply time,
# and it never calls AWS, so apply here creates nothing real.
mock_provider "aws" {
  mock_data "aws_region" {
    defaults = {
      region = "eu-west-2"
    }
  }
}

variables {
  name_prefix        = "studio-demo"
  availability_zones = ["eu-west-2a", "eu-west-2b"]
  tags               = { Environment = "demo", Project = "rag-agent-studio" }
}

run "spans_two_azs_with_public_and_private_subnets" {
  command = plan

  assert {
    condition     = output.availability_zones == tolist(["eu-west-2a", "eu-west-2b"])
    error_message = "The VPC must span the two availability zones it is given."
  }

  assert {
    condition     = aws_vpc.this.cidr_block == "10.0.0.0/16"
    error_message = "The VPC must default to 10.0.0.0/16."
  }

  assert {
    condition     = [for s in aws_subnet.public : s.availability_zone] == ["eu-west-2a", "eu-west-2b"]
    error_message = "There must be one public subnet in each of the two AZs."
  }

  assert {
    condition     = [for s in aws_subnet.private : s.availability_zone] == ["eu-west-2a", "eu-west-2b"]
    error_message = "There must be one private subnet in each of the two AZs."
  }

  assert {
    condition     = [for s in aws_subnet.public : s.cidr_block] == ["10.0.0.0/24", "10.0.1.0/24"]
    error_message = "Public subnets must be /24s at the start of the VPC range."
  }

  assert {
    condition     = [for s in aws_subnet.private : s.cidr_block] == ["10.0.16.0/20", "10.0.32.0/20"]
    error_message = "Private subnets must be /20s that do not overlap the public ones."
  }

  assert {
    condition     = length(output.public_subnet_ids) == 2 && length(output.private_subnet_ids) == 2
    error_message = "The module must output both subnet ID lists."
  }
}

run "private_subnets_have_no_public_ips" {
  command = plan

  assert {
    condition     = alltrue([for s in aws_subnet.private : s.map_public_ip_on_launch == false])
    error_message = "Private subnets must never assign public IPv4 addresses on launch."
  }

  assert {
    condition     = alltrue([for s in aws_subnet.private : s.assign_ipv6_address_on_creation == false])
    error_message = "Private subnets must not assign IPv6 addresses, which are publicly routable."
  }

  assert {
    condition     = alltrue([for s in aws_subnet.public : s.map_public_ip_on_launch == false])
    error_message = "Public subnets must not hand out public IPs either; only the NAT gets an Elastic IP."
  }

  assert {
    condition     = aws_route.public_internet.destination_cidr_block == "0.0.0.0/0"
    error_message = "Public subnets must route the internet through the internet gateway."
  }

  assert {
    condition     = length(aws_route_table_association.private) == 2 && length(aws_route_table_association.public) == 2
    error_message = "Every subnet must be associated with its tier's route table."
  }
}

run "egresses_through_fck_nat_by_default" {
  command = apply

  assert {
    condition     = output.nat_mode == "fck-nat"
    error_message = "fck-nat must be the default egress (ADR-0010)."
  }

  assert {
    condition     = length(aws_instance.fck_nat) == 1 && length(aws_nat_gateway.this) == 0
    error_message = "By default there must be one fck-nat instance and no managed NAT gateway."
  }

  assert {
    condition     = aws_instance.fck_nat[0].instance_type == "t4g.nano"
    error_message = "fck-nat must default to a t4g.nano."
  }

  assert {
    condition     = aws_network_interface.fck_nat[0].source_dest_check == false
    error_message = "The fck-nat interface must have source/destination checking off to forward traffic."
  }

  assert {
    condition     = aws_network_interface.fck_nat[0].subnet_id == aws_subnet.public[0].id
    error_message = "fck-nat must sit in a public subnet."
  }

  assert {
    condition     = aws_route.private_egress.destination_cidr_block == "0.0.0.0/0" && aws_route.private_egress.network_interface_id == aws_network_interface.fck_nat[0].id
    error_message = "Private egress must go to the fck-nat interface, not a NAT gateway."
  }

  assert {
    condition     = aws_route.private_egress.gateway_id == null
    error_message = "Private subnets must never route straight to the internet gateway."
  }
}

run "managed_nat_toggle_swaps_fck_nat_for_a_nat_gateway" {
  command = apply

  variables {
    managed_nat = true
  }

  assert {
    condition     = output.nat_mode == "managed"
    error_message = "The toggle must switch the egress mode to managed."
  }

  assert {
    condition     = length(aws_nat_gateway.this) == 1 && length(aws_instance.fck_nat) == 0 && length(aws_network_interface.fck_nat) == 0
    error_message = "With the toggle on there must be one NAT gateway and no fck-nat instance."
  }

  assert {
    condition     = aws_nat_gateway.this[0].subnet_id == aws_subnet.public[0].id && aws_nat_gateway.this[0].connectivity_type == "public"
    error_message = "The managed NAT gateway must be public and sit in a public subnet."
  }

  assert {
    condition     = aws_route.private_egress.nat_gateway_id == aws_nat_gateway.this[0].id && aws_route.private_egress.gateway_id == null
    error_message = "Private egress must go to the NAT gateway, not an instance or the internet gateway."
  }
}

run "rejects_an_unknown_nat_instance_type_family" {
  command = plan

  variables {
    fck_nat_instance_type = "t3.nano"
  }

  expect_failures = [var.fck_nat_instance_type]
}

run "vpc_endpoints_keep_aws_traffic_off_the_nat" {
  command = apply

  assert {
    condition     = aws_vpc_endpoint.s3.service_name == "com.amazonaws.eu-west-2.s3" && aws_vpc_endpoint.s3.vpc_endpoint_type == "Gateway"
    error_message = "S3 must be reached through a (free) gateway endpoint."
  }

  assert {
    condition     = aws_vpc_endpoint.s3.route_table_ids == toset([aws_route_table.private.id])
    error_message = "The S3 gateway endpoint must be on the private route table."
  }

  assert {
    condition = toset([for e in aws_vpc_endpoint.interface : e.service_name]) == toset([
      "com.amazonaws.eu-west-2.ecr.api",
      "com.amazonaws.eu-west-2.ecr.dkr",
      "com.amazonaws.eu-west-2.logs",
      "com.amazonaws.eu-west-2.secretsmanager",
    ])
    error_message = "There must be interface endpoints for ECR (API and Docker), CloudWatch Logs and Secrets Manager."
  }

  assert {
    condition = alltrue([for e in aws_vpc_endpoint.interface :
      e.vpc_endpoint_type == "Interface" && e.private_dns_enabled &&
      e.subnet_ids == toset(aws_subnet.private[*].id) &&
      e.security_group_ids == toset([aws_security_group.endpoints.id])
    ])
    error_message = "Interface endpoints must use private DNS, sit in both private subnets and use the endpoint security group."
  }

  assert {
    condition = (
      aws_vpc_security_group_ingress_rule.endpoints_https.cidr_ipv4 == "10.0.0.0/16" &&
      aws_vpc_security_group_ingress_rule.endpoints_https.from_port == 443 &&
      aws_vpc_security_group_ingress_rule.endpoints_https.to_port == 443 &&
      aws_vpc_security_group_ingress_rule.endpoints_https.ip_protocol == "tcp"
    )
    error_message = "Endpoints must accept only HTTPS, and only from inside the VPC."
  }

  assert {
    condition     = output.endpoint_security_group_id == aws_security_group.endpoints.id
    error_message = "The module must output the endpoint security group."
  }
}

run "endpoints_are_the_same_with_a_managed_nat" {
  command = plan

  variables {
    managed_nat = true
  }

  assert {
    condition     = length(aws_vpc_endpoint.interface) == 4
    error_message = "The NAT toggle must not change the VPC endpoints."
  }
}

run "names_resources_from_the_prefix" {
  command = plan

  assert {
    condition     = output.name == "studio-demo-network" && aws_vpc.this.tags["Name"] == "studio-demo-network"
    error_message = "The network name must be derived from name_prefix."
  }

  assert {
    condition     = output.tags == { Environment = "demo", Project = "rag-agent-studio", Module = "network", ManagedBy = "terraform" }
    error_message = "The standard tags are the caller's Project and Environment plus Module and ManagedBy."
  }
}

run "every_fck_nat_mode_resource_carries_the_standard_tags" {
  command = plan

  assert {
    condition = alltrue([for r in [
      aws_vpc.this, aws_internet_gateway.this, aws_route_table.public, aws_route_table.private, aws_eip.nat,
      aws_default_security_group.this, aws_security_group.endpoints, aws_vpc_security_group_ingress_rule.endpoints_https,
      aws_vpc_endpoint.s3, aws_security_group.fck_nat[0], aws_vpc_security_group_ingress_rule.fck_nat_from_vpc[0],
      aws_vpc_security_group_egress_rule.fck_nat_to_internet[0], aws_network_interface.fck_nat[0], aws_instance.fck_nat[0],
    ] : alltrue([for k, v in output.tags : lookup(r.tags, k, "") == v])])
    error_message = "Every resource must carry the standard tags."
  }

  assert {
    condition     = alltrue([for r in concat(aws_subnet.public, aws_subnet.private, values(aws_vpc_endpoint.interface)) : alltrue([for k, v in output.tags : lookup(r.tags, k, "") == v])])
    error_message = "Every subnet and interface endpoint must carry the standard tags."
  }

  assert {
    condition     = alltrue([for k, v in output.tags : lookup(aws_instance.fck_nat[0].volume_tags, k, "") == v])
    error_message = "The fck-nat root volume must carry the standard tags."
  }
}

run "every_managed_nat_mode_resource_carries_the_standard_tags" {
  command = plan

  variables {
    managed_nat = true
  }

  assert {
    condition     = alltrue([for k, v in output.tags : lookup(aws_nat_gateway.this[0].tags, k, "") == v])
    error_message = "The managed NAT gateway must carry the standard tags."
  }
}

run "locks_down_the_default_security_group" {
  command = plan

  assert {
    condition     = length(aws_default_security_group.this.ingress) == 0 && length(aws_default_security_group.this.egress) == 0
    error_message = "The VPC's default security group must allow nothing."
  }
}

run "rejects_tags_without_project_and_environment" {
  command = plan

  variables {
    tags = { Environment = "demo" }
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

run "rejects_an_invalid_vpc_cidr" {
  command = plan

  variables {
    vpc_cidr = "10.0.0.0/24"
  }

  expect_failures = [var.vpc_cidr]
}

run "rejects_anything_but_two_distinct_azs" {
  command = plan

  variables {
    availability_zones = ["eu-west-2a", "eu-west-2a"]
  }

  expect_failures = [var.availability_zones]
}

run "rejects_a_single_az" {
  command = plan

  variables {
    availability_zones = ["eu-west-2a"]
  }

  expect_failures = [var.availability_zones]
}
