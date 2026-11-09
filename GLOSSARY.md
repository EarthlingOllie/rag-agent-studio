# RAG Agent Studio

A studio where Organisations build Agents grounded in a Knowledge Base, inside isolated Projects, and embed them on their own sites.

## Tenancy

**Organisation**:
The tenant. Owns Members, Projects and Provider Credentials.
_Avoid_: Tenant, account, company

**Theme**:
An Organisation's visual styling for embedded Agents: Colour Tokens, corner radius, a font from the Font Allowlist, a Theme Mode, a Launcher, and its Theme Images. Owners change it and every Member can view it; a saved change applies at once, with no publishing. An Agent may override its colours and avatar.
_Avoid_: Branding, skin, styles

**Colour Token**:
A named Theme colour with a light-mode and a dark-mode value: primary, on-primary, surface, on-surface, accent and muted. An "on-" token is the text colour used on the token it names.
_Avoid_: Palette entry, swatch

**Font Allowlist**:
The curated Google Fonts a Theme may use. The widget never loads a font from anywhere else.
_Avoid_: Font list, web fonts

**Theme Mode**:
Whether the widget uses the Colour Tokens' light values, their dark values, or follows the Visitor's preference (automatic).
_Avoid_: Colour scheme setting, dark mode toggle

**Appearance**:
Whether the Studio itself shows light, dark, or follows the system setting. A Member's choice for their browser, set from the top bar; it never affects the widget, which follows its Theme Mode.
_Avoid_: Theme, Theme Mode, dark mode

**Tidepool**:
The Studio's design system (`docs/design/README.md`, code in `frontend/apps/studio/src/design`): colour tokens with a light and a dark value, class recipes, and the shared components every Studio page is built from (top bar and breadcrumb, menus, dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list). It styles the Studio only, never the widget, which shows the Organisation's Theme.
_Avoid_: Theme, skin, component library

**Breadcrumb**:
The Studio's navigation: the path in the top bar, Organisation / section / item, computed from the page's address. Each level with siblings is a switcher, a menu of them (the Organisation switcher, the Organisation's sections, the Organisation settings areas, the Project switcher, a Project's sections); the last crumb is the page the Member is on. It replaces the side menu and the tab rows. Profile and Sign out are in the account menu beside it.
_Avoid_: Tabs, side menu, nav bar

**Project section**:
One of the six areas of a Project in the Studio, in this order: Documents, Instructions, Agents, Conversations, Analytics and Settings. The Member moves between them with the section switcher, the Breadcrumb's last level inside a Project, which numbers them 1–6. The crumb before it is the Project switcher: the Organisation's open Projects, plus All Projects. Rare actions on the Project itself (Archive, permanent deletion) are in its page header's ⋯ menu, not in a section.
_Avoid_: Tab, page, area

**Palette ratchet**:
The CI check that counts Tailwind palette classes (`slate-700`, `dark:`, `bg-white`…) in the Studio's source and fails when the count rises above the committed baseline (`frontend/palette-baseline.json`). Each reskin slice lowers the baseline; at zero the baseline file goes and none are allowed.
_Avoid_: Lint rule, colour check

**Launcher**:
How the widget appears on the host page: a floating bubble in a bottom corner that opens the chat (filling the screen when open on a phone), or an inline container that shows it in place. The Theme sets it; an Embed Snippet's `data-launcher` (with `data-target` naming the inline container) overrides it on that page. While the bubble is open, Tab stays inside the chat (the focus trap); closing it, with its Close button or Escape, returns focus to the Launcher.
_Avoid_: Chat button, trigger

**Reply announcement**:
What a screen reader hears when an Agent's reply is complete: the Agent's name and the whole reply, read once from the widget's polite status region. The Conversation log itself stays silent, so a streamed reply is never read out token by token; a failed reply is announced by its error instead.
_Avoid_: Live update, toast

**Theme Image**:
One of the two images a Theme can have: the **logo**, shown in the widget's header, and the **default Agent avatar**, shown beside the Agent's name for every Agent without an avatar of its own. Each is a PNG, JPEG or WebP image of at most 1 MB, uploaded straight to object storage, and applies as soon as it is uploaded; Owners replace or remove it.
_Avoid_: Branding asset, icon, picture

**Contrast Warning**:
A notice that a pair of Colour Tokens falls below WCAG AA contrast (4.5:1 for text, 3:1 for the accent against the surface) in a mode the Theme shows. It warns and never blocks saving.
_Avoid_: Contrast error, accessibility check

**Retention Window**:
How long an Organisation keeps Message text and Message Feedback comments before the Purge clears them: 90 days by default, from 7 to 3650, set by Owners in Organisation settings (General). Changes are recorded as Audit Events (`organisation.retention_window_changed`). It applies to every Conversation, Visitors' and the Playground's, archived Agents' and Projects' included. Aggregate metrics are kept.

**Member**:
A person who signs in to the Studio and belongs to one or more Organisations.
_Avoid_: User, admin

**Profile**:
A Member's own details: their name, email and password. It is the same in every Organisation they belong to, and only the Member can change it.
_Avoid_: Account settings, user settings

**Password Reset Link**:
An emailed link that lets a Member who forgot their password choose a new one. It works once and expires; using it, or changing the password from the Profile, signs the Member out everywhere else.
_Avoid_: Recovery link, magic link

**Membership**:
A Member's place in one Organisation, with a role: Owner or Editor. Signing up creates an Organisation and an Owner Membership for the new Member.
_Avoid_: Seat, account

**Active Organisation**:
The Organisation a Member is working in. A Member of several Organisations picks it with the Organisation switcher, the first crumb of the Breadcrumb; the Studio remembers the choice and opens it next time, and otherwise opens their first Organisation. It never grants access: every Organisation page and API route names its Organisation, and a Member reaches only Organisations they have a Membership in.
_Avoid_: Current tenant, workspace, default Organisation

**Invite**:
An Owner's offer of a Membership with a chosen role, addressed to one email. It comes as an Invite Link, emailed or copied by the Owner. It is pending until the invited person accepts it or an Owner revokes it.
_Avoid_: Invitation code, join request

**Invite Link**:
The link that accepts an Invite. It works once and expires; a person without an account creates one from it and joins in one step, and an existing Member just gains the Membership. An Owner can get a new link for a pending Invite, which stops the old one working.
_Avoid_: Join link, magic link

**Lockout**:
A temporary block on signing in, after too many failed attempts for one account or from one IP address. Before it, each further attempt must wait a little longer. A Lockout of a Member's account is recorded as an Audit Event in each of their Organisations.
_Avoid_: Ban, suspension, block

**Owner**:
A Member role that can manage Provider Credentials, Members and Organisation settings, as well as everything an Editor can.

**Editor**:
A Member role that can manage Projects, Documents and Agents.

**Last Owner**:
An Organisation's only remaining Owner. An Organisation always keeps at least one Owner, so the Last Owner can't be demoted, removed or leave; another Member must be made an Owner first.
_Avoid_: Sole admin, primary owner

**Leaving**:
A Member ending their own Membership of an Organisation. Removing is an Owner ending someone else's. Either way, access to that Organisation ends with the next request; the Member keeps their account and their other Memberships.

