# Bundled Terraform ruleset with every rule on. Spec 09 adds the AWS ruleset once modules create AWS resources.
config {
  call_module_type = "local"
}

plugin "terraform" {
  enabled = true
  preset  = "all"
}
