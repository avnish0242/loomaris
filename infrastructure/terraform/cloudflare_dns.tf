# ─── ACM certificate DNS validation ──────────────────────────────────────────
# proxied=false required — ACM validation must resolve directly, not through Cloudflare proxy

resource "cloudflare_record" "cert_validation" {
  for_each = {
    for record in distinct([
      for dvo in aws_acm_certificate.main.domain_validation_options : {
        name    = dvo.resource_record_name
        content = dvo.resource_record_value
        type    = dvo.resource_record_type
      }
    ]) : record.name => record
  }

  zone_id = var.cloudflare_zone_id
  name    = each.value.name
  content = each.value.content
  type    = each.value.type
  ttl     = 60
  proxied = false
}

# ─── App subdomains → ALB ─────────────────────────────────────────────────────
# proxied=false — ALB terminates TLS with the ACM cert; Cloudflare proxy not needed

resource "cloudflare_record" "api" {
  zone_id = var.cloudflare_zone_id
  name    = "api"
  content = aws_lb.main.dns_name
  type    = "CNAME"
  ttl     = 1
  proxied = false
}

resource "cloudflare_record" "app" {
  zone_id = var.cloudflare_zone_id
  name    = "app"
  content = aws_lb.main.dns_name
  type    = "CNAME"
  ttl     = 1
  proxied = false
}

# ─── Apex + www → Netlify corporate site ─────────────────────────────────────

resource "cloudflare_record" "apex_netlify" {
  zone_id = var.cloudflare_zone_id
  name    = "@"
  content = "75.2.60.5"
  type    = "A"
  ttl     = 1
  proxied = true
}

resource "cloudflare_record" "www_netlify" {
  zone_id = var.cloudflare_zone_id
  name    = "www"
  content = "75.2.60.5"
  type    = "A"
  ttl     = 1
  proxied = true
}

# ─── Zoho Mail ────────────────────────────────────────────────────────────────

resource "cloudflare_record" "zoho_mx1" {
  zone_id  = var.cloudflare_zone_id
  name     = "@"
  content  = "mx.zoho.com"
  type     = "MX"
  ttl      = 300
  priority = 10
}

resource "cloudflare_record" "zoho_mx2" {
  zone_id  = var.cloudflare_zone_id
  name     = "@"
  content  = "mx2.zoho.com"
  type     = "MX"
  ttl      = 300
  priority = 20
}

resource "cloudflare_record" "zoho_mx3" {
  zone_id  = var.cloudflare_zone_id
  name     = "@"
  content  = "mx3.zoho.com"
  type     = "MX"
  ttl      = 300
  priority = 50
}

resource "cloudflare_record" "zoho_spf" {
  zone_id = var.cloudflare_zone_id
  name    = "@"
  content = "v=spf1 include:zoho.com ~all"
  type    = "TXT"
  ttl     = 300
}

resource "cloudflare_record" "zoho_dkim" {
  zone_id = var.cloudflare_zone_id
  name    = "zmail._domainkey"
  content = "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDI6GZryaW6P8L0K58Y3Qd4QuoX72m8n5ni0mbQiS4oUVHXsAheo42/JSLPcR7/EeEU8Vivh9Z2VrUoc78cGmVyOpFFTdzeh6vRBOs5+3HkiY8AUE7OSpI0OBJmgqUSklvIKrX1QrjAuRgLbUV2wnTMmUZkvy/LP1WtnUiG+rfZKwIDAQAB"
  type    = "TXT"
  ttl     = 300
  proxied = false
}
