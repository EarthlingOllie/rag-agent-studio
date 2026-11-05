# Module contract for the cdn module (ticket 09-05), at the module seam, with mocked AWS providers.
# Runs that compare resource IDs use `command = apply`: the mock provider only invents them at apply time,
# and it never calls AWS, so apply here creates nothing real.
mock_provider "aws" {
  mock_resource "aws_cloudfront_distribution" {
    defaults = {
      arn            = "arn:aws:cloudfront::123456789012:distribution/E2EXAMPLE0ABCD"
      domain_name    = "d111111abcdef8.cloudfront.net"
      hosted_zone_id = "Z2FDTNDATAQYW2"
    }
  }

  mock_resource "aws_cloudfront_function" {
    defaults = {
      arn = "arn:aws:cloudfront::123456789012:function/studio-demo-cdn-spa-fallback"
    }
  }

  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:123456789012:certificate/11111111-2222-3333-4444-555555555555"
      domain_validation_options = [{
        domain_name           = "studio.example.com"
        resource_record_name  = "_0123456789abcdef.studio.example.com."
        resource_record_type  = "CNAME"
        resource_record_value = "_fedcba9876543210.acm-validations.aws."
      }]
    }
  }

  mock_resource "aws_route53_record" {
    defaults = {
      fqdn = "_0123456789abcdef.studio.example.com"
    }
  }

  mock_data "aws_route53_zone" {
    defaults = {
      zone_id = "Z0123456789EXAMPLEZONE"
    }
  }
}

variables {
  name_prefix                        = "studio-demo"
  tags                               = { Environment = "demo", Project = "rag-agent-studio" }
  static_bucket_regional_domain_name = "studio-demo-static-123456789012.s3.eu-west-2.amazonaws.com"
  static_origin_access_control_id    = "E1OACEXAMPLE01"
  alb_dns_name                       = "studio-demo-ecs-1234567890.eu-west-2.elb.amazonaws.com"
  origin_header_name                 = "X-Origin-Verify"
  origin_header_value                = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}

run "serves_the_studio_from_the_static_bucket_through_origin_access_control" {
  command = apply

  assert {
    condition     = aws_cloudfront_distribution.this.default_cache_behavior[0].target_origin_id == "static"
    error_message = "The default behaviour (/) must serve the Studio from the static bucket."
  }

  assert {
    condition     = aws_cloudfront_distribution.this.default_cache_behavior[0].cache_policy_id == aws_cloudfront_cache_policy.static.id
    error_message = "The Studio must be cached with the static cache policy."
  }

  assert {
    condition = [for o in aws_cloudfront_distribution.this.origin : {
      domain = o.domain_name, oac = o.origin_access_control_id, custom = length(o.custom_origin_config)
    } if o.origin_id == "static"] == [{ domain = var.static_bucket_regional_domain_name, oac = var.static_origin_access_control_id, custom = 0 }]
    error_message = "The static origin must be the bucket's regional domain, signed with origin access control."
  }

  assert {
    condition     = aws_cloudfront_distribution.this.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https"
    error_message = "Viewers of the Studio must be redirected to HTTPS."
  }

  assert {
    condition     = aws_cloudfront_distribution.this.default_root_object == "index.html"
    error_message = "The distribution root must serve the Studio's index.html."
  }

  assert {
    condition     = aws_cloudfront_distribution.this.price_class == "PriceClass_100" && aws_cloudfront_distribution.this.enabled
    error_message = "The distribution must be enabled, at price class 100 (spec 09)."
  }

  assert {
    condition     = aws_cloudfront_distribution.this.viewer_certificate[0].cloudfront_default_certificate && length(aws_cloudfront_distribution.this.aliases) == 0
    error_message = "Without a domain, TLS must use the default *.cloudfront.net certificate (ADR-0011)."
  }

  assert {
    condition     = output.url == "https://d111111abcdef8.cloudfront.net" && output.certificate_arn == null
    error_message = "Without a domain, the URL must be the distribution's default domain over HTTPS, with no certificate."
  }

  assert {
    condition     = output.distribution_arn == "arn:aws:cloudfront::123456789012:distribution/E2EXAMPLE0ABCD"
    error_message = "The module must output the distribution ARN for the static bucket policy."
  }
}

