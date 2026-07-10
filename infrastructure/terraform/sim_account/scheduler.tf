resource "aws_scheduler_schedule_group" "sim_teardowns" {
  name = "loomaris-sim-teardowns"
  tags = { "loomaris:sim-cost-center" = "sim" }
}
