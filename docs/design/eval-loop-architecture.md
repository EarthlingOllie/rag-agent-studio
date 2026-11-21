# Evaluation loop architecture

What is built and what is planned, drawn from the code in `backend/app/evaluation/` and specs 14–16.

| Spec | Scope | Status |
|---|---|---|
| [14 Evaluation loop](../specs/14-evaluation-loop-spec.md) | Evaluation Set, two-sided Evaluation Runs, judge, Publish summary, Rollout evaluation | **Implemented** (tickets 14-01…14-11 done) |
| [15 Live evaluation](../specs/15-live-evaluation-spec.md) | Live sample rate, Live Verdicts, Live score, drop alert, Evaluation budget | **Proposed** (ready-for-agent) |
| [16 Suggestions](../specs/16-suggestions-spec.md) | Suggestion runs: evidence → proposal → check → apply to Draft | **Proposed** (ready-for-agent) |

The offline Attack evaluation suite (`backend/app/evals/`, spec 08) tests the Guardrails only. It sits outside this loop, so it isn't drawn.

## 1. The loop end to end

Solid green nodes are implemented. Dashed amber nodes are proposed.

```mermaid
flowchart LR
    classDef impl fill:#dcfce7,stroke:#15803d,color:#14532d
    classDef prop fill:#fef3c7,stroke:#b45309,color:#78350f,stroke-dasharray:5 4
    classDef ext fill:#e5e7eb,stroke:#6b7280,color:#111827

    Visitor(["Visitor"]):::ext
    Editor(["Editor"]):::ext

    subgraph Serve["Serving"]
        Reply["Visitor reply<br/>Guardrail pipeline run_turn"]:::impl
        Msg[("Agent Message + Trace")]:::impl
        Fb["Message Feedback /<br/>Conversation Rating"]:::impl
    end

    subgraph S14["Spec 14 - Evaluation loop (implemented)"]
        Prefill["from_message.prefill<br/>Add to Evaluation Set"]:::impl
        Set[("Evaluation Set<br/>EvaluationCase + Expected sources")]:::impl
        Est["estimate.estimate<br/>Cost estimate"]:::impl
        Start["service.start_run<br/>snapshot sides + cases"]:::impl
        Job["job.run_evaluation<br/>Celery task"]:::impl
        Checks["expectations<br/>expected_source / fallback"]:::impl
        Judge["judge.judge<br/>reference_answer / grounding"]:::impl
        Comb["combining<br/>majority of repeats, score"]:::impl
        Summ["summary.publish_summary<br/>Regressions, stale, score drop"]:::impl
        Roll["rollout.start_rollout<br/>Rollout evaluation"]:::impl
    end

    subgraph S15["Spec 15 - Live evaluation (proposed)"]
        Sample{"Sample?<br/>Live sample rate,<br/>budget not spent"}:::prop
        LiveJob["Live judging task"]:::prop
        LV[("Live Verdict<br/>grounded + answers_question")]:::prop
        Budget[("Evaluation budget<br/>monthly spend")]:::prop
        LScore["Live score<br/>analytics rollup + Wilson"]:::prop
        Alert["Live score drop alert<br/>hourly z-test"]:::prop
    end

    subgraph S16["Spec 16 - Suggestions (proposed)"]
        Evid["Gather evidence<br/>max 50"]:::prop
        Propose["Propose<br/>Evaluation Model, structured"]:::prop
        Sugg[("Suggestion<br/>changes + KB gaps")]:::prop
        Check["Check<br/>Run kind=suggestion"]:::prop
        Apply["Apply to Draft<br/>3-way merge, clashes"]:::prop
    end

    Draft[("Draft")]:::impl
    Publish["Publish / Bulk publish"]:::impl
    Live[("Live Version")]:::impl

    Visitor --> Reply --> Msg
    Visitor --> Fb
    Live --> Reply

    Msg --> Prefill --> Set
    Editor -->|"writes / copies cases"| Set
    Editor -->|"Evaluate"| Est --> Start
    Set --> Start
    Draft --> Start
    Live --> Start
    Start --> Job
    Job --> Checks
    Job --> Judge
    Checks --> Comb
    Judge --> Comb
    Comb --> Summ --> Publish
    Publish -->|"rollout dialog"| Roll --> Start
    Draft --> Publish --> Live

    Reply -.-> Sample -.->|"chosen"| LiveJob
    LiveJob -.->|"reuses judge"| Judge
    LiveJob -.-> LV
    LiveJob -.->|"adds Cost"| Budget
    Budget -.-> Sample
    LV -.-> LScore -.-> Alert
    Alert -.->|"email Owners"| Editor
    LV -.->|"failed reply"| Prefill

    LV -.-> Evid
    Fb -.-> Evid
    Comb -.->|"failed cases on Live"| Evid
    Evid -.-> Propose -.-> Sugg
    Sugg -.-> Check -.->|"Run with suggestion side"| Start
    Sugg -.-> Apply -.-> Draft
```