**MFA**:
Multi-factor authentication: a Member's sign-in also needs a code from an authenticator app (TOTP). It belongs to the Member, so it applies in every Organisation they belong to.
_Avoid_: 2FA, two-step verification (fine in Studio copy, not in code or docs)

**Require MFA policy**:
An Organisation setting, turned on or off by an Owner, that every Member must have MFA. While it is on, a Member without MFA can sign in but can do nothing in that Organisation until they turn MFA on, and no Member can turn MFA off while any of their Organisations has it on. An Owner must have MFA before turning it on.
_Avoid_: Enforce 2FA, mandatory MFA, MFA enforcement

**Recovery Code**:
One of ten single-use codes a Member gets when they turn MFA on, to sign in without their authenticator app. Shown once; making new ones stops the old ones working.
_Avoid_: Backup code

**Audit Event**:
An append-only record of who changed what in an Organisation, and when, with the values before and after the change. Secret-like values are never stored. Only Owners can see Audit Events.
_Avoid_: Activity, history, log

**Demo Organisation**:
The Organisation `make seed` builds for showing the product: Northwind Traders, a fictional company, with a demo Owner and Editor whose sign-in details are published, the Northwind Handbook Project and its synthetic Documents, and the Agents the Demo pages embed (the Product FAQ, the Low-budget helper and the Attack panel's Guardrail demo Agent, which always answers with the Naive demo model), published with the shop origin as their Allowed Origin. A fresh one comes with its Seeded history. It is found through the demo Owner's account. `make seed-reset` erases it, its Audit Events included, and builds it again; no other Organisation can be erased. In the AWS demo the seed workflow builds it the same way, as a one-off ECS task (with a reset option for `make seed-reset`).
_Avoid_: Sample org, test tenant, sandbox

**Seeded history**:
The four weeks the Demo Organisation has lived through by the time `make seed` finishes: Project Instructions v1 and v2 (the Product FAQ left behind on v1, the Low-budget helper and the Guardrail demo Agent rolled out to v2), the HR helper's Versions 1 to 3 with v2 reverted, and Visitor Conversations every day with Message Feedback and Conversation Ratings that make v2 clearly worse and v3 promising on a small sample, rolled up for every day. It is played through the API under a clock set four weeks back, with feedback drawn from a fixed random seed, and is made only when the Demo Organisation is first created.
_Avoid_: Fake data, sample history, fixtures

**Demo pages**:
Static pages that show an Agent the way a Visitor meets it: Northwind's fictional shop with the Product FAQ as a bubble, a help-centre page with it inline, and a page with the Low-budget helper, whose tiny daily Token Budget a button spends in one click (the widget then shows its Unavailable text and the Studio its Budget alert). They are on the shop origin, which the seed allows: `http://localhost:5175/demo/` in `docker compose`, `/demo/` on the Studio's own address in AWS. A fourth page, on an origin no Agent allows (`http://localhost:5176`, local only), pastes the same Embed Snippet and is refused by the browser. The pages ask the API which seeded Agents to embed; those routes exist only when the stack runs with `DEMO_PAGES` on.
_Avoid_: Demo host page (for the shop), test page

**Attack panel**:
The Demo page (`/demo/attacks.html`) with one button per attack category (instruction override, prompt extraction, role-play jailbreak, encoded attack) and a benign control. Each click sends that button's fixed message to the Guardrail demo Agent the way the widget does, as a new Visitor Conversation, and shows the reply as it streams and what each Guardrail layer did: the input Guardrail blocked, flagged, logged or passed it; the Canary token replaced or flagged the reply, stayed quiet, or was not reached because the message was blocked. The Guardrail demo Agent answers with the Naive demo model, so whatever is stopped is stopped by a Guardrail layer. It uses Demo mode's debug endpoint, which returns each answer's Guardrail outcomes without a Studio login.
_Avoid_: Red-team page, jailbreak console

**Five-minute demo**:
The README's scripted tour of the Demo Organisation for someone who has never seen the product, in a fixed order: the Studio, the flagged Chunk in the Document viewer, the Agent editor and a Playground Trace, the HR helper's publish and revert in Live History, the Product FAQ on the shop's Demo page, the disallowed origin, the Attack panel, the spent Token Budget, the analytics comparison of the HR helper's Versions, the Organisation cost page, and the Audit tab. One Playwright test plays the whole script against a seeded stack, so the tour can't silently break.
_Avoid_: Walkthrough, showcase script, smoke test

**Demo mode**:
A stack run with `DEMO_PAGES` on (`docker compose` and the AWS demo): only then do the demo routes exist, the Demo pages' Agent lookup and budget button and the Attack panel's debug endpoint. Without it they answer 404.
_Avoid_: Seed mode, debug mode

**Archive**:
To retire an Agent or Project. It stops serving Visitors but keeps its Versions, Conversations and metrics. An archived Agent leaves the Agents list, its Draft can't be changed and the Playground starts no Conversation with it. Any Member can archive. Permanent deletion is a separate action.
_Avoid_: Disable, soft delete

**Restore**:
To bring an archived Agent or Project back to its list so it serves again. Only Owners can restore.
_Avoid_: Unarchive, undelete

**Permanent deletion**:
Removing an archived Agent or Project for good. An Agent takes its Draft, Conversations and their Messages with it, which releases its Credential references; a Project takes its Documents, Chunks, stored files, Tags, Agents and Conversations, in a background cascade. Only an Owner can do it, only once the Agent or Project is archived, and only after typing its name exactly. It can't be undone; the Audit Event records who deleted it and what it held.
_Avoid_: Purge, hard delete

## Models

**Provider Credential**:
A secret an Organisation stores so it can call a model provider.
_Avoid_: API key, token, connection

**Capability**:
What a Provider Credential can be used for: chat, embeddings or reranking. Each provider offers a fixed set, listed with its models in the capability registry; a credential may be limited to some of them.
_Avoid_: Feature, scope, permission

**Masked suffix**:
The last four characters of a Provider Credential's secret: all of the secret the platform ever shows after it is saved.
_Avoid_: Hint, preview, redacted key

**Credential check**:
A live call to the provider that proves a Provider Credential works, made when it is saved, rotated, or re-checked on demand. It passes or fails with a typed reason (invalid key, missing model access, quota exceeded, provider unreachable; for Bedrock also role not assumable and wrong region). A Bedrock check first assumes the role (or checks the access keys), then checks model access in the credential's region.
_Avoid_: Validation, test call, ping

**Bedrock role**:
An IAM role in an Owner's AWS account that the platform assumes to call Bedrock. The preferred way to connect Bedrock, because no secret is stored; access keys are the fallback.
_Avoid_: Cross-account key, IAM credential, assume-role key

**External ID**:
A stable, unguessable value the platform generates once per Organisation and passes whenever it assumes that Organisation's Bedrock role. The role's trust policy requires it, so no other customer can get the platform to assume the role.
_Avoid_: Shared secret, tenant key, role token

**Trust policy**:
The policy on a Bedrock role that names the platform's AWS principal and requires the Organisation's External ID. The Studio shows it, ready to paste into AWS.
_Avoid_: Role policy, assume-role document

**Assumed-role session**:
Temporary AWS credentials the platform gets by assuming a Bedrock role. Cached per role and External ID, and renewed shortly before it expires.
_Avoid_: STS token, temporary key

**Rotation**:
Replacing a Provider Credential's secret while keeping its identity, so everything that references it keeps working.
_Avoid_: Re-key, replace, regenerate

**Credential reference**:
Something that uses a Provider Credential, such as an Agent's model or a Project's Embedding Model. A credential can't be deleted while any reference to it exists.
_Avoid_: Dependency, usage, link

**Default Model**:
The chat model an Organisation's Agents use unless an Agent overrides it: one chat-capable Provider Credential and one of its chat models, chosen by an Owner. It is a Credential reference, so its credential can't be deleted while it is chosen.
_Avoid_: Global model, org model

**Demo model**:
The demo provider's only chat model. It answers with the first retrieved Chunk, quoted and cited, and every answer starts "Demo model (canned answer, not AI)". It needs no key and calls nothing, so the Demo Organisation works without a real Provider Credential. The Studio labels the provider "Demo: canned answers, not a real model".
_Avoid_: Fake model (that is the test double), mock, stub model

**Naive demo model**:
The demo provider's second chat model (`demo-naive`): the Naive model behind its own label, "Naive demo model (obeys injected instructions, not AI)". The Attack panel's Guardrail demo Agent always answers with it, even when the seed was given a real Provider Credential, so the panel shows the Guardrails at work rather than a model refusing.
_Avoid_: Evil model, unsafe model

**Model gateway**:
The single factory every model call goes through: it turns a Provider Credential and a model name into a chat model, an embedder or a reranker, refusing a model the credential doesn't offer for that Capability. Tests and `docker compose` swap in fake adapters here and nowhere else.
_Avoid_: Model client factory, provider router, LLM proxy

**Reranker**:
A model that reorders retrieved passages by relevance to a query, built by the Model gateway from a credential with the rerank Capability. An Agent's optional Reranker (a rerank-capable credential and one of its rerank models, set in the Draft's Retrieval) scores every Chunk retrieval found before the Minimum Score and Top-k are applied; Chunks are then ordered by its score, which becomes their Relevance. It is a Credential reference.
_Avoid_: Re-ranker, scorer

