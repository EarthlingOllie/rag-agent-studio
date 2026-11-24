# Spec 20: Calls

**Status:** draft, awaiting review · **Builds on:** [Spec 02](./02-provider-credentials-theme-spec.md), [Spec 04](./04-agents-retrieval-playground-spec.md), [Spec 06](./06-embed-widget-operational-settings-spec.md), [Spec 07](./07-feedback-logging-comparison-spec.md), [Spec 13](./13-agentic-retrieval-spec.md) · **Decisions:** [ADR-0019](../adr/0019-calls-through-a-custom-llm.md), [ADR-0009](../adr/0009-operational-settings-outside-versions.md)

## Problem Statement

A Visitor can only type to an Agent. Some Visitors would rather talk: they are on a phone, their hands are busy, typing is slow or hard for them, or the question is easier to say than to write. Organisations that want a spoken assistant today have to build a second one in a voice product, with its own prompt and its own copy of the knowledge, outside the Guardrails, Traces, Versions and analytics they rely on here. The two drift apart, and nobody can say which Version a spoken answer came from.

## Solution

An Agent can take **Calls**. When calling is on, the Launcher opens on a choice of **Message** or **Call**, and the chat has a Call button, so a Visitor can move between typing and talking inside one Conversation.

A Call is the same Agent with ElevenLabs' real-time conversation layer on top (ADR-0019). ElevenLabs listens, takes turns and speaks. Every reply is still written by our runtime: the same prompt, retrieval, Guardrails, Fallback Text, Trace and Cost as a typed reply, attributed to the same Live Version. What was said is saved as **Spoken Messages** beside the typed ones, so the Agent remembers both, and the Conversation log shows the Call as text while it happens.

- **Set up by the Organisation.** ElevenLabs is a Provider Credential with a new **voice** Capability. Each Agent has **Call settings** (on or off, credential, voice, spoken greeting) in its Operational Settings.
- **Bounded.** A **Maximum Call length** and a daily **Call minutes budget** cap the per-minute bill; spoken replies also count toward the Token Budget and rate limits.
- **Costed.** Each Call records its minutes and a **Voice Cost**, apart from the model Cost of its replies.
- **Never recorded.** Audio goes from the browser straight to ElevenLabs and is never stored by the platform.

## User Stories

### Setting up

1. As an Owner, I want to add an ElevenLabs Provider Credential with the voice Capability, checked live when saved, so that our Agents can take Calls on our own account.
2. As an Owner, I want the ElevenLabs key encrypted, shown only as its Key hint and rotatable like any other credential, so that it is as safe as our model keys.
3. As an Owner, I want a credential that an Agent calls with to be undeletable while it is in use, so that Calls can't be broken by tidying up.
4. As an Editor, I want to turn calling on for an Agent in its Operational Settings, off by default, so that Calls start only when we choose.
5. As an Editor, I want to pick the voice from the voices in our ElevenLabs account and hear a sample, so that the Agent sounds right.
6. As an Editor, I want to write a spoken greeting, so that a Call opens in the Agent's own words.
7. As an Editor, I want turning calling on refused, with a clear reason, while the Organisation has no voice-capable credential, so that I can't offer Calls that can't work.
8. As an Editor, I want Call settings to apply at once without publishing, so that I can switch calling off during an incident.
9. As an Owner, I want every Call settings change recorded as an Audit Event with before and after values, so that I can see who turned calling on.
10. As an Editor, I want never to open the ElevenLabs dashboard: saving the Call settings sets everything up there, so that the two can't drift.
11. As an Editor, I want to reword the "Message" and "Call" choices with UI text overrides, so that they match the Agent's voice.

### Starting and holding a Call

