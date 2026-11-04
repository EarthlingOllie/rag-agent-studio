# RAG Agent Studio

A studio where Organisations build Agents grounded in a Knowledge Base, inside isolated Projects, and embed them on their own sites.

## Tenancy

**Organisation**:
The tenant. Owns Members, Projects and Provider Credentials.
_Avoid_: Tenant, account, company

**Member**:
A person who signs in to the Studio and belongs to one or more Organisations.
_Avoid_: User, admin

**Owner**:
A Member role that can manage Provider Credentials, Members and Organisation settings, as well as everything an Editor can.

**Editor**:
A Member role that can manage Projects, Documents and Agents.

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
An immutable, numbered snapshot of a Draft, created by publishing it.
_Avoid_: Revision, release

**Live Version**:
The Version currently served to Visitors. Reverting moves it back to an earlier Version.
_Avoid_: Active, current, production

**Publish**:
To freeze a Draft into a new Version and make it the Live Version.

**Playground**:
The place in the Studio where Members chat with a Draft. Its Conversations are excluded from metrics.

**Embed Snippet**:
The code an Organisation pastes into its site to show an Agent.
_Avoid_: Embed link, widget code

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

**Conversation Rating**:
A Visitor's 1–5 score for a whole Conversation.
_Avoid_: CSAT, review
