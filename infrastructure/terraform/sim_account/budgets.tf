resource "aws_budgets_budget" "sim_daily" {
  name         = "loomaris-sim-daily"
  budget_type  = "COST"
  limit_amount = "5"
  limit_unit   = "USD"
  time_unit    = "DAILY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["loomaris:sim-cost-center$sim"]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80   # alert at $4/day (80% of $5)
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100  # action at $5/day
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}
