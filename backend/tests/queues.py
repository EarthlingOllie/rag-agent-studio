"""The two job queues' settings (ticket 22-03), for tests that build Settings by hand."""

QUEUE_SETTINGS = {
    "general_queue_name": "studio-general",
    "general_queue_url": "https://sqs.eu-west-2.amazonaws.com/000000000000/studio-general",
    "runs_queue_name": "studio-runs",
    "runs_queue_url": "https://sqs.eu-west-2.amazonaws.com/000000000000/studio-runs",
}
