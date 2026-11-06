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

**Launcher**:
How the widget appears on the host page: a floating bubble in a bottom corner that opens the chat, or an inline container that shows it in place.
_Avoid_: Chat button, trigger

**Theme Image**:
One of the two images a Theme can have: the **logo**, shown in the widget's header, and the **default Agent avatar**, shown beside the Agent's name for every Agent without an avatar of its own. Each is a PNG, JPEG or WebP image of at most 1 MB, uploaded straight to object storage, and applies as soon as it is uploaded; Owners replace or remove it.
_Avoid_: Branding asset, icon, picture

**Contrast Warning**:
A notice that a pair of Colour Tokens falls below WCAG AA contrast (4.5:1 for text, 3:1 for the accent against the surface) in a mode the Theme shows. It warns and never blocks saving.
_Avoid_: Contrast error, accessibility check

**Retention Window**:
How long an Organisation keeps Message text before it is purged. Aggregate metrics are kept.

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
The Organisation a Member is working in. A Member of several Organisations picks it with the Organisation switcher; the Studio remembers the choice and opens it next time, and otherwise opens their first Organisation. It never grants access: every Organisation page and API route names its Organisation, and a Member reaches only Organisations they have a Membership in.
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
The Organisation `make seed` builds for showing the product: Northwind Traders, a fictional company, with a demo Owner and Editor whose sign-in details are published, the Northwind Handbook Project and its synthetic Documents. It is found through the demo Owner's account. `make seed-reset` erases it, its Audit Events included, and builds it again; no other Organisation can be erased.
_Avoid_: Sample org, test tenant, sandbox

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
The Guardrail check ingestion runs on every Chunk: the injection classifier looks for instructions aimed at an AI (an indirect prompt injection hidden in a Document). A Chunk it flags keeps a Guardrail flag; nothing is blocked, and a flagged Chunk is still retrievable.
_Avoid_: Document scan, content filter, malware scan

**Injection classifier**:
The port that judges whether text looks like instructions aimed at an AI. Its adapters are the heuristic classifier (pattern rules, the baseline from ticket 03-07), the rule-driven fake in tests, and later the local ONNX model and the LLM classifier (spec 08).
_Avoid_: Detector, filter, moderation model

**Guardrail flag**:
What the injection classifier records on a Chunk it flags: a label (such as `prompt_injection`), a score from 0 to 1, and a reason an Editor can read. The Document viewer shows it on the Chunk, and the Document list counts a Document's flagged Chunks.
_Avoid_: Warning, alert, violation

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
The Project Instructions Version that newly published Agent Versions pin by default. Agents may still pin older ones. Publishing the Instructions makes the new Version Current; reverting them moves Current back to the Version that was Current when the present one was published, so reverting again keeps walking back rather than toggling.
_Avoid_: Live (for Project Instructions), latest

**Live History**:
The ordered, append-only record of an Agent's Live Version changes. Each entry has the from-Version (none for the first publish), the to-Version, the action (publish, revert, bulk publish or bulk revert), who and when, and the bulk operation that made it, if any. The Studio shows it as the Live History timeline on the Agent page. Reverting follows it back: the Agent returns to the Version that was Live when its present Live Version was published, so publishing v1, v2 and v3 and then reverting twice gives v2 and then v1, never v3 again.
_Avoid_: Changelog, deployments

**Publish**:
To freeze a Draft into a new Version and make it the Live Version for an Agent, or the Current Version for Project Instructions.

**Revert**:
To move the Live Version (Agents) or the Current Version (Project Instructions) back one step in its history. For an Agent this restores both the configuration and the Instructions Version it was pinned to, and is refused when there's nothing to revert to (the Agent is not live, or its Live Version was its first) or the earlier Version's Provider Credential is gone. Reverting never creates, edits or deletes a Version, and it never changes the Draft.
_Avoid_: Rollback, undo

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
The code an Organisation pastes into its site to show an Agent.
_Avoid_: Embed link, widget code

**Operational Settings**:
An Agent's settings that take effect immediately and are not part of any Version: Allowed Origins, rate limits and Token Budget.

**Token Budget**:
The maximum tokens an Agent may consume per day before it stops answering Visitors.

**Allowed Origins**:
The sites permitted to display an Agent through its Embed Snippet.

**Guardrail**:
A check on Visitor input, Agent output or a Document that can flag or block content as prompt injection or leakage.

**Canary token**:
A random secret placed in the platform preamble of every prompt, with the instruction never to reveal it. If an answer starts to repeat it (whatever its case or spacing, even split across stream chunks), the stream is cut and the reply replaced with the Agent's fallback text; a disguised copy (separated by punctuation, reversed or base64) found once the answer is complete is logged and flagged, as it has already been sent.
_Avoid_: Canary, honeytoken, tripwire

**Guardrail outcome**:
What one Guardrail layer decided about an answer: its layer, verdict, action (such as replaced or flagged) and reason. Saved on the Message and shown in its Trace.

## Conversations

**Visitor**:
An anonymous person chatting with an embedded Agent.
_Avoid_: User, customer, end user

**Conversation**:
One Visitor's thread of Messages with an Agent.
_Avoid_: Session, chat, thread

**Message**:
One turn in a Conversation, from either the Visitor or the Agent. An Agent Message records what produced it: the Agent Version that answered, or the Draft marker for a Playground answer (Message attribution). A Playground answer also records the Project Instructions it ran with: an Instructions Version or the Draft marker.

**Message Feedback**:
A Visitor's thumbs-up or thumbs-down, with an optional comment, on one Agent Message.
_Avoid_: Reaction, vote

**Trace**:
The record of why an Agent Message said what it did: the model, token use, Cost and latency, its Message retrievals (cited, given but not cited, or excluded and why), Guardrail outcomes, Version, and the Project Instructions it ran with. Shown in the Playground's Trace drawer.
_Avoid_: Debug log, explanation

**Conversation Rating**:
A Visitor's 1–5 score for a whole Conversation.
_Avoid_: CSAT, review