**Price table**:
The platform's price for each provider's models, in US dollars per million input, output and cached input tokens, each with the date it took effect. It lives in the repo as data and is loaded on every migrate; a new price is a new dated entry, so past costs keep the price they were made at.
_Avoid_: Rate card, price list, pricing

**Price override**:
An Owner's price for one model of one Provider Credential, such as a negotiated rate. Any of the three prices can be overridden; the rest keep the Price table's. Overrides take precedence over the Price table and go with their credential.
_Avoid_: Custom price, discount

**Cost**:
What a model call cost in US dollars: its token counts times the prices in effect when it was made, preferring Price overrides. Unknown when tokens were used at a price nobody has set.
_Avoid_: Spend, charge, bill

**Embedding Model**:
The model that turns Chunks and queries into vectors for a Project. It is the platform's local model unless the Project chooses a provider model (Voyage, OpenAI or Bedrock) through an embedding-capable Provider Credential, which then becomes a Credential reference. It can change at any time: a Project without Documents switches at once, and one with Documents goes through a Re-embed. The model retrieval uses is the **active** one; the one a running Re-embed moves to is the **pending** one.

**Re-embed**:
The background job that moves a Project's Knowledge Base to a new Embedding Model. It writes the pending model's vector for every Chunk next to the active model's, with visible progress, while the active model keeps serving; then, in one step, the pending model becomes active and the old vectors are deleted. Uploads during a Re-embed are embedded with both models. A failed Re-embed leaves the active model unchanged and shows why; choosing again while one runs cancels it.
_Avoid_: Migration, re-index, rebuild

**Embedding Model registry**:
The list, kept in code, of every Embedding Model a Project can use, with its provider, vector dimension, tokenizer, token limit and the Capability its credential needs.
_Avoid_: Model catalogue, embedding config

**Retrieval probe**:
A diagnostic endpoint that returns a Project's top-k Chunks nearest a query by vector alone, using the Project's current Embedding Model. It is for tests and diagnostics, not what Agents retrieve with.
_Avoid_: Search endpoint, retriever

## Knowledge

**Project**:
An isolated container of a Knowledge Base, Project Instructions and Agents. Nothing crosses a Project boundary.
_Avoid_: Workspace, context repository, collection

**Knowledge Base**:
All the Documents and Chunks in a Project.
_Avoid_: Corpus, index, vector store

**Document**:
A file uploaded into a Project's Knowledge Base.
_Avoid_: File, upload, source

**Document status**:
Where a Document is in ingestion: Queued (uploaded, waiting for the worker), Processing (being converted, chunked and embedded), Ready (its Chunks are stored and retrievable) or Failed (with a readable reason).
_Avoid_: State, phase, job status

**Ingestion**:
Turning an uploaded Document into Chunks: convert it with Docling, store the markdown, chunk it with the Embedding Model's tokenizer, embed the Chunks and write them in one transaction.
_Avoid_: Indexing, processing pipeline, import

**OCR**:
A per-Project setting, off by default. When it is on, ingestion also reads text in images, so scanned PDFs become readable. It makes ingestion slower, so it is only turned on for Projects that need it. A change applies to Documents processed afterwards; retrying a Document reprocesses it with the new setting.
_Avoid_: Text recognition, scan mode

**Content hash**:
The SHA-256 of a Document's uploaded bytes, recorded when the upload is confirmed.
_Avoid_: Checksum, fingerprint, etag

**Failure category**:
What kind of failure set a Document to Failed, shown with its readable message: unsupported content (the file isn't what its type says, or has no readable text), conversion error (the converter couldn't convert it, or processing went wrong), provider error (the Embedding Model's provider kept failing after the automatic retries) or quota (the Project's Document quota had no room for it).
_Avoid_: Error code, error type, failure reason

**Retry**:
Sending a Document through ingestion again from its stored file, with its Project's current settings, without uploading it again: a Failed Document, or its Failed new edition, or else a Ready Document's current edition (whose Chunks keep serving until the new ones replace them). Not while the Document, or a new edition of it, is still being processed. An Editor retries by hand; a transient failure (a provider error) is retried automatically, after an exponential backoff, up to a fixed number of attempts.
_Avoid_: Reprocess, re-ingest, re-run

**Document quota**:
The most Documents a Project may hold, not counting Failed ones. Uploads beyond it are refused with a clear message, and a Document processed when the Project is already full fails with the quota category. A new Edition doesn't add a Document, so the quota never refuses one. Every Project starts at 500; an Owner can change it.
_Avoid_: Document limit, storage limit, cap

**Document viewer**:
The Studio page for one Document: its converted markdown beside its Chunks, each with its heading path and page range, and a download of the original file.
_Avoid_: Document preview, inspector, detail page

**Heading path**:
The headings above a Chunk in its Document, outermost first, shown as `Leave › Annual leave`. It is embedded with the Chunk so retrieval knows its context.
_Avoid_: Breadcrumb, section, context
**Duplicate**:
An upload whose Content hash matches a Document already in the Project (its current Edition, or a Staged edition still being ingested). It is refused, naming the Document that has the content. A Failed Document or Failed Staged edition holds no content, so its file is not a Duplicate and can be uploaded again, as a new Document or as the next Edition.
_Avoid_: Copy, clash, repeat upload

