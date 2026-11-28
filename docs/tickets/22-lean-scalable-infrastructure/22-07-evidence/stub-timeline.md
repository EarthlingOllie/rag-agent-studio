# The scaling script's output in scale.test.sh's happy path (stubbed aws and a fake Studio, 1-second polls, not AWS)

```text
==> terraform init (state bucket rag-agent-studio-tfstate-123456789012)
Created the Project 'Scaling demonstration 2026-11-27T00:02:39Z'.
Uploaded 20 Documents (5 copies of each seed Document) to 'Scaling demonstration 2026-11-27T00:02:39Z'.
Sending API requests from 2 loops for 1 seconds.

time      elapsed  general queue  runs queue  api    worker-general  worker-runs
(queues: waiting+in flight jobs; services: running/desired tasks)
Started an Evaluation Run on HR helper.
No Evaluation Run on Product FAQ: The Evaluation Set is empty.
00:02:40  00:00    0+0            0+0         1/1    1/1             0/0
00:02:40  00:01    14+2           1+0         1/2    1/3             0/1
00:02:40  00:02    8+6            0+1         2/3    3/3             1/1
00:02:40  00:03    0+4            0+0         3/3    3/3             1/1
00:02:40  00:04    0+0            -+-         2/1    2/1             0/0
00:02:40  00:05    0+0            0+0         1/1    1/1             0/0

289 API requests sent; 1 Evaluation Runs started.
Every service scaled out and back to its minimum: api 1 -> 3 -> 1, worker-general 1 -> 3 -> 1, worker-runs 0 -> 1 -> 0.
Deleted the Project 'Scaling demonstration 2026-11-27T00:02:39Z'.
```

The timeline from a real deploy is ticket 22-09's evidence.