run "serves_embed_js_and_widget_assets_from_the_static_bucket_cached" {
  command = apply

  assert {
    condition = { for b in aws_cloudfront_distribution.this.ordered_cache_behavior : b.path_pattern => {
      origin = b.target_origin_id, cache = b.cache_policy_id, methods = toset(b.allowed_methods), compress = b.compress, viewer = b.viewer_protocol_policy
      } if contains(["/embed.js", "/widget/assets/*"], b.path_pattern) } == {
      "/embed.js"        = { origin = "static", cache = aws_cloudfront_cache_policy.static.id, methods = toset(["GET", "HEAD"]), compress = true, viewer = "redirect-to-https" }
      "/widget/assets/*" = { origin = "static", cache = aws_cloudfront_cache_policy.static.id, methods = toset(["GET", "HEAD"]), compress = true, viewer = "redirect-to-https" }
    }
    error_message = "/embed.js and /widget/assets/* must each have a cached, compressed, read-only behaviour on the static bucket."
  }

  assert {
    condition     = alltrue([for b in aws_cloudfront_distribution.this.ordered_cache_behavior : length(b.function_association) == 0 if b.target_origin_id == "static"])
    error_message = "Widget assets must not be rewritten by the Studio's SPA fallback: a missing asset is a 404."
  }
}

# What the function does is tested in Node (functions/spa-fallback.test.mjs); this asserts it is the one deployed.
run "a_function_gives_the_studio_spa_fallback_routing" {
  command = apply

  assert {
    condition = (
      aws_cloudfront_function.spa_fallback.runtime == "cloudfront-js-2.0" && aws_cloudfront_function.spa_fallback.publish &&
      aws_cloudfront_function.spa_fallback.code == file("functions/spa-fallback.js")
    )
    error_message = "The published SPA fallback function must be exactly functions/spa-fallback.js, on the 2.0 runtime."
  }

  assert {
    condition = [for f in aws_cloudfront_distribution.this.default_cache_behavior[0].function_association : {
      event = f.event_type, arn = f.function_arn
    }] == [{ event = "viewer-request", arn = aws_cloudfront_function.spa_fallback.arn }]
    error_message = "The Studio's default behaviour must run the SPA fallback on viewer requests."
  }

  assert {
    condition     = length(aws_cloudfront_distribution.this.custom_error_response) == 0
    error_message = "No distribution-wide error page: it would turn the API's 403s and 404s into the Studio's HTML."
  }
}

run "caches_static_paths" {
  command = plan

  assert {
    condition = (
      aws_cloudfront_cache_policy.static.default_ttl == 86400 && aws_cloudfront_cache_policy.static.max_ttl == 31536000 &&
      aws_cloudfront_cache_policy.static.parameters_in_cache_key_and_forwarded_to_origin[0].enable_accept_encoding_brotli &&
      aws_cloudfront_cache_policy.static.parameters_in_cache_key_and_forwarded_to_origin[0].enable_accept_encoding_gzip
    )
    error_message = "Static assets must be cached for a day by default, up to a year, with gzip and brotli variants."
  }

  assert {
    condition = (
      aws_cloudfront_cache_policy.static.parameters_in_cache_key_and_forwarded_to_origin[0].cookies_config[0].cookie_behavior == "none" &&
      aws_cloudfront_cache_policy.static.parameters_in_cache_key_and_forwarded_to_origin[0].headers_config[0].header_behavior == "none" &&
      aws_cloudfront_cache_policy.static.parameters_in_cache_key_and_forwarded_to_origin[0].query_strings_config[0].query_string_behavior == "none"
    )
    error_message = "Static assets must not vary on cookies, headers or query strings, so they never leak a session into the cache."
  }
}

run "gives_each_path_its_own_behaviour" {
  command = plan

  assert {
    condition     = [for b in aws_cloudfront_distribution.this.ordered_cache_behavior : b.path_pattern] == ["/api/*", "/widget/a/*", "/embed.js", "/widget/assets/*"]
    error_message = "Besides / (the default), exactly /api/*, /widget/a/*, /embed.js and /widget/assets/* must each have a behaviour (spec 09 story 17)."
  }

  assert {
    condition     = toset([for o in aws_cloudfront_distribution.this.origin : o.origin_id]) == toset(["static", "api"])
    error_message = "The distribution must have exactly two origins: the static bucket and the ALB."
  }
}