12. As a Visitor, I want the Launcher to offer Message or Call when the Agent takes Calls, so that I can choose how to ask.
13. As a Visitor, I want the Launcher to open straight into the chat when the Agent doesn't take Calls, so that nothing changes where calling is off.
14. As a Visitor, I want to be asked for my microphone only when I choose Call, so that the page never listens uninvited.
15. As a Visitor who refuses the microphone, or whose site blocks it, I want a short explanation and to land in messaging, so that I can still ask.
16. As a Visitor, I want to hear the Agent's greeting when a Call opens a new Conversation, so that I know it is listening.
17. As a Visitor, I want to speak naturally and interrupt the Agent, so that the Call feels like a conversation.
18. As a Visitor, I want what I say and what the Agent answers to appear in the Conversation log as text, so that I can read what I missed.
19. As a Visitor, I want sources shown in the log and never read aloud, so that I can check an answer without listening to references.
20. As a Visitor, I want spoken answers free of formatting symbols and citation markers, so that they sound natural.
21. As a Visitor, I want to hear the Searching status while the Agent looks something up, so that silence doesn't seem like a dropped Call.
22. As a Visitor, I want Mute and End call controls, so that I am in charge of the microphone.
23. As a Visitor, I want to start a Call from the chat and return to the chat when it ends, with the Agent remembering both, so that switching costs me nothing.
24. As a Visitor who reloads the page mid-Call, I want my Conversation back with everything that was said and a one-tap "Continue call", so that I can carry on.
25. As a Visitor, I want to give thumbs on spoken replies and be asked to rate only after the Call ends, so that feedback doesn't interrupt talking.
26. As a Visitor using a screen reader, I want replies not announced during a Call, and every Call control labelled, so that nothing talks over the Agent.
27. As a Visitor using a keyboard, I want to choose, mute and end a Call without a mouse, with focus kept inside the widget, so that Calls are as accessible as the chat.

### Safety, limits and failure

28. As an Editor, I want every spoken turn to pass the same input Guardrail, Canary check and Fallback Text as a typed one, so that talking is no way round our defences.
29. As a Visitor whose words are blocked by a Guardrail, I want to hear the Agent's refusal and stay in the Call, so that one refusal doesn't hang up on me.
30. As a Visitor, I want to hear the Unavailable text and be returned to messaging when the Agent can't answer, so that a Call never ends in silence.
31. As an Editor, I want to set a Maximum Call length (10 minutes by default), so that one Call can't run all day.
32. As an Editor, I want to set a daily Call minutes budget (60 by default) and see today's minutes against it, so that the voice bill is capped.
33. As an Owner, I want an alert badge and one email when the Call minutes budget is spent, so that I find out as I do for the Token Budget.
34. As an Owner, I want one Call at a time per Conversation, a cap on concurrent Calls per IP address and silent Calls ended automatically, so that an open line can't be used to run up cost.
35. As an Owner, I want spoken replies to count toward the Token Budget and rate limits, so that those limits still cap real use.
36. As an Editor, I want a "Calls failing" alert when Calls can't start, and messaging to keep working meanwhile, so that a voice outage is visible and contained.
37. As an Owner, I want audio never stored and Spoken Messages purged with the Retention Window, so that Calls add no new kind of personal data to keep.

### Reviewing and measuring

38. As an Editor, I want Spoken Messages marked in the Conversations viewer, with interrupted replies marked too, so that I can tell what was said from what was typed.
39. As an Editor, I want each spoken reply to open the same Trace as a typed one, so that I can debug a Call.
40. As an Editor, I want to filter Conversations to those with a Call, so that I can review how Calls go.
41. As an Editor, I want spoken replies counted in Version KPIs, Live Verdicts and Evaluation like typed ones, so that a Version is measured on everything it answered.
42. As an Owner, I want Calls and Call minutes per day in Analytics, so that I can see how much calling is used.
43. As an Owner, I want each Call's minutes and Voice Cost shown on its Conversation and rolled into Agent, Project and Organisation cost, so that I know what the voice layer adds.
44. As an Owner, I want to override the per-minute voice price for our credential, so that Voice Cost matches our ElevenLabs plan.

### Playground, demo and development

45. As an Editor, I want to call the Draft from the Playground, with each spoken reply's Trace, so that I can hear the Agent before Visitors do.
46. As an Owner, I want Playground Calls kept out of metrics and the Call minutes budget but counted in Organisation cost, so that testing behaves as it does for typed messages.
47. As a developer, I want the whole Call flow to run locally and in CI against a fake voice layer, so that Calls are tested without ElevenLabs.
48. As a developer, I want the seeded Demo Organisation to take Calls only when the seed is given an ElevenLabs key and a public address, so that the demo still runs with no key.

## Implementation Decisions

