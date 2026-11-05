# RAG Agent Studio

A studio where Organisations build Agents grounded in a Knowledge Base, inside isolated Projects, and embed them on their own sites.

## Tenancy

**Organisation**:
The tenant. Owns Members, Projects and Provider Credentials.
_Avoid_: Tenant, account, company

**Theme**:
An Organisation's visual styling for embedded Agents. An Agent may override its colours and avatar.
_Avoid_: Branding, skin, styles

**Retention Window**:
How long an Organisation keeps Message text before it is purged. Aggregate metrics are kept.

**Member**:
A person who signs in to the Studio and belongs to one or more Organisations.
_Avoid_: User, admin

**Membership**:
A Member's place in one Organisation, with a role: Owner or Editor. Signing up creates an Organisation and an Owner Membership for the new Member.
_Avoid_: Seat, account

**Lockout**:
A temporary block on signing in, after too many failed attempts for one account or from one IP address. Before it, each further attempt must wait a little longer. A Lockout of a Member's account is recorded as an Audit Event in each of their Organisations.
_Avoid_: Ban, suspension, block

**Owner**:
A Member role that can manage Provider Credentials, Members and Organisation settings, as well as everything an Editor can.

**Editor**:
A Member role that can manage Projects, Documents and Agents.

**Audit Event**:
An append-only record of who changed what in an Organisation, and when.
_Avoid_: Activity, history, log

**Archive**:
To retire an Agent or Project. It stops serving Visitors but keeps its Versions, Conversations and metrics. Permanent deletion is a separate action.
_Avoid_: Disable, soft delete

## Models

**Provider Credential**:
A secret an Organisation stores so it can call a model provider.
_Avoid_: API key, token, connection

**Default Model**:
The chat model an Organisation's Agents use unless an Agent overrides it.

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

**Tag**:
A label on Documents that an Agent can use to limit which Documents it retrieves from.
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