run "routes_the_api_and_widget_shell_to_the_alb_uncached" {
  command = apply

  assert {
    condition = { for b in aws_cloudfront_distribution.this.ordered_cache_behavior : b.path_pattern => {
      origin  = b.target_origin_id, cache = b.cache_policy_id, request = b.origin_request_policy_id, compress = b.compress, viewer = b.viewer_protocol_policy, functions = length(b.function_association)
      methods = toset(b.allowed_methods)
      } if b.target_origin_id != "static" } == {
      "/api/*" = {
        origin  = "api", cache = aws_cloudfront_cache_policy.dynamic.id, request = aws_cloudfront_origin_request_policy.dynamic.id, compress = false, viewer = "https-only", functions = 0
        methods = toset(["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"])
      }
      "/widget/a/*" = {
        origin  = "api", cache = aws_cloudfront_cache_policy.dynamic.id, request = aws_cloudfront_origin_request_policy.dynamic.id, compress = false, viewer = "https-only", functions = 0
        methods = toset(["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"])
      }
    }
    error_message = "/api/* and /widget/a/* must go to the ALB uncached, with every method, no SPA rewrite, and no compression that would buffer SSE."
  }
}

run "never_caches_dynamic_paths" {
  command = plan

  assert {
    condition = (
      aws_cloudfront_cache_policy.dynamic.min_ttl == 0 && aws_cloudfront_cache_policy.dynamic.default_ttl == 0 && aws_cloudfront_cache_policy.dynamic.max_ttl == 0 &&
      !aws_cloudfront_cache_policy.dynamic.parameters_in_cache_key_and_forwarded_to_origin[0].enable_accept_encoding_gzip &&
      !aws_cloudfront_cache_policy.dynamic.parameters_in_cache_key_and_forwarded_to_origin[0].enable_accept_encoding_brotli
    )
    error_message = "The dynamic cache policy must cache nothing: every TTL is 0."
  }
}

run "forwards_viewer_headers_cookies_and_query_strings_to_the_api" {
  command = plan

  assert {
    condition = (
      aws_cloudfront_origin_request_policy.dynamic.headers_config[0].header_behavior == "allExcept" &&
      aws_cloudfront_origin_request_policy.dynamic.headers_config[0].headers[0].items == toset(["host"])
    )
    error_message = "Every viewer header except Host must reach the API (spec 09); Host must be the ALB's own name."
  }

  assert {
    condition = (
      aws_cloudfront_origin_request_policy.dynamic.cookies_config[0].cookie_behavior == "all" &&
      aws_cloudfront_origin_request_policy.dynamic.query_strings_config[0].query_string_behavior == "all"
    )
    error_message = "Every cookie (the Studio session) and query string must reach the API."
  }
}

run "the_alb_origin_carries_the_secret_header_and_a_long_read_timeout" {
  command = plan

  assert {
    condition = nonsensitive([for o in aws_cloudfront_distribution.this.origin : {
      domain = o.domain_name, oac = coalesce(o.origin_access_control_id, "none"), protocol = o.custom_origin_config[0].origin_protocol_policy, port = o.custom_origin_config[0].http_port
      read   = o.custom_origin_config[0].origin_read_timeout, keepalive = o.custom_origin_config[0].origin_keepalive_timeout
    } if o.origin_id == "api"]) == [{ domain = var.alb_dns_name, oac = "none", protocol = "http-only", port = 80, read = 60, keepalive = 60 }]
    error_message = "The API origin must be the ALB over plain HTTP on 80 (ADR-0011), with a 60 s read timeout for SSE."
  }

  assert {
    condition = [for o in aws_cloudfront_distribution.this.origin : [for h in o.custom_header : { name = h.name, value = h.value }] if o.origin_id == "api"] == [[{
      name = "X-Origin-Verify", value = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }]]
    error_message = "Every request to the ALB must carry the origin header secret, or the ALB answers 403 (ADR-0011)."
  }

  assert {
    condition     = alltrue([for o in aws_cloudfront_distribution.this.origin : length(o.custom_header) == 0 if o.origin_id == "static"])
    error_message = "The origin secret must never be sent to S3."
  }
}

run "the_read_timeout_is_configurable" {
  command = plan

  variables {
    origin_read_timeout = 180
  }

  assert {
    condition     = [for o in aws_cloudfront_distribution.this.origin : o.custom_origin_config[0].origin_read_timeout if o.origin_id == "api"] == [180]
    error_message = "The ALB origin's read timeout must follow origin_read_timeout."
  }
}

