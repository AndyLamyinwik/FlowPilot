export interface Schedule {
  workflow_id: string
  enabled: boolean
  cron: string | null
  timezone: string | null
  next_run_at: string | null
  scheduler_running: boolean
  last_error: string | null
}
