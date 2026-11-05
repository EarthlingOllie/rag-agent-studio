# The demo environment wires every module with one shared prefix and tag set. CI access (ci-oidc) belongs to infra/bootstrap.
run "wires_every_module_with_the_environment_prefix" {
  command = plan

  assert {
    condition = output.module_names == {
      cache    = "studio-demo-cache"
      cdn      = "studio-demo-cdn"
      database = "studio-demo-database"
      ecs      = "studio-demo-ecs"
      kms      = "studio-demo-kms"
      network  = "studio-demo-network"
      storage  = "studio-demo-storage"
    }
    error_message = "Every module must be named from the demo prefix."
  }

  assert {
    condition     = output.tags == { Environment = "demo", Project = "rag-agent-studio" }
    error_message = "The environment's tags must carry the environment and project."
  }
}

run "rejects_an_unknown_environment" {
  command = plan

  variables {
    environment = "prod"
  }

  expect_failures = [var.environment]
}
