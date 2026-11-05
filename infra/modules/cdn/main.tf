# CDN module (ticket 09-05): one CloudFront distribution serves the Studio, the widget and the API over TLS on its
# default domain, routing by path (ADR-0011).
locals {
  module_name = "cdn"
  name        = "${var.name_prefix}-${local.module_name}"
  tags        = merge(var.tags, { Module = local.module_name, ManagedBy = "terraform" })

  # Every path the distribution serves besides / (the Studio, the default behaviour), in match order.
  # Dynamic paths go to the API: /widget/a/* is the widget shell, whose CSP is set per Agent (ADR-0011).
  dynamic_paths = ["/api/*", "/widget/a/*"]
  static_paths  = ["/embed.js", "/widget/assets/*"]

  custom_domain = var.domain_name != null
}

# Static builds have content-hashed asset names; index.html and embed.js are invalidated by every deploy (spec 09).
resource "aws_cloudfront_cache_policy" "static" {
  name        = "${local.name}-static"
  comment     = "Cached, compressed static Studio and widget assets"
  min_ttl     = 0
  default_ttl = 86400
  max_ttl     = 31536000

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true

    cookies_config {
      cookie_behavior = "none"
    }

    headers_config {
      header_behavior = "none"
    }

    query_strings_config {
      query_string_behavior = "none"
    }
  }
}

# The API and widget shell are per-user and streamed (SSE), so nothing is cached. This is the same as AWS's managed
# CachingDisabled policy, kept here so tests can assert it.
resource "aws_cloudfront_cache_policy" "dynamic" {
  name        = "${local.name}-dynamic"
  comment     = "Never cache the API or the widget shell"
  min_ttl     = 0
  default_ttl = 0
  max_ttl     = 0

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_brotli = false
    enable_accept_encoding_gzip   = false

    cookies_config {
      cookie_behavior = "none"
    }

    headers_config {
      header_behavior = "none"
    }

    query_strings_config {
      query_string_behavior = "none"
    }
  }
}

# Every viewer header except Host (the ALB answers to its own name), every cookie (the Studio session) and every
# query string reach the API (spec 09 story 18).
resource "aws_cloudfront_origin_request_policy" "dynamic" {
  name    = "${local.name}-dynamic"
  comment = "Forward everything the API needs except Host"

  headers_config {
    header_behavior = "allExcept"

    headers {
      items = ["host"]
    }
  }

  cookies_config {
    cookie_behavior = "all"
  }

  query_strings_config {
    query_string_behavior = "all"
  }
}

# The Studio and widget assets are never framed. HSTS covers the distribution's host and its subdomains.
resource "aws_cloudfront_response_headers_policy" "static" {
  #checkov:skip=CKV_AWS_259:Everything but preload is set and asserted; preload commits a registrable domain to browser lists, and the default *.cloudfront.net is not ours.
  name    = "${local.name}-static"
  comment = "Security headers for the Studio and widget assets"

  security_headers_config {
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      override                   = true
    }

    content_type_options {
      override = true
    }

    frame_options {
      frame_option = "DENY"
      override     = true
    }

    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
  }
}

# The widget shell's CSP frame-ancestors comes from each Agent's Allowed Origins (ADR-0011), so CloudFront adds no
# frame or CSP header to API responses and keeps any nosniff the API sent. HSTS is the same everywhere.
resource "aws_cloudfront_response_headers_policy" "dynamic" {
  #checkov:skip=CKV_AWS_259:Everything but preload is set and asserted; preload commits a registrable domain to browser lists, and the default *.cloudfront.net is not ours.
  name    = "${local.name}-dynamic"
  comment = "HSTS and nosniff for API responses"

  security_headers_config {
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      override                   = true
    }

    content_type_options {
      override = false
    }
  }
}

# Deep links into the Studio load index.html (spec 09 story 19). The behaviour is tested in Node next to the code.
resource "aws_cloudfront_function" "spa_fallback" {
  name    = "${local.name}-spa-fallback"
  comment = "Serve the Studio's index.html for client-side routes"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = file("${path.module}/functions/spa-fallback.js")

  tags = merge(local.tags, { Name = "${local.name}-spa-fallback" })
}