## 2. Domain model

`<<implemented>>` classes exist in `backend/app/evaluation/models.py`. `<<proposed>>` classes and members marked `[proposed]`, and the `suggestion` run and side kinds, come from specs 15 and 16.

```mermaid
classDiagram
    direction LR

    class Agent {
        <<existing>>
        uuid id
        bool live_score_drop_alert [proposed]
    }
    class OperationalSettings {
        <<existing>>
        int live_sample_rate [proposed, 0-100]
    }
    class AgentMessage {
        <<existing>>
        text answer
        jsonb trace
    }

    class EvaluationModel {
        <<implemented>>
        uuid organisation_id
        uuid credential_id
        str model
    }
    class EvaluationCase {
        <<implemented>>
        text question
        text reference_answer
        bool expect_fallback
        CaseSource source
    }
    class EvaluationExpectedSource {
        <<implemented>>
        uuid document_id
        str document_name
        text passage
        bool stale
        StaleReason stale_reason
    }
    class EvaluationRun {
        <<implemented>>
        RunStatus status
        RunKind kind
        str judge_model
        int repeats
        int answers_done
        int answers_total
        decimal estimated_cost_usd
    }
    class EvaluationRunSide {
        <<implemented>>
        str position
        SideKind kind
        uuid agent_version_id
        int draft_revision
        text instructions
        jsonb config
        str chat_model
    }
    class EvaluationRunCase {
        <<implemented>>
        text question
        text reference_answer
        bool expect_fallback
        jsonb expected_sources
    }
    class EvaluationCaseResult {
        <<implemented>>
        int repeat
        ResultStatus status
        text answer
        jsonb trace
        decimal cost_usd
        decimal judge_cost_usd
    }
    class EvaluationVerdict {
        <<implemented>>
        VerdictKind kind
        VerdictOutcome outcome
        text reason
    }

    class RunKind {
        <<enumeration>>
        agent
        rollout
        suggestion [proposed]
    }
    class SideKind {
        <<enumeration>>
        draft
        version
        rollout
        suggestion [proposed]
    }

    class LiveVerdict {
        <<proposed>>
        status pending/judged/error/skipped
        outcome grounded
        outcome answers_question
        bool passed
        decimal cost_usd
        datetime purged_at
    }
    class EvaluationBudget {
        <<proposed>>
        decimal evaluation_budget_usd
        month spend_so_far
        bool spent_email_sent
    }
    class Suggestion {
        <<proposed>>
        status queued to completed
        date_range days
        uuid base_version_id
        jsonb base_config
        outcome changes/gaps_only/no_change
        decimal cost_proposing
        decimal cost_checking
    }
    class SuggestedChange {
        <<proposed>>
        str path
        any base_value
        any suggested_value
        text explanation
    }
    class KnowledgeBaseGap {
        <<proposed>>
        str topic
        text explanation
    }
    class EvidenceLink {
        <<proposed>>
        kind live_verdict/thumbs_down/low_rating/evaluation_case
        uuid message_or_result_id
    }

    Agent "1" --> "0..200" EvaluationCase : Evaluation Set
    EvaluationCase "1" --> "*" EvaluationExpectedSource
    Agent "1" --> "*" EvaluationRun
    EvaluationRun "1" --> "1..2" EvaluationRunSide
    EvaluationRun "1" --> "*" EvaluationRunCase : frozen copy
    EvaluationRunCase ..> EvaluationCase : copied from
    EvaluationRunCase "1" --> "*" EvaluationCaseResult : per side x repeat
    EvaluationRunSide "1" --> "*" EvaluationCaseResult
    EvaluationCaseResult "1" --> "*" EvaluationVerdict
    EvaluationRun ..> EvaluationModel : judge copied at start
    EvaluationRun ..> RunKind
    EvaluationRunSide ..> SideKind

    Agent "1" --> "1" OperationalSettings
    AgentMessage "1" --> "0..1" LiveVerdict
    LiveVerdict ..> EvaluationModel : judged by
    LiveVerdict ..> EvaluationBudget : spends

    Agent "1" --> "*" Suggestion
    Suggestion "1" --> "*" SuggestedChange
    Suggestion "1" --> "*" KnowledgeBaseGap
    Suggestion "1" --> "*" EvidenceLink
    EvidenceLink ..> LiveVerdict
    EvidenceLink ..> AgentMessage
    EvidenceLink ..> EvaluationCaseResult
    Suggestion "1" --> "0..1" EvaluationRun : check
```

