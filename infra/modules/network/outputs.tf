output "name" {
  description = "Name the module gives its resources."
  value       = local.name
}

output "tags" {
  description = "Tags the module applies to its resources."
  value       = local.tags
}

output "availability_zones" {
  description = "The two availability zones the VPC spans."
  value       = local.azs
}

output "vpc_id" {
  description = "ID of the VPC."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "CIDR block of the VPC."
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "Public subnet IDs, one per AZ, for the ALB and the NAT."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs, one per AZ, for ECS tasks, RDS and ElastiCache."
  value       = aws_subnet.private[*].id
}

output "nat_mode" {
  description = "How private subnets reach the internet: fck-nat or managed."
  value       = local.nat_mode
}

output "nat_public_ip" {
  description = "Elastic IP that private-subnet egress leaves from, for allowlists."
  value       = aws_eip.nat.public_ip
}

output "private_route_table_id" {
  description = "Route table shared by the private subnets."
  value       = aws_route_table.private.id
}

output "vpc_endpoints" {
  description = "Every VPC endpoint the module creates, as service name to endpoint type. Only the S3 gateway: no interface endpoints."
  value       = { (aws_vpc_endpoint.s3.service_name) = aws_vpc_endpoint.s3.vpc_endpoint_type }
}
