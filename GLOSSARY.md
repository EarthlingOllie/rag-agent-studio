# RAG Agent Studio

A studio where Organisations build Agents grounded in a Knowledge Base, inside isolated Projects, and embed them on their own sites.

## Tenancy

**Organisation**:
The tenant. Owns Members, Projects and Provider Credentials.
_Avoid_: Tenant, account, company

**Theme**:
An Organisation's visual styling for embedded Agents: Colour Tokens, corner radius, a font from the Font Allowlist, a Theme Mode and a Launcher. Owners change it and every Member can view it; a saved change applies at once, with no publishing. An Agent may override its colours and avatar.
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

**Archive**:
To retire an Agent or Project. It stops serving Visitors but keeps its Versions, Conversations and metrics. Permanent deletion is a separate action.
_Avoid_: Disable, soft delete

**Restore**:
To bring an archived Project back to the Projects list so it serves again. Only Owners can restore.
_Avoid_: Unarchive, undelete

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

**Model gateway**:
The single factory every model call goes through: it turns a Provider Credential and a model name into a chat model, an embedder or a reranker, refusing a model the credential doesn't offer for that Capability. Tests and `docker compose` swap in fake adapters here and nowhere else.
_Avoid_: Model client factory, provider router, LLM proxy

**Reranker**:
A model that reorders retrieved passages by relevance to a query, built by the Model gateway from a credential with the rerank Capability.
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
The model that turns Chunks and queries into vectors for a Project. It is the platform's local model unless the Project chooses a provider.

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

**Content hash**:
The SHA-256 of a Document's uploaded bytes, recorded when the upload is confirmed.
_Avoid_: Checksum, fingerprint, etag

**Tag**:
A label on Documents that an Agent can use to limit which Documents it retrieves from. A Tag belongs to one Project, and its name is unique in that Project, ignoring case. A Document can carry several Tags; Editors apply them one Document at a time or to many Documents at once (bulk tagging). Renaming a Tag keeps it on its Documents; deleting it takes it off them, and the Documents stay.
_Avoid_: Category, folder, label

**Chunk**:
A retrievable passage of a Document.
_Avoid_: Segment, passage, node

**Project Instructions**:
Text injected into every Agent in a Project. Versioned the same way as Agents.
_Avoid_: Project context, global prompt, shared context

## Agents and versioning

**Agent**:
A configurable assistant that answers from its Project's Knowledge Base.
_Avoid_: Bot, chatbot, assistant

**Draft**:
The single editable, unpublished configuration of an Agent or of Project Instructions.

**AgentConfig**:
Everything in an Agent's Draft or Version that shapes how it answers: its Behaviour (system prompt and model settings), Retrieval (top-k and search settings), Experience and Guardrails settings. Operational Settings and the Theme are not part of it.
_Avoid_: Agent settings, agent options

**Public ID**:
An Agent's unguessable identifier, used by its Embed Snippet. Separate from its internal ID.
_Avoid_: Embed key, slug

**Top-k**:
How many of the best-scoring Chunks an Agent is given with each question.

**Hybrid search**:
Retrieval that runs semantic (vector) search and keyword (full-text) search over a Project's Chunks and fuses their rankings with weighted reciprocal rank fusion, so exact terms such as product codes are found as well as similar meanings.
_Avoid_: Vector search (for the whole), combined search

**Hybrid weighting**:
The share of the fused score an Agent gives semantic search, from 0 (keyword search alone) to 1 (semantic search alone); keyword search has the rest.
_Avoid_: Alpha, semantic ratio

**Relevance**:
How well a Chunk matches a question, from 0 to 1: the better of its semantic score (cosine similarity) and its keyword score (the share of the question's terms it contains). The Minimum Score is compared with it; the fused score only orders Chunks.

**Minimum Score**:
The Relevance a Chunk needs to be given to an Agent's model. When no Chunk reaches it, the Agent replies with its Fallback Text.
_Avoid_: Cut-off, similarity threshold

**Fallback Text**:
What an Agent replies, in its own words, when retrieval finds nothing relevant. The model isn't asked.
_Avoid_: Default answer, "I don't know" message

**Excluded Chunk**:
A Chunk retrieval found but didn't give the model, with its reason: below the Minimum Score, or outside the Top-k. It feeds the Trace.

**Spotlighting**:
Putting retrieved Chunks and Visitor input into labelled, delimited data blocks, which the platform preamble tells the model to treat as data and never as instructions.
_Avoid_: Sandboxing, quoting

**Version**:
An immutable, numbered snapshot of a Draft, created by publishing it. An Agent's Version pins exactly one Project Instructions Version.
_Avoid_: Revision, release

**Live Version**:
The Agent Version currently served to Visitors. Only Agents have one.
_Avoid_: Active, production

**Current Version**:
The Project Instructions Version that newly published Agent Versions pin by default. Agents may still pin older ones.
_Avoid_: Live (for Project Instructions), latest

**Live History**:
The ordered record of an Agent's Live Version changes. Reverting steps back one entry.
_Avoid_: Changelog, deployments

**Publish**:
To freeze a Draft into a new Version and make it the Live Version for an Agent, or the Current Version for Project Instructions.

**Playground**:
The place in the Studio where Members chat with a Draft. Its Conversations are excluded from metrics.

**Playground Conversation**:
A Conversation held in the Playground. It is flagged as such, so metrics and the Token Budget leave it out; its cost still counts.

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

## Conversations

**Visitor**:
An anonymous person chatting with an embedded Agent.
_Avoid_: User, customer, end user

**Conversation**:
One Visitor's thread of Messages with an Agent.
_Avoid_: Session, chat, thread

**Message**:
One turn in a Conversation, from either the Visitor or the Agent.

**Message Feedback**:
A Visitor's thumbs-up or thumbs-down, with an optional comment, on one Agent Message.
_Avoid_: Reaction, vote

**Trace**:
The record of why an Agent Message said what it did: the retrieved Chunks, Guardrail outcomes, model, Version and token use.
_Avoid_: Debug log, explanation

**Conversation Rating**:
A Visitor's 1–5 score for a whole Conversation.
_Avoid_: CSAT, review