run "rejects_a_read_timeout_cloudfront_does_not_allow" {
  command = plan

  variables {
    origin_read_timeout = 181
  }

  expect_failures = [var.origin_read_timeout]
}

run "rejects_a_short_read_timeout" {
  command = plan

  variables {
    origin_read_timeout = 29
  }

  expect_failures = [var.origin_read_timeout]
}

run "rejects_an_origin_that_is_not_an_alb" {
  command = plan

  variables {
    alb_dns_name = "example.com"
  }

  expect_failures = [var.alb_dns_name]
}

run "rejects_a_short_origin_secret" {
  command = plan

  variables {
    origin_header_value = "short"
  }

  expect_failures = [var.origin_header_value]
}

run "rejects_an_invalid_header_name" {
  command = plan

  variables {
    origin_header_name = "X Origin Verify"
  }

  expect_failures = [var.origin_header_name]
}

run "adds_security_headers_without_overriding_the_api" {
  command = apply

  assert {
    condition = concat(
      [aws_cloudfront_distribution.this.default_cache_behavior[0].response_headers_policy_id],
      [for b in aws_cloudfront_distribution.this.ordered_cache_behavior : b.response_headers_policy_id if b.target_origin_id == "static"]
    ) == [for i in range(3) : aws_cloudfront_response_headers_policy.static.id]
    error_message = "The Studio, embed.js and widget assets must all get the static security headers."
  }

  assert {
    condition     = [for b in aws_cloudfront_distribution.this.ordered_cache_behavior : b.response_headers_policy_id if b.target_origin_id == "api"] == [for i in range(2) : aws_cloudfront_response_headers_policy.dynamic.id]
    error_message = "The API and widget shell must get the dynamic security headers."
  }

  assert {
    condition = [for c in aws_cloudfront_response_headers_policy.static.security_headers_config : {
      hsts    = c.strict_transport_security[0].access_control_max_age_sec, hsts_override = c.strict_transport_security[0].override, subdomains = c.strict_transport_security[0].include_subdomains
      nosniff = length(c.content_type_options), frame = c.frame_options[0].frame_option, referrer = c.referrer_policy[0].referrer_policy
    }] == [{ hsts = 31536000, hsts_override = true, subdomains = true, nosniff = 1, frame = "DENY", referrer = "strict-origin-when-cross-origin" }]
    error_message = "Static responses must carry HSTS for a year, nosniff, a strict referrer policy, and must never be framed."
  }

  assert {
    condition = [for c in aws_cloudfront_response_headers_policy.dynamic.security_headers_config : {
      hsts             = c.strict_transport_security[0].access_control_max_age_sec, hsts_override = c.strict_transport_security[0].override, subdomains = c.strict_transport_security[0].include_subdomains
      nosniff_override = c.content_type_options[0].override, frame = length(c.frame_options), csp = length(c.content_security_policy)
    }] == [{ hsts = 31536000, hsts_override = true, subdomains = true, nosniff_override = false, frame = 0, csp = 0 }]
    error_message = "API responses get HSTS, and nosniff unless the API set one, but never a frame or CSP header: the widget shell's frame-ancestors comes from each Agent's Allowed Origins."
  }
}

run "without_a_domain_there_is_no_certificate_or_dns" {
  command = plan

  assert {
    condition = (
      length(data.aws_route53_zone.this) == 0 && length(aws_acm_certificate.this) == 0 &&
      length(aws_acm_certificate_validation.this) == 0 && length(aws_route53_record.validation) == 0 && length(aws_route53_record.alias) == 0
    )
    error_message = "Without domain_name the module must create no ACM certificate and no Route 53 records."
  }
}

