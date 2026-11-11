# Network module (ticket 09-02): a private, cheap VPC across two AZs (ADR-0010).
locals {
  module_name = "network"
  name        = "${var.name_prefix}-${local.module_name}"
  tags        = merge(var.tags, { Module = local.module_name, ManagedBy = "terraform" })

  azs = var.availability_zones
}

resource "aws_vpc" "this" {
  #checkov:skip=CKV2_AWS_11:Flow logs are a paid extra (ingestion and storage) that the short-lived demo VPC does not need.
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.tags, { Name = local.name })
}

# The default security group allows nothing, so a resource that forgets its own group is isolated.
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.tags, { Name = "${local.name}-default-deny" })
}

resource "aws_subnet" "public" {
  count = length(local.azs)

  vpc_id                          = aws_vpc.this.id
  availability_zone               = local.azs[count.index]
  cidr_block                      = cidrsubnet(var.vpc_cidr, 8, count.index)
  map_public_ip_on_launch         = false
  assign_ipv6_address_on_creation = false

  tags = merge(local.tags, { Name = "${local.name}-public-${local.azs[count.index]}", Tier = "public" })
}

resource "aws_subnet" "private" {
  count = length(local.azs)

  vpc_id                          = aws_vpc.this.id
  availability_zone               = local.azs[count.index]
  cidr_block                      = cidrsubnet(var.vpc_cidr, 4, count.index + 1)
  map_public_ip_on_launch         = false
  assign_ipv6_address_on_creation = false

  tags = merge(local.tags, { Name = "${local.name}-private-${local.azs[count.index]}", Tier = "private" })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.tags, { Name = local.name })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.tags, { Name = "${local.name}-public", Tier = "public" })
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# One private route table: there is a single NAT, so every private subnet shares its default route.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.tags, { Name = "${local.name}-private", Tier = "private" })
}

resource "aws_route_table_association" "private" {
  count = length(aws_subnet.private)

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# Egress: one fck-nat instance by default, or one managed NAT gateway when var.managed_nat is set.
locals {
  nat_mode = var.managed_nat ? "managed" : "fck-nat"
}

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = merge(local.tags, { Name = "${local.name}-nat" })

  depends_on = [aws_internet_gateway.this]
}

resource "aws_nat_gateway" "this" {
  count = var.managed_nat ? 1 : 0

  connectivity_type = "public"
  allocation_id     = aws_eip.nat.id
  subnet_id         = aws_subnet.public[0].id

  tags = merge(local.tags, { Name = local.name })
}

data "aws_ami" "fck_nat" {
  count = var.managed_nat ? 0 : 1

  most_recent = true
  owners      = ["568608671756"] # The fck-nat project's AWS account.

  filter {
    name   = "name"
    values = ["fck-nat-al2023-*-arm64-ebs"]
  }

  filter {
    name   = "architecture"
    values = ["arm64"]
  }
}

resource "aws_security_group" "fck_nat" {
  count = var.managed_nat ? 0 : 1

  name        = "${local.name}-fck-nat"
  description = "fck-nat: forwards traffic from inside the VPC to the internet"
  vpc_id      = aws_vpc.this.id

  tags = merge(local.tags, { Name = "${local.name}-fck-nat" })
}

resource "aws_vpc_security_group_ingress_rule" "fck_nat_from_vpc" {
  count = var.managed_nat ? 0 : 1

  security_group_id = aws_security_group.fck_nat[0].id
  description       = "All traffic from inside the VPC, to be forwarded"
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "-1"

  tags = local.tags
}

resource "aws_vpc_security_group_egress_rule" "fck_nat_to_internet" {
  count = var.managed_nat ? 0 : 1

  security_group_id = aws_security_group.fck_nat[0].id
  description       = "Forwarded traffic to the internet"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"

  tags = local.tags
}

resource "aws_network_interface" "fck_nat" {
  count = var.managed_nat ? 0 : 1

  description       = "fck-nat egress interface"
  subnet_id         = aws_subnet.public[0].id
  security_groups   = [aws_security_group.fck_nat[0].id]
  source_dest_check = false

  tags = merge(local.tags, { Name = "${local.name}-fck-nat" })
}

resource "aws_eip_association" "fck_nat" {
  count = var.managed_nat ? 0 : 1

  allocation_id        = aws_eip.nat.id
  network_interface_id = aws_network_interface.fck_nat[0].id
}

resource "aws_instance" "fck_nat" {
  count = var.managed_nat ? 0 : 1
  #checkov:skip=CKV2_AWS_41:fck-nat only forwards packets and calls no AWS API, so it gets no IAM role.
  #checkov:skip=CKV_AWS_126:Detailed monitoring costs more than the demo NAT itself; basic monitoring is kept.

  ami           = data.aws_ami.fck_nat[0].id
  instance_type = var.fck_nat_instance_type
  ebs_optimized = true
  monitoring    = false

  primary_network_interface {
    network_interface_id = aws_network_interface.fck_nat[0].id
  }

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    encrypted = true
  }

  volume_tags = merge(local.tags, { Name = "${local.name}-fck-nat" })
  tags        = merge(local.tags, { Name = "${local.name}-fck-nat" })
}

resource "aws_route" "private_egress" {
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = var.managed_nat ? aws_nat_gateway.this[0].id : null
  network_interface_id   = var.managed_nat ? null : aws_network_interface.fck_nat[0].id
}

# VPC endpoints: ECS image pulls, logs and secrets stay inside AWS instead of crossing the NAT.
locals {
  interface_endpoint_services = toset(["ecr.api", "ecr.dkr", "logs", "secretsmanager"])
}

data "aws_region" "current" {}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = merge(local.tags, { Name = "${local.name}-s3" })
}

resource "aws_security_group" "endpoints" {
  name        = "${local.name}-endpoints"
  description = "VPC interface endpoints: HTTPS from inside the VPC only"
  vpc_id      = aws_vpc.this.id

  tags = merge(local.tags, { Name = "${local.name}-endpoints" })
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_https" {
  security_group_id = aws_security_group.endpoints.id
  description       = "HTTPS from inside the VPC"
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443

  tags = local.tags
}

resource "aws_vpc_endpoint" "interface" {
  for_each = local.interface_endpoint_services

  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.endpoints.id]

  tags = merge(local.tags, { Name = "${local.name}-${replace(each.key, ".", "-")}" })
}