## 3. Implemented: one Evaluation Run

```mermaid
sequenceDiagram
    autonumber
    actor Editor
    participant API as evaluation.api
    participant Svc as evaluation.service
    participant Q as Celery tasks.run_evaluation_task
    participant Job as job.run_evaluation
    participant GP as GuardrailPipeline.run_turn
    participant Ret as retrieval.retrieve
    participant Exp as expectations
    participant J as judge.judge
    participant DB as Postgres

    Editor->>API: POST /evaluation/estimate
    API->>Svc: estimate_run -> plan_run
    Svc-->>Editor: Cost estimate per side
    Editor->>API: POST /evaluation/runs (sides, e.g. Live vs Draft)
    API->>Svc: start_run
    Svc->>DB: refuse if a Run is in progress or the set is empty
    Svc->>DB: insert Run (queued), Sides (config, Instructions, models), RunCases (frozen copies)
    Svc->>Q: enqueue_run(run_id) after commit
    Q->>Job: run_evaluation
    Job->>DB: lock Run, set running
    loop each case, each repeat, each side (sides alternate)
        Job->>DB: refresh status, stop if cancelled
        Job->>GP: run_turn([], config, instructions, question)
        GP->>Ret: Hybrid / Agentic Knowledge Search
        GP-->>Job: DoneEvent (answer, cited, retrieved) or ErrorEvent
        Job->>Exp: check_expected_source / check_fallback (no model)
        Exp->>DB: update Stale flags on the Evaluation Set
        opt Reference answer, or the answer isn't the Fallback Text
            Job->>J: judge(question, answer, cited excerpts, reference)
            J-->>Job: reference_answer and grounding Verdicts, usage
        end
        Job->>DB: CaseResult (answer, trace, cost, judge cost) + Verdicts, answers_done++
    end
    Job->>DB: completed, or failed if every answer errored
    Editor->>API: GET /runs/{id}/results, GET /publish-summary
    API->>Svc: combining.side_result / score, Regressions
    Svc-->>Editor: Evaluation scores, Regressions, Unsteady cases
```

## 4. Proposed: Live Verdicts (spec 15)

```mermaid
sequenceDiagram
    autonumber
    actor Visitor
    participant Serve as Serving path
    participant DB as Postgres
    participant T as Live judging task
    participant J as judge.judge, extended
    participant A as analytics, hourly
    actor Owner

    Visitor->>Serve: question
    Serve-->>Visitor: reply (never waits for judging)
    Serve->>DB: store Message + DoneEvent
    alt not blocked, not Fallback Text, rate > 0, draw < rate, month's budget not spent
        Serve->>DB: LiveVerdict(pending), after commit
        Serve->>T: enqueue
        T->>DB: load Remembered turns, question, Chunks given + cited flags
        alt Message or a turn Purged
            T->>DB: LiveVerdict skipped
        else
            T->>J: grounding + answers_question, no system prompt
            J-->>T: Verdicts + usage, or error (no retry)
            T->>DB: LiveVerdict judged/error, Cost, atomic monthly spend += Cost
            opt spend reaches the budget
                T-->>Owner: budget-spent email, once
            end
        end
    end
    A->>DB: roll up judged/passed per Version per day
    A->>A: Live score + Wilson; z-test vs previous Live Version (>=30, drop >=5pts)
    A-->>Owner: Live score drop alert + email
```

## 5. Proposed: Suggestion run (spec 16)

```mermaid
stateDiagram-v2
    [*] --> queued: Editor starts (range, estimate)
    queued --> gathering
    gathering --> proposing: evidence (failed Live Verdicts, thumbs-down, rating 1-2, failed cases), max 50
    proposing --> failed: model error, timeout, invalid output
    proposing --> completed: no change, or gaps only
    proposing --> completed: changes, no Evaluation Set (Not checked)
    proposing --> checking: changes and an Evaluation Set
    checking --> completed: Run of Live vs suggestion side finished
    queued --> cancelled
    gathering --> cancelled
    proposing --> cancelled
    checking --> cancelled: cancels its Run
    completed --> applied: Apply to Draft (no clashes, revision matches)
    completed --> [*]
    applied --> [*]
    failed --> [*]
    cancelled --> [*]
```