**Edition**:
One uploaded version of a Document's file, numbered from 1. Only the current Edition is kept (ADR-0003 versions Agents, not Documents); uploading a newer Edition replaces it in place, keeping the Document's identity and Tags.
_Avoid_: Document version, revision

**Staged edition**:
A newer Edition being ingested. Its Chunks are written under its own Edition number while the current Edition keeps serving; when it is Ready it is swapped in, and the old Chunks removed, in one transaction. A Failed one leaves the Document as it was.
_Avoid_: Draft edition, pending upload, shadow copy

**Tag**:
A label on Documents that an Agent can use to limit which Documents it retrieves from. A Tag belongs to one Project, and its name is unique in that Project, ignoring case. A Document can carry several Tags; Editors apply them one Document at a time or to many Documents at once (bulk tagging). Renaming a Tag keeps it on its Documents; deleting it takes it off them, and the Documents stay.
_Avoid_: Category, folder, label

**Chunk**:
A retrievable passage of a Document.
_Avoid_: Segment, passage, node

**Ingestion scan**:
The Guardrail check ingestion runs on every Chunk: the injection classifier (the local classifier, the same model as the input Guardrail) looks for instructions aimed at an AI (an indirect prompt injection hidden in a Document). A Chunk it flags keeps a Guardrail flag. Nothing is blocked at upload; whether a flagged Chunk is still retrievable is the Project's Flagged Chunk mode.
_Avoid_: Document scan, content filter, malware scan