resource "aws_cloudfront_distribution" "this" {
  #checkov:skip=CKV_AWS_68:WAF is out of scope for spec 09 (noted as a future addition in front of CloudFront).
  #checkov:skip=CKV2_AWS_47:No WAF, so no Log4j managed rule (spec 09, out of scope); the backend is Python.
  #checkov:skip=CKV_AWS_86:Access logs need a log bucket with ACLs and paid storage the short-lived demo does not need; the API logs every request.
  #checkov:skip=CKV_AWS_374:The demo is shown to reviewers anywhere; there is no audience to restrict by country.
  #checkov:skip=CKV_AWS_310:One region, one ALB and one bucket (spec 09): there is no second origin to fail over to.
  #checkov:skip=CKV_AWS_174:With the default *.cloudfront.net certificate CloudFront fixes the minimum at TLSv1 (ADR-0011); a custom domain gets TLSv1.2_2021, asserted by the tests.
  comment             = "${local.name}: Studio, widget and API"
  enabled             = true
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  price_class         = "PriceClass_100"
  default_root_object = "index.html"
  aliases             = local.custom_domain ? [var.domain_name] : []

  origin {
    origin_id                = "static"
    domain_name              = var.static_bucket_regional_domain_name
    origin_access_control_id = var.static_origin_access_control_id
  }

  # Plain HTTP to the ALB, which admits only CloudFront's prefix list carrying the secret header (ADR-0011).
  origin {
    origin_id   = "api"
    domain_name = var.alb_dns_name

    custom_origin_config {
      origin_protocol_policy   = "http-only"
      http_port                = 80
      https_port               = 443
      origin_ssl_protocols     = ["TLSv1.2"]
      origin_read_timeout      = var.origin_read_timeout
      origin_keepalive_timeout = 60
    }

    custom_header {
      name  = var.origin_header_name
      value = var.origin_header_value
    }
  }

  default_cache_behavior {
    target_origin_id           = "static"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = aws_cloudfront_cache_policy.static.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.static.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_fallback.arn
    }
  }

  # Compression stays off so CloudFront never holds back SSE chunks to compress them.
  dynamic "ordered_cache_behavior" {
    for_each = local.dynamic_paths

    content {
      path_pattern               = ordered_cache_behavior.value
      target_origin_id           = "api"
      viewer_protocol_policy     = "https-only"
      allowed_methods            = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods             = ["GET", "HEAD"]
      compress                   = false
      cache_policy_id            = aws_cloudfront_cache_policy.dynamic.id
      origin_request_policy_id   = aws_cloudfront_origin_request_policy.dynamic.id
      response_headers_policy_id = aws_cloudfront_response_headers_policy.dynamic.id
    }
  }

  dynamic "ordered_cache_behavior" {
    for_each = local.static_paths

    content {
      path_pattern               = ordered_cache_behavior.value
      target_origin_id           = "static"
      viewer_protocol_policy     = "redirect-to-https"
      allowed_methods            = ["GET", "HEAD"]
      cached_methods             = ["GET", "HEAD"]
      compress                   = true
      cache_policy_id            = aws_cloudfront_cache_policy.static.id
      response_headers_policy_id = aws_cloudfront_response_headers_policy.static.id
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # Without a domain CloudFront's own certificate serves *.cloudfront.net, and it fixes the minimum TLS version itself.
  viewer_certificate {
    cloudfront_default_certificate = !local.custom_domain
    acm_certificate_arn            = local.custom_domain ? aws_acm_certificate_validation.this[0].certificate_arn : null
    ssl_support_method             = local.custom_domain ? "sni-only" : null
    minimum_protocol_version       = local.custom_domain ? "TLSv1.2_2021" : "TLSv1"
  }

  tags = merge(local.tags, { Name = local.name })
}

# Optional custom domain (spec 09 story 20): a DNS-validated certificate in us-east-1 and alias records.
data "aws_route53_zone" "this" {
  count = local.custom_domain ? 1 : 0

  name         = coalesce(var.hosted_zone_name, var.domain_name)
  private_zone = false
}

resource "aws_acm_certificate" "this" {
  count = local.custom_domain ? 1 : 0

  region            = "us-east-1" # The only region CloudFront reads certificates from.
  domain_name       = var.domain_name
  validation_method = "DNS"

  tags = merge(local.tags, { Name = var.domain_name })

  lifecycle {
    create_before_destroy = true
  }
}

# One domain, so one validation record. Its name and value are only known once the certificate is requested.
resource "aws_route53_record" "validation" {
  count = local.custom_domain ? 1 : 0

  zone_id         = data.aws_route53_zone.this[0].zone_id
  name            = tolist(aws_acm_certificate.this[0].domain_validation_options)[0].resource_record_name
  type            = tolist(aws_acm_certificate.this[0].domain_validation_options)[0].resource_record_type
  records         = [tolist(aws_acm_certificate.this[0].domain_validation_options)[0].resource_record_value]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "this" {
  count = local.custom_domain ? 1 : 0

  region                  = "us-east-1"
  certificate_arn         = aws_acm_certificate.this[0].arn
  validation_record_fqdns = [aws_route53_record.validation[0].fqdn]
}

resource "aws_route53_record" "alias" {
  for_each = toset(local.custom_domain ? ["A", "AAAA"] : [])

  zone_id = data.aws_route53_zone.this[0].zone_id
  name    = var.domain_name
  type    = each.key

  alias {
    name                   = aws_cloudfront_distribution.this.domain_name
    zone_id                = aws_cloudfront_distribution.this.hosted_zone_id
    evaluate_target_health = false
  }
}
