# Module contract for the ecs stub: inputs are validated and outputs are stable.
variables {
  name_prefix = "studio-demo"
  tags        = { Environment = "demo" }
}

run "names_resources_from_the_prefix" {
  command = plan

  assert {
    condition     = output.name == "studio-demo-ecs"
    error_message = "The ecs name must be derived from name_prefix."
  }

  assert {
    condition     = output.tags == { Environment = "demo", Module = "ecs", ManagedBy = "terraform" }
    error_message = "Tags must merge the caller's tags with the module's own."
  }
}

run "rejects_an_invalid_prefix" {
  command = plan

  variables {
    name_prefix = "Studio_Demo"
  }

  expect_failures = [var.name_prefix]
}