**Injection classifier**:
The port that judges whether text looks like instructions aimed at an AI. Its adapters are the local classifier (the default for both the input Guardrail and the ingestion scan), the heuristic classifier (pattern rules, the baseline from ticket 03-07, for stacks built without the model), the rule-driven fake in tests, and the LLM classifier (an Agent's optional second check on Visitor messages).
_Avoid_: Detector, filter, moderation model

**Guardrail flag**:
What the injection classifier records on a Chunk it flags: a label (such as `prompt_injection`), a score from 0 to 1, and a reason an Editor can read. The Document viewer shows it on the Chunk, and the Document list counts a Document's flagged Chunks. An Editor can clear a flag they judge a false positive (clearing a flag); that is recorded as an Audit Event (`chunk.flag_cleared`, with the flag it had) and the Chunk is retrieved like any other from then on, until a new edition or retry scans it again.
_Avoid_: Warning, alert, violation

**Flagged Chunk mode**:
A Project setting for what retrieval does with Chunks that carry a Guardrail flag: mark (the default: they are retrieved like any other, and marked in the Document viewer) or exclude (they are never retrieval candidates and are never sent to a reranker; the Trace lists any that were found as excluded by the ingestion scan). Retrieval follows a change at once, with no reprocessing.
_Avoid_: Quarantine setting, scan mode

**Project Instructions**:
Markdown injected into every Agent in a Project, after the platform preamble and before the Agent's system prompt. Versioned the same way as Agents: each Project has one Draft of them, numbered Instructions Versions published from it with a note, and a Current Version.
_Avoid_: Project context, global prompt, shared context

## Agents and versioning

**Agent**:
A configurable assistant that answers from its Project's Knowledge Base.
_Avoid_: Bot, chatbot, assistant

**Draft**:
The single editable, unpublished configuration of an Agent or of Project Instructions.

**Draft revision**:
A counter on a Draft that moves on with every change to it. A change names the Draft revision it was made on, and if someone has changed the Draft since, the change is refused (a stale Draft) with their latest Draft. The Editor then loads their Draft or saves theirs over it on purpose, so nobody silently overwrites a colleague's edits. It is a concurrency token, not a Version.
_Avoid_: Draft version, ETag

**Unpublished changes**:
An Agent's Draft that differs from its Live Version's AgentConfig. The Studio badges the Agent with "Unpublished changes". An Agent that has never been published has none: it is "Not live".
_Avoid_: Dirty, pending changes

**Discard the Draft**:
To put the Live Version's AgentConfig back in an Agent's Draft, losing its Unpublished changes. Nothing is published. An Agent that is not live has nothing to discard to.

**Start a Draft from a Version**:
To replace an Agent's Draft with the AgentConfig of any of its Versions, to build on an earlier configuration without reverting. Nothing is published, and the Live Version is unchanged. The Version's settings are checked like a save, since a credential it names may have been deleted since.
_Avoid_: Restore, check out

**Diff**:
What changes from one side to another. For an Agent, each side is the Draft or a Version (the Live Version or any other), and the diff lists every AgentConfig setting that differs by its path (such as Retrieval › Top k), with the items added and removed for lists (Tags, starter questions), a line diff for markdown (the system prompt), and, between two Versions, the change of pinned Instructions Version with a line diff of their text. For Project Instructions, each side is the Draft or an Instructions Version, compared line by line. The publish form shows the Draft-to-Live diff.
_Avoid_: Changeset, delta

**AgentConfig**:
Everything in an Agent's Draft or Version that shapes how it answers: its Behaviour (system prompt and model settings), Retrieval (top-k and search settings), Experience and Guardrails settings. Operational Settings and the Theme are not part of it.
_Avoid_: Agent settings, agent options

**Public ID**:
An Agent's unguessable identifier, used by its Embed Snippet. Separate from its internal ID.
_Avoid_: Embed key, slug

**Top-k**:
How many of the best-scoring Chunks an Agent is given with each question.

**Model override**:
An Agent's own chat model: a chat-capable Provider Credential and one of its chat models, set in the Draft's Behaviour. Without one the Agent uses the Default Model. It is a Credential reference, as are an Agent's Reranker and Guardrail LLM classifier.
_Avoid_: Agent model, custom model

**Remembered turns**:
How many earlier question-and-answer pairs of a Conversation the model is given with each new question.
_Avoid_: History length, memory, context window

**Starter question**:
A suggested question the widget offers a Visitor before the first message. An Agent has up to six.
_Avoid_: Suggested prompt, quick reply

**UI text override**:
An Agent's replacement for one piece of the widget's built-in text, such as the "Send" button. Empty keeps the built-in text.
_Avoid_: Translation, label override

**Autosave**:
Saving the Draft by itself once the Editor pauses, with an indicator of whether every change is saved. A setting the API refuses is marked with the reason and not saved.
_Avoid_: Auto-publish

**Hybrid search**:
Retrieval that runs semantic (vector) search and keyword (full-text) search over a Project's Chunks and fuses their rankings with weighted reciprocal rank fusion, so exact terms such as product codes are found as well as similar meanings.
_Avoid_: Vector search (for the whole), combined search

**Hybrid weighting**:
The share of the fused score an Agent gives semantic search, from 0 (keyword search alone) to 1 (semantic search alone); keyword search has the rest.
_Avoid_: Alpha, semantic ratio

**Relevance**:
How well a Chunk matches a question, from 0 to 1: the better of its semantic score (cosine similarity) and its keyword score (the share of the question's terms it contains), or, when the Agent has a Reranker, the Reranker's score. The Minimum Score is compared with it; the fused score only orders Chunks, and only when there is no Reranker.

**Minimum Score**:
The Relevance a Chunk needs to be given to an Agent's model. When no Chunk reaches it, the Agent replies with its Fallback Text.
_Avoid_: Cut-off, similarity threshold

**Fallback Text**:
What an Agent replies, in its own words, when retrieval finds nothing relevant. The model isn't asked.
_Avoid_: Default answer, "I don't know" message

**Excluded Chunk**:
A Chunk retrieval found but didn't give the model, with its reason: below the Minimum Score, outside the Top-k, or outside the Agent's Tags (Tag scoping). It feeds the Trace.

**Tag scoping**:
Limiting an Agent to the Documents carrying at least one of the Tags its AgentConfig names, so several Agents can share one Project but see different material. Both searches of Hybrid search are limited before fusion; no Tags searches every Document. The Tags must be the Agent's Project's own. The best Top-k Chunks it left out are shown in the Trace as Excluded Chunks. Deleting a Tag takes it out of the Drafts scoped to it, and the Studio first warns which Agents those are, since an Agent left with no Tags searches every Document.
_Avoid_: Tag filter, document permissions, ACL

**Markdown editor**:
The Studio's editor for prompt fields (an Agent's system prompt, Project Instructions). It shows markdown formatted but stores markdown: text is kept exactly until it is edited, and its Markdown view edits the stored text itself.
_Avoid_: Rich text editor, WYSIWYG field, HTML

**Spotlighting**:
Putting retrieved Chunks and Visitor input into labelled, delimited data blocks, which the platform preamble tells the model to treat as data and never as instructions.
_Avoid_: Sandboxing, quoting

**Chunk label**:
The name a retrieved Chunk is given to the model with, by its rank: [C1], [C2] and so on. The model cites Chunks by their labels.

**Citation**:
A Chunk an Agent's answer cites. Where the model supports structured output it lists the Chunk labels it used beside the answer; otherwise the labels written in the answer are parsed. Each resolves back to its Chunk, and the Studio shows it as a chip linking to that Chunk in the Document viewer.
_Avoid_: Reference, footnote, source link

**Message retrieval**:
One Chunk retrieval found for an Agent Message, saved with its score, relevance, rank (when it was given to the model), whether it was cited and, for an Excluded Chunk, the reason. The Trace's list of Chunks.

**Version**:
An immutable, numbered snapshot of a Draft, created by publishing it with a note. Numbers start at 1 for each Agent and each Project's Instructions, and concurrent publishes get consecutive, unique numbers. An Agent's Version (an Agent Version) holds the AgentConfig and pins one Project Instructions Version: the Current Version unless the Editor chooses another, or none while the Project has never published its Instructions, in which case it runs with no Project Instructions.
_Avoid_: Revision, release

**Instructions Version**:
A Version of a Project's Instructions: its number, the markdown, the note, who published it and when. A Project's first one may come from the Instructions it had before Versions existed, and has no author.
_Avoid_: Instructions revision

**Live Version**:
The Agent Version currently served to Visitors, with the Instructions Version it pins. Only Agents have one. An Agent that has never been published has none and is shown as "Not live": it serves no Visitor.
_Avoid_: Active, production

**Current Version**:
The Project Instructions Version that newly published Agent Versions pin by default. Agents may still pin older ones. Publishing the Instructions makes the new Version Current; reverting them moves Current back to the Version that was Current when the present one was published, so reverting again keeps walking back rather than toggling. The Instructions page shows the Versions as a timeline, newest first, with the Current Version carrying the **Current** badge; any two Versions, or a Version and the saved Draft, can be compared there.
_Avoid_: Live (for Project Instructions), latest

**Live History**:
The ordered, append-only record of an Agent's Live Version changes. Each entry has the from-Version (none for the first publish), the to-Version, the action (publish, revert, bulk publish or bulk revert), who and when, and the bulk operation that made it, if any. The Studio shows it as the Live History timeline on the Agent page. Reverting follows it back: the Agent returns to the Version that was Live when its present Live Version was published, so publishing v1, v2 and v3 and then reverting twice gives v2 and then v1, never v3 again.
_Avoid_: Changelog, deployments

**Publish**:
To freeze a Draft into a new Version and make it the Live Version for an Agent, or the Current Version for Project Instructions.

**Revert**:
To move the Live Version (Agents) or the Current Version (Project Instructions) back one step in its history. For an Agent this restores both the configuration and the Instructions Version it was pinned to, and is refused when there's nothing to revert to (the Agent is not live, or its Live Version was its first) or the earlier Version's Provider Credential is gone. Reverting never creates, edits or deletes a Version, and it never changes the Draft.
_Avoid_: Rollback, undo

**Bulk publish**:
To publish a new Version of several Agents at once, each built from that Agent's **Live** configuration plus a chosen Project Instructions Version, never from its Draft (ADR-0003). Agents that have never been published are skipped (their first Version must be reviewed on their own page), and so are Agents already Live with that Instructions Version. Publishing Project Instructions opens the **rollout dialog**, which offers the new Version to the Project's Agents with every Agent that can take it pre-selected and Agents with unpublished Draft changes badged, since those edits aren't included.
_Avoid_: Mass deploy, publish all

**Bulk revert**:
To revert several Agents at once, each one step back in its own Live History. Editors start one from the Agent list (multi-select) or from the offer shown after reverting Project Instructions, which lists the Agents still Live with the reverted Instructions Version.
_Avoid_: Mass rollback

**Bulk operation**:
One bulk publish or bulk revert. Each Agent in it is processed in its own transaction, so a failure on one Agent never leaves another half-updated, and the result reports every Agent as succeeded, skipped (with the reason) or failed (with the reason). Its **bulk operation ID** is recorded on each Live History entry and Audit Event it makes.

**Behind**:
An Agent is behind when it is live but its Live Version doesn't pin the Current Instructions Version. The Project Instructions page shows "N Agents behind" and which Instructions Version each Agent pins, as version chips with an **Instructions behind** badge on each Agent that is behind, so partial rollouts are visible. An Agent that has never been published is not live, so it is never behind.
_Avoid_: Outdated, stale

**Playground**:
The place in the Studio where Members chat with a Draft. Its Conversations are excluded from metrics.

**Instructions picker**:
The Playground's choice of which Project Instructions the Agent's Draft answers with: the Instructions Draft (the default) or any Instructions Version, Current or not. It lets Editors test new Instructions with an Agent before publishing either. Each answer records its choice: the Instructions Version, or the Draft marker.
_Avoid_: Instructions selector, Instructions override

**Draft marker**:
What a Playground answer records in place of a Version when it ran with a Draft: `draft` for the Agent's configuration, and `draft` for the Project Instructions when the Instructions picker was left on the Instructions Draft.

**Playground Conversation**:
A Conversation held in the Playground. It is flagged as such, so metrics and the Token Budget leave it out; its cost still counts.

**Playground reset**:
Starting a new Playground Conversation, so the Draft is tested from a clean slate with no remembered turns. The earlier Playground Conversation is kept as it was.
_Avoid_: Clear, restart, new chat

**Provider error**:
A model provider's failure while answering, reported at the end of the answer's stream as one of four kinds, each with a readable message: invalid key, rate limited (including an exhausted quota), model unavailable, or another provider error. No answer is saved, so the question is not among the remembered turns.
_Avoid_: Model error, API error, crash

**Embed Snippet**:
The code an Organisation pastes into its site to show an Agent: one `<script>` tag that loads the platform's small loader with the Agent's Public ID, and optionally `data-launcher` and `data-target` to choose the Launcher. The loader injects an iframe for the Agent's Widget shell and sizes it as the widget asks, taking those layout messages only from the widget's own frame and origin. The Studio shows it, with a copy button, only once the Agent has a Live Version.
_Avoid_: Embed link, widget code

**Widget shell**:
The HTML page the Embed Snippet's iframe loads, served by the API for each request. Its `frame-ancestors` policy lets only the Agent's Allowed Origins show it, and it hands the widget a Bootstrap token. It inlines the Theme, with the Agent's Theme override, as CSS custom properties, and the Live Version's public Experience: name, avatar, greeting, starter questions, UI text overrides and whether citations show. An archived, unknown or not-live Agent gets the "no longer available" shell instead.
_Avoid_: Widget page, iframe HTML

**Bootstrap token**:
A short-lived (15 minutes), signed token the Widget shell gives the widget, bound to the Agent. The widget exchanges it for a Conversation token, which starts the Visitor's Conversation.

**Conversation token**:
The signed, opaque token that is a Visitor's only credential: bound to one Visitor Conversation and its Agent, and expiring 24 hours after the Conversation's last activity (each message and each Resume slides the window on). Only its hash is stored. Each answer it gets comes from the Agent's Live Version at that moment. The widget keeps it in the iframe's local storage, which browsers partition per top-level site; where that storage is blocked, the widget keeps it in memory only and a reload starts a new Conversation. Once its Conversation is ended it is refused.
_Avoid_: Session, visitor token

**Resume**:
Getting a Visitor's Conversation back when they reload or move to another page of the same site within 24 hours of its last activity: the widget sends its kept Conversation token and shows the earlier Messages with their sources, and the next question continues that Conversation. After 24 hours without activity the token is refused and the widget silently starts afresh.
_Avoid_: Restore, reconnect

**Ending a Conversation**:
A Visitor closing their Conversation from the widget (End chat), or leaving it to start another (New chat). The Conversation and its Messages are kept for the Studio; only its Conversation token stops working, and the Visitor's next question starts a new Conversation.
_Avoid_: Delete, close session

**No longer available shell**:
What a Visitor sees in place of the chat when the Agent is archived, in an archived Project, unknown or has never been published: "This assistant is no longer available." The Widget shell serves it on page load, and the widget switches to it if the Agent is retired mid-Conversation or before a Resume.
_Avoid_: Error page, 404

**Operational Settings**:
An Agent's settings that take effect immediately and are not part of any Draft or Version: Allowed Origins, the Unavailable text, the Theme override, rate limits and Token Budget. Allowed Origins, the Unavailable text, the rate limits and the Token Budget are edited through their own endpoint (the Theme override through its own, Owners only), apply on the next request without publishing, and every change is an Audit Event (`agent.operational_settings_changed`) holding the before and after values of the settings it changed.

**Unavailable text**:
What Visitors are told, in the Agent's own words, when it can't answer (no model to answer with, a provider failure, a message refused by a rate limit or because the day's Token Budget is spent). Part of the Operational Settings; left empty, it is the platform's default, "This assistant is temporarily unavailable. Please try again later."
_Avoid_: Error message, offline message

**Theme override**:
An Agent's own colours and avatar in its widget, replacing the Theme's for that Agent only: any of the Colour Tokens (each with its light and dark value) and an avatar image. The other tokens, the font, radius, mode and Launcher still follow the Theme. Like the Theme, only Owners change it; it is an Operational Setting, so it isn't versioned and applies at once. The widget's avatar is the Agent's own, else the Live Version's avatar URL, else the Theme's default avatar.
_Avoid_: Agent theme, sub-brand theme

**Rate limits**:
How many Visitor messages an Agent admits in any one minute, per Conversation (its Conversation token; 10 by default) and per IP address (30 by default), counted in sliding windows. Part of the Operational Settings. A message over a limit isn't answered or saved: the widget gets an `unavailable` event and shows the Unavailable text, and the refused message doesn't count, so waiting always works. The Playground has none.
_Avoid_: Throttling (that is sign-in protection), quota

**Admission control**:
The check every Visitor message passes, after its Conversation token is accepted and before anything is saved or a model is called: first the Agent's Token Budget, then its Rate limits. It admits the message or refuses it with a reason, and a refusal reaches the Visitor as the Unavailable text. The Playground never goes through it.

**Trusted proxies**:
The load balancers and CDN ranges (`TRUSTED_PROXIES`; in AWS the VPC, where the ALB is, and CloudFront's origin-facing ranges) whose `X-Forwarded-For` entries are believed when finding a client's IP address for per-IP limits: the per-IP Rate limit and sign-in protection. The client is the right-most address that isn't a trusted proxy; anything a client wrote itself is ignored. With none, the connection's own address is the client's. Nothing else believes forwarding headers (uvicorn's own handling is off).

**Token Budget**:
The maximum tokens an Agent's Visitor replies may use per UTC date (1,000,000 by default) before it stops answering Visitors. Part of the Operational Settings. Each reply adds the input and output tokens it actually used to the Agent's counter for that date; once the day's usage reaches the budget, Admission control refuses Visitor messages with the Unavailable text (`unavailable` event, reason `budget_exhausted`), the Agent gets its Budget alert and the Owners are emailed. A new UTC date starts a new counter, so the budget resets at midnight UTC; raising it applies at once. The Playground doesn't count and is never refused. The Studio's budget meter shows today's usage against it.
_Avoid_: Quota, spend limit (cost is tracked separately)

**Budget alert**:
The flag an Agent carries once its Token Budget is spent for the day, raised by the first reply that reaches it or the first message it refuses. The Studio shows it as a "Budget exhausted" badge on the Agent list and the Agent page, and raising it emails every Owner once per Agent per day. A Beat task clears the flags at midnight UTC.
_Avoid_: Budget warning, alarm

**Allowed Origins**:
The sites permitted to display an Agent through its Embed Snippet, each a scheme, host and optional port (`https://www.example.com`, `http://localhost:8080`). A host may start with a subdomain wildcard over a named site (`https://*.example.com` is every subdomain of example.com, but not example.com itself, and never a bare `*.com`), and localhost (`localhost`, `127.0.0.1`, `[::1]`) may take any port as `http://localhost:*`, for development. The Widget shell's `frame-ancestors` policy lists them; with none, no site may show the Agent. Part of the Operational Settings: changes apply to the next page load, without publishing, and are audited.

**Guardrail**:
A check on Visitor input, Agent output or a Document that can flag or block content as prompt injection or leakage.

**Canary token**:
A random secret placed in the platform preamble of every prompt, with the instruction never to reveal it. If an answer starts to repeat it (whatever its case or spacing, even split across stream chunks), the stream is cut and the reply replaced with the Agent's fallback text; a disguised copy (separated by punctuation, reversed or base64) found once the answer is complete is logged and flagged, as it has already been sent.
_Avoid_: Canary, honeytoken, tripwire

**Input Guardrail**:
The Guardrail that checks every Visitor message (and every Playground question) with the injection classifier before the Agent runtime sees it. By default it is the local classifier, with no setup; an Agent can add an LLM classifier (block mode only, for now). What it does with a message it flags is the Agent's Input mode.

**Input mode**:
What the input Guardrail does with a message it flags, chosen per Agent in its Guardrails settings and versioned with the AgentConfig (a Visitor gets the Live Version's mode, the Playground the Draft's). **Block** (the default): the message never reaches retrieval or the model; the Visitor gets the Agent's refusal text. **Warn**: the message is answered, but the prompt carries a Caution block and the answer Message is flagged. **Log**: the message is answered exactly as an unflagged one would be, and the verdict is only recorded. In every mode the Guardrail outcome is saved on the Message and shown in its Trace; an unflagged message leaves none.
_Avoid_: Guardrail level, enforcement mode

**Caution block**:
The extra system text the input Guardrail's warn mode adds to the prompt, after the Agent's system prompt, for the flagged turn only: it tells the model the message was flagged as a possible prompt injection, not to follow instructions in it or change role, not to reveal its instructions or the Canary token, and to answer only a genuine question the excerpts answer.
_Avoid_: Warning prompt, safety prefix

**Local classifier**:
The default injection classifier of the input Guardrail and the ingestion scan: a DeBERTa-v3 prompt-injection model (ONNX) run on the CPU, bundled in the API image and loaded once per process (the API and the worker each share one copy between the two). A message longer than the model reads at once is scored in overlapping windows and the highest score counts; a score at or above the threshold (0.5 by default) flags it.

**LLM classifier**:
An Agent's optional second injection classifier for the input Guardrail: a chat model of one of the Organisation's Provider Credentials (a Credential reference), chosen in the Agent's Guardrails settings and versioned with it. Each message the local classifier passes is also judged by it, through the model gateway, with a fixed classifier prompt and a structured answer (label, score, reason); the message is shown to it as delimited, untrusted data. Its fail mode decides what happens when it can't judge.
_Avoid_: AI classifier, judge model

**Fail mode**:
What the input Guardrail does when the LLM classifier can't judge a message (its provider errors, it answers off the schema, or it doesn't answer within `LLM_CLASSIFIER_TIMEOUT_S`). Closed (the default) treats the message as flagged, so in block mode the Visitor gets the refusal text; open answers it without that check. Either way the Trace records an `unchecked` Guardrail outcome saying why.
_Avoid_: Fail-safe, fallback mode

**Refusal text**:
What the Agent replies, in place of an answer, to a message the input Guardrail blocked. Set per Agent in its Guardrails settings and versioned with it; the default is "Sorry, I can't help with that request."
_Avoid_: Block message, rejection text

**Guardrail outcome**:
What one Guardrail layer decided about an answer: its layer (input or canary), verdict (such as injection or leak, or unchecked when the LLM classifier couldn't judge), action (blocked, flagged, logged, replaced or allowed: the input Guardrail blocks, flags or logs by its Input mode; the Canary token replaces a leak, or flags an encoded one found after sending; allowed when an Agent failing open let an unchecked message through), reason, and score when the layer gives one. Saved on the Message and shown in its Trace.

**Attack evaluation suite**:
The versioned set of attack and benign cases (`backend/evals/attack_suite.json`) run through the real Guardrail pipeline to show the defences work: each case declares its expected outcome per layer (ingestion scan, input Guardrail, Canary token, and whether the answer stayed harmless). It runs on every PR against the Naive model, where any unexpected outcome fails, and nightly against a real model, where it fails below the configured pass rate.
_Avoid_: Red-team suite, jailbreak tests

**Naive model**:
The mocked chat model the Attack evaluation suite runs against in CI: it obeys whatever instructions it finds (in the Visitor's message, the history or a retrieved Chunk, disguised or not), so the suite tests the Guardrails rather than a model's own refusals.
_Avoid_: Dumb model, evil model

**Pass rate**:
In an Attack evaluation suite report, the share of cases defended: an attack got none of its markers into a reply and sent no encoded Canary token; a benign question was answered without being blocked, flagged or cut off.

## Conversations

**Visitor**:
An anonymous person chatting with an embedded Agent.
_Avoid_: User, customer, end user

**Conversation**:
One Visitor's thread of Messages with an Agent.
_Avoid_: Session, chat, thread

**Message**:
One turn in a Conversation, from either the Visitor or the Agent. An Agent Message records what produced it: the Agent Version that answered, or the Draft marker for a Playground answer (Message attribution). A Playground answer also records the Project Instructions it ran with: an Instructions Version or the Draft marker.

**Conversations viewer**:
The Project's Conversations tab in the Studio. It lists the Project's Conversations, Visitors' and the Playground's (Playground Conversations flagged), newest first, filtered by Agent, by Agent Version (those with an answer from it), by the UTC days they started on, by Visitor or Playground, by Message Feedback (a reply with a thumbs up, with a thumbs down, any feedback, or none), by Conversation Rating (one score from 1 to 5, rated, or not rated), and by Guardrail outcome (a reply whose Guardrail blocked, flagged, logged, replaced or allowed it, any Guardrail outcome, or none); each row shows its thumbs-up and thumbs-down counts, its current Conversation Rating and how many of its replies have a Guardrail outcome. Opening one shows its Messages, each Agent Message with the Agent Version or Draft that answered, its Message Feedback (thumb, comment, the Agent Version it counts for, and when) and its Trace in the Trace drawer, and for a Visitor Conversation its Conversation Rating (score, the Agent Version it counts for, when, any dismissal of the Rating prompt) with its Rating change log. An Agent's page links to the viewer filtered to that Agent. Any Member can use it.
_Avoid_: Chat log, transcript list

**Message Feedback**:
A Visitor's thumbs-up or thumbs-down, with an optional comment (up to 1000 characters), on one Agent Message in their own Conversation; at most one per Message. The Visitor gives it from the widget, authenticated by the Conversation token, and can change it (giving it again replaces it) or remove it (pressing the chosen thumb again). It belongs to the Agent Version of the Message it is on, stored when it is written, so a later publish or revert never moves it.
_Avoid_: Reaction, vote

**Trace**:
The record of why an Agent Message said what it did: the model, token use, Cost and latency, its Message retrievals (cited, given but not cited, or excluded and why), Guardrail outcomes, the Agent Version (or Draft) that answered, and the Project Instructions it ran with (for an Agent Version's answer, the ones the Version pins). Shown in the Trace drawer, in the Playground and in the Conversations viewer.
_Avoid_: Debug log, explanation

**Conversation Rating**:
A Visitor's 1–5 score for a whole Visitor Conversation, given from the widget's Rating prompt (authenticated by the Conversation token) once the Agent has replied; one current score per Conversation, which the Visitor can change. It belongs to the Agent Version of the last Agent Message before the rating, or before its latest change, stored when written, so a later publish or revert never moves it. The first rating and every change are kept in the Rating change log.
_Avoid_: CSAT, review

**Rating prompt**:
The widget's card asking the Visitor to rate the Conversation from 1 to 5. It appears after the Live Version's Nth Agent reply (the Experience setting "rating prompt reply count"; 0 asks only at the end), until the Visitor rates or dismisses it ("Not now"); the dismissal is saved, so it isn't shown again in that Conversation. On "End chat" a Visitor who hasn't rated is asked once more ("Before you go"), and can rate or end without rating. The Experience's UI text can reword its question.
_Avoid_: Survey, popup

**Rating change log**:
The append-only record of a Conversation's Conversation Ratings: the first rating and each change, with the score before it, the Agent Version it was attributed to and when. Giving the same score again isn't a change.
_Avoid_: Rating history

**Version KPIs**:
An Agent Version's key numbers over a range of UTC days (the last 30 by default), shown as KPI cards in the Project's Analytics tab: volume (Visitor Conversations it replied in, and its replies), mean and p95 tokens per reply (input plus output, over replies that asked a model), cost per Conversation (from each reply's frozen Cost), thumbs-up rate with its Wilson interval and sample size, mean Conversation Rating with its count, fallback rate (replies that were the fallback text), Block rate and p95 latency (to the first token and to the whole reply). Only Visitor Conversations count: Playground Conversations never do. Days before today come from the Usage rollups; today is counted live from the raw tables (the live partial day).
_Avoid_: Stats, dashboard numbers

**Usage rollup**:
The `usage_daily` row for one Agent Version and one UTC day: Conversations, Messages, token sums, cost, thumbs up and down, rating sum and count, fallback count, Guardrail blocks (for the Block rate), and fixed-bucket histograms (10% wide buckets, which add up across days) of tokens per reply, time to first token and latency, from which percentiles are read. A Beat task runs hourly: it recomputes the current day and finalises each earlier day not yet final for the Organisation (normally the previous day; days a stopped Beat missed are caught up). A final day isn't recomputed, so feedback or a rating changed after its day was finalised doesn't move it. Each day's rollup is recomputed in full, so running the task again gives the same rollups. A reply, its tokens, cost, latency, Guardrail block and Message Feedback belong to the day the reply was made; a Conversation to the day the Version first replied in it; a Conversation Rating to the day of the Conversation's first reply.
_Avoid_: Aggregate, summary table

**Block rate**:
The share of an Agent Version's Visitor replies that were its refusal text because the input Guardrail blocked the question, shown with the count as the "Guardrail block rate" KPI card in the Version KPIs. Warned or logged messages were answered, so they aren't blocks; neither is a reply the Canary token replaced. Only Visitor Conversations count. A rate under 1% is shown with one decimal, so a few blocks don't read as none.
_Avoid_: Attack rate, refusal rate

**Block rate alert**:
The flag an Agent carries while its Block rate spikes, as in an attack. After each hourly rollup, the Agent's Visitor messages in the hour up to that run are compared with its baseline, the week before that hour: at least 5 blocked messages, at least 20% of the hour's messages and at least three times the baseline's rate is a spike. Raising it emails every Owner once (with a link to the Conversations viewer filtered to the Agent's blocked messages); the Studio shows a "Block rate spike" badge on the Agent list and the Agent page, the same badge mechanism as the Budget alert. The first hourly run that no longer finds a spike clears it, and a new spike alerts again.
_Avoid_: Attack alarm, spike warning

**Wilson interval**:
The 95% Wilson score interval of a rate (the thumbs-up rate), worked out from its counts when the Version KPIs are read; shown with the sample size so a few lucky votes don't look like a winner.
_Avoid_: Error bars, margin

**Purge**:
Clearing a Message's text, the reasons in its Guardrail outcomes and the comment of any Message Feedback on it, and stamping it purged-at, while every number and attribution (tokens, Cost, latency, Agent Version, thumbs, Conversation Rating, Message retrievals, each Guardrail outcome's verdict) stays, so the Version KPIs read the same before and after. A daily Beat task (00:35 UTC) purges the Messages older than each Organisation's Retention Window, but a Visitor reply only once the Usage rollup of its day is final (rollups come before purges). Deleting a Conversation purges its Messages at once, through the same path. The Conversations viewer shows a purged Message as "Text purged" with when and why.
_Avoid_: Deletion, cleanup, expiry

**Deleting a Conversation**:
An Owner's removal of one Conversation's text on request (a Visitor's deletion request), from the Conversations viewer: its Messages are Purged at once, its Conversation token stops working, and it is recorded as an Audit Event (`conversation.deleted`). The Conversation stays in the list, marked deleted on request, so its numbers stay in the metrics.
_Avoid_: Erasing a Conversation, removing a chat

**Tombstone**:
What a Trace keeps of a Message retrieval whose Document was deleted: the Document's name when the answer was given (its Chunk and Document IDs are cleared). The Trace drawer shows "Chunk from deleted Document <name>", so history stays readable.
_Avoid_: Broken reference, orphan

**Low confidence**:
The visual treatment of a KPI with a small sample (fewer than 30 votes, ratings or Conversations): its card is muted and dashed and labelled "Low confidence" with the reason. A deliberate product choice: keep it when redesigning.
_Avoid_: Insufficient data, greyed out

**Version comparison**:
Any two Versions of an Agent (the first and the second) side by side over a chosen range of UTC days, in the Analytics tab: every Version KPI for each, the difference (second minus first; rates in percentage points), and the Version a metric favours. Rows whose values differ are highlighted, and a metric whose sample is small on either side is marked "(small sample)". The configuration diff from the first Version to the second (the Agent diff, pinned Project Instructions included) is shown alongside, and the comparison can be exported as CSV. By default the Live Version (else the newest) is compared with the newest other one. Only Visitor Conversations count.
_Avoid_: A/B test, benchmark

**Better side**:
The Version a compared metric favours. A higher thumbs-up rate or mean rating is better; fewer tokens per reply, a lower cost per Conversation, a lower fallback rate and lower latency are better. Volumes, totals and the Wilson interval's bounds favour neither, nor do level values or a metric only one side has. It says which value is preferable, not that the difference is significant: read it with the sample sizes and intervals.
_Avoid_: Winner

**Time series**:
One metric of an Agent (every Version together: Conversations, replies, cost, mean tokens per reply, thumbs-up rate, mean Conversation Rating, fallback rate or p95 latency) per day, ISO week (Monday to Sunday) or month over a range of UTC days (the last 30 by default; the first and last periods are clipped to the range), shown as a chart in the Project's Analytics tab with each point's sample size. Like the Version KPIs it reads the Usage rollups plus the live partial day, and only Visitor Conversations count. A period with no sample has no value (a gap), not zero. Live History markers on it show where the Live Version changed.
_Avoid_: Trend graph, history chart

**Live History marker**:
A mark on the Time series at a Live History entry made during its range: the day, the action (publish, revert, bulk publish or bulk revert) and the Versions from and to, so an Editor can see the effect of each release.
_Avoid_: Release line, annotation

**Confounder note**:
The warning under the Time series when the Project's Knowledge Base changed during its range: how many Documents were added, replaced or processed again, and how many were deleted. Documents aren't versioned (ADR-0003), so answers can change without the Live Version changing, and a difference across a marker may be the Documents' doing.
_Avoid_: Disclaimer, KB warning

**Organisation cost**:
What the Organisation spent over a range of UTC days (the last 30 by default), at each reply's frozen Cost, broken down by Project or by Agent (each with its Project), with Playground usage in its own column beside Visitor usage, and a total. Only Projects and Agents that replied in the period have a line; archived ones still do. Visitor usage on days before today comes from the Usage rollups and today's is counted live; Playground usage, which never goes into the rollups, comes from the raw Messages. Shown on the Owner-only Cost page.
_Avoid_: Billing, invoice, spend report