- **Capability registry.** A new provider, ElevenLabs (API key auth), with one new Capability, `voice`. Its live Credential check proves the key works and can use the agents API. A credential's voices are listed through a new Studio route for the voice picker (name, ID, sample URL). The Price table gains a per-minute price for voice, with Price overrides.
- **Voice layer port.** One port in front of ElevenLabs with these operations: set up or update the remote agent for an Agent's Call settings, remove it, list voices, and start a Call (returning what the browser needs to join). The production adapter talks to ElevenLabs; the fake is scripted and selected by settings, as other fakes are. Nothing else imports the ElevenLabs API.
- **Remote agent.** One ElevenLabs agent per Agent with calling on, created when calling is first saved on and updated on every Call settings change. It holds the voice, the language (English), the spoken greeting, our turn endpoint's address as its custom LLM, a per-Agent secret as that LLM's API key (stored on our side with envelope encryption), and has the extra-body option on. It has no prompt, tools or knowledge of its own. It is removed when calling is turned off, the Agent is archived or deleted, or its credential changes. The endpoint address comes from the platform's public base URL setting.
- **Call settings** join the Operational Settings model and endpoint: enabled, credential, voice, spoken greeting, Maximum Call length (minutes) and Call minutes budget (minutes per UTC date). They are validated on save (a voice-capable credential of this Organisation, a voice it offers), make a Credential reference, and are audited with the other Operational Settings.
- **Widget shell.** Boot data gains whether the Agent takes Calls, and the `message_choice` and `call_choice` UI text overrides (added to AgentConfig's Experience UI text, so they are in Versions). The shell's CSP allows connections to ElevenLabs only when calling is on. The iframe is given microphone permission by the loader; the loader stays inside its size budget.
- **Starting a Call** (widget API, Conversation token): `POST …/conversation/calls`.
  - Admission control first: the existing checks, then Call checks (no other Call open on the Conversation, concurrent Calls for the IP under the platform cap, Call minutes budget not spent). A refusal is the Unavailable text with a reason.
  - It records a **Call** (Conversation, started at, the Version that was Live) and asks the voice layer for a WebRTC token.
  - It returns that token and a **Call token**: signed, bound to the Call and Conversation, valid for the Maximum Call length.
  - A voice layer failure returns the Unavailable text and raises the Calls failing alert on the Agent.
- **The turn endpoint** (called by ElevenLabs): an OpenAI-compatible chat completions route under the Agent's public ID, streaming Server-Sent Events.
  - It checks the per-Agent secret and the Call token from the request's extra body, then that the Call is still open and inside its limits. Anything else is refused with no model call.
  - It takes only the last user message as the Visitor's words and ignores the rest of the history ElevenLabs sends. Earlier turns come from the Conversation, under the History turns setting.
  - It runs the same serving path as a typed widget message: admission (rate limits, Token Budget), Live Version resolution, `run_turn`, persistence, usage and budget counters. Messages are saved with `spoken` set.
  - The runtime's events are mapped to speech: `token` text is stripped of Markdown and citation labels and streamed; a `search` event streams the Searching status once per reply as a buffer phrase; text that could still be retracted is held until it can't be; `replace` and `refusal` speak the replacement or refusal text; `unavailable` and errors speak the Unavailable text and mark the Call ended.
- **The Conversation log during a Call.** The widget takes the Visitor's transcribed words and the speaking state from the ElevenLabs client, and the Agent's full reply (text, citations, Message ID) from our API, so the log, sources and feedback work exactly as for a typed reply.
- **Ending a Call.** `DELETE …/conversation/calls/current` from the widget, or the platform's own end: the Maximum Call length, the silence cut-off (no turn for 60 seconds, checked by a Beat task that also closes Calls whose browser vanished), the Unavailable outcome, or ending the Conversation. Ending records the end time, the minutes (rounded up) added to the day's Call minutes counter, and the Voice Cost frozen at the price then in effect.
- **Interruption.** The widget tells our API when the Visitor talked over a reply; the Agent Message is marked interrupted and keeps its full text.
- **Persistence.** A Call record per Call; Messages gain `spoken`, `interrupted` and a nullable Call reference; Operational Settings gain the Call settings; the Agent gains its remote agent ID, encrypted secret and the Calls failing flag. The Purge treats Spoken Messages as it treats typed ones and keeps Call minutes and Voice Cost as aggregates.
- **Widget app.** A choice screen in the Launcher's panel when calling is on; a Call view over the Conversation log with speaking and listening states, Mute and End call; the text box hidden during a Call; a Call button in the chat header; "Continue call" on a Resume whose last Call was cut off by a reload. The ElevenLabs client is loaded only when a Visitor picks Call. The rating prompt and Reply announcement wait until the Call ends.
- **Studio UI** (Tidepool components throughout).
  - Credentials: ElevenLabs in the provider list, with the voice Capability and its per-minute Price override.
  - Embed & limits: a Call settings card (toggle, credential, voice picker with sample, spoken greeting), the two Call limits with a Call minutes meter beside the Token Budget meter, and the Calls failing and Budget alerts.
  - Playground configuration: the two new UI text overrides in Experience.
  - Conversations viewer: a spoken mark and an interrupted mark on Messages, a Call row showing minutes and Voice Cost, and a "Has a Call" filter.
  - Analytics: Calls and Call minutes per day; Voice Cost in the cost breakdowns.
- **Analytics.** Daily rollups add Calls, Call minutes and Voice Cost per Agent Version. Spoken replies need no change to existing KPIs, Live sampling or Evaluation, since they are Messages.
- **Playground Calls.** The Playground gains a Call button when the Agent's calling is on. It uses the same voice layer and turn endpoint with a Playground Call token, answers with the Draft, and is excluded from metrics and the Call minutes budget; its Voice Cost counts.
- **Seed.** Calling stays off unless `SEED_ELEVENLABS_API_KEY` and a public base URL are set, in which case the Product FAQ takes Calls.

## Testing Decisions

- **Good tests** drive a Call the way the widget and the voice layer would and assert what a Visitor hears and sees and what is saved, not how ElevenLabs is called.
- **API seam.**
  - ElevenLabs credentials: save, check failure reasons, voice listing, deletion refused while referenced.
  - Call settings: validation, immediate effect, Audit Events, the remote agent set up, updated and removed through the fake.
  - Starting a Call: each admission refusal, the Call token, the Calls failing alert on a voice layer failure.
  - The turn endpoint: a wrong secret, a tampered, expired or cross-Conversation Call token, and an ended Call are all refused without a model call; ElevenLabs' history is ignored and typed turns are remembered; spoken text is stripped; the Searching phrase, refusal, replacement and Unavailable outcomes; Messages saved as spoken with a Trace and the Live Version; tokens counted to the Token Budget.
  - Ending: by the Visitor, by Maximum Call length, by silence and by ending the Conversation (controllable clock); minutes, the Call minutes budget, its alert and single email, and Voice Cost with a Price override.
  - Interruption marking; Resume returning Spoken Messages and the cut-off Call; the Purge.
  - Tenancy: every new Studio route refuses another Organisation.
- **Voice layer adapter.** The ElevenLabs adapter is tested against recorded HTTP exchanges, and in the live suite against a real account.
- **Frontend, network seam (widget).** The choice screen only when calling is on; microphone refused falls back to messaging; the log filling during a Call; Mute and End call; the hidden text box; Continue call after a reload; rating and announcements deferred; keyboard and screen-reader behaviour. The ElevenLabs client is replaced by a fake at the module boundary.
- **Frontend, network seam (Studio).** The Call settings card and its refusals, the voice picker, the minutes meter and alerts, the Conversations viewer marks and filter, the Analytics additions.
- **End-to-end (Playwright).** With the fake voice layer: an Editor turns calling on, a Visitor on the demo host page chooses Call, a scripted Call produces a spoken exchange in the log with a source, End call returns to the chat, and the Conversation shows in the Studio with its spoken marks and minutes. Axe checks on the choice screen and the Call view in light and dark mode.
- **Embed loader.** The iframe's microphone permission; the size budget still holds.

## Out of Scope

- Phone numbers, outbound calls and transfers to a person.
- Storing or replaying audio.
- Languages other than English, and detecting the Visitor's language.
- A spoken-style prompt: the model is asked exactly what it is asked for a typed Message.
- Typing during a Call.
- A second voice provider, or a browser-speech demo voice.
- Choosing the voice per Version.

## Further Notes

- ElevenLabs must reach the turn endpoint from the public internet. A local stack holds real Calls only through a tunnel, with the public base URL set to it.
- Our clock, not ElevenLabs', times Calls, so Voice Cost can differ slightly from the invoice.
- Long, list-heavy answers will sound stilted until a spoken style is designed. Editors can only address that in the system prompt, for typed and spoken replies together.
- An interrupted reply stays whole in the Agent's memory, so the Agent may refer to words the Visitor never heard.