run "a_domain_adds_an_acm_certificate_in_us_east_1" {
  command = apply

  variables {
    domain_name = "studio.example.com"
  }

  assert {
    condition = (
      aws_acm_certificate.this[0].region == "us-east-1" && aws_acm_certificate.this[0].domain_name == "studio.example.com" &&
      aws_acm_certificate.this[0].validation_method == "DNS" && aws_acm_certificate_validation.this[0].region == "us-east-1"
    )
    error_message = "A domain must get a DNS-validated ACM certificate in us-east-1, the only region CloudFront reads certificates from."
  }

  assert {
    condition = (
      data.aws_route53_zone.this[0].name == "studio.example.com" && !data.aws_route53_zone.this[0].private_zone &&
      aws_route53_record.validation[0].zone_id == "Z0123456789EXAMPLEZONE" &&
      aws_route53_record.validation[0].name == "_0123456789abcdef.studio.example.com." &&
      aws_route53_record.validation[0].type == "CNAME" &&
      aws_route53_record.validation[0].records == toset(["_fedcba9876543210.acm-validations.aws."])
    )
    error_message = "The certificate's DNS validation record must be written into the domain's public hosted zone."
  }

  assert {
    condition     = aws_acm_certificate_validation.this[0].validation_record_fqdns == toset(["_0123456789abcdef.studio.example.com"])
    error_message = "The distribution must wait for the certificate to validate through that record."
  }

  assert {
    condition = (
      aws_cloudfront_distribution.this.aliases == toset(["studio.example.com"]) &&
      !aws_cloudfront_distribution.this.viewer_certificate[0].cloudfront_default_certificate &&
      aws_cloudfront_distribution.this.viewer_certificate[0].acm_certificate_arn == aws_acm_certificate.this[0].arn &&
      aws_cloudfront_distribution.this.viewer_certificate[0].ssl_support_method == "sni-only" &&
      aws_cloudfront_distribution.this.viewer_certificate[0].minimum_protocol_version == "TLSv1.2_2021"
    )
    error_message = "With a domain, the distribution must answer on it with the ACM certificate over SNI and TLS 1.2 or later."
  }
}

run "a_domain_adds_route53_alias_records" {
  command = apply

  variables {
    domain_name = "studio.example.com"
  }

  assert {
    condition = { for k, r in aws_route53_record.alias : k => {
      zone = r.zone_id, name = r.name, type = r.type, target = r.alias[0].name, target_zone = r.alias[0].zone_id
      } } == {
      A    = { zone = "Z0123456789EXAMPLEZONE", name = "studio.example.com", type = "A", target = "d111111abcdef8.cloudfront.net", target_zone = "Z2FDTNDATAQYW2" }
      AAAA = { zone = "Z0123456789EXAMPLEZONE", name = "studio.example.com", type = "AAAA", target = "d111111abcdef8.cloudfront.net", target_zone = "Z2FDTNDATAQYW2" }
    }
    error_message = "The domain must have IPv4 and IPv6 alias records pointing at the distribution."
  }

  assert {
    condition     = output.url == "https://studio.example.com" && output.certificate_arn == aws_acm_certificate.this[0].arn
    error_message = "With a domain, the URL must be the domain over HTTPS, and the certificate ARN must be output."
  }
}

run "a_subdomain_can_live_in_its_parent_zone" {
  command = apply

  variables {
    domain_name      = "studio.example.com"
    hosted_zone_name = "example.com"
  }

  assert {
    condition     = data.aws_route53_zone.this[0].name == "example.com" && aws_route53_record.alias["A"].name == "studio.example.com"
    error_message = "hosted_zone_name must choose the zone that holds the domain's records."
  }
}

run "rejects_a_domain_that_is_not_a_hostname" {
  command = plan

  variables {
    domain_name = "https://studio.example.com"
  }

  expect_failures = [var.domain_name]
}

run "rejects_a_hosted_zone_without_a_domain" {
  command = plan

  variables {
    hosted_zone_name = "example.com"
  }

  expect_failures = [var.hosted_zone_name]
}

run "every_resource_carries_the_standard_tags" {
  command = plan

  variables {
    domain_name = "studio.example.com"
  }

  assert {
    condition = alltrue([for t in [
      aws_cloudfront_distribution.this.tags, aws_cloudfront_function.spa_fallback.tags, aws_acm_certificate.this[0].tags
    ] : t.Project == "rag-agent-studio" && t.Environment == "demo" && t.ManagedBy == "terraform" && t.Module == "cdn"])
    error_message = "Every taggable resource must carry the project, environment, managed-by and module tags (spec 09 story 33)."
  }
}

run "names_resources_from_the_prefix" {
  command = plan

  assert {
    condition     = output.name == "studio-demo-cdn"
    error_message = "The cdn name must be derived from name_prefix."
  }

  assert {
    condition     = output.tags == { Environment = "demo", Project = "rag-agent-studio", Module = "cdn", ManagedBy = "terraform" }
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
