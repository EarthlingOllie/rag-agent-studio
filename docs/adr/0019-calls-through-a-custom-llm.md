# A Call is ElevenLabs speaking for our runtime

A Call puts ElevenLabs' real-time conversation layer on top of the Agent, and ElevenLabs does only the listening, turn-taking and speaking. On every Visitor turn it calls our API as its "custom LLM" with the transcribed words, the runtime answers exactly as it does for a typed Message (same prompt, retrieval, Guardrails, Fallback Text, Trace and Cost), and ElevenLabs speaks the text we stream back, with formatting and citation markers stripped. The widget's audio goes straight to ElevenLabs on a short-lived signed URL our API mints with the Organisation's Provider Credential; audio never passes through or is stored by the platform.

We chose this over copying each Agent's configuration into an ElevenLabs-hosted agent, which would answer without our Guardrails, Traces or Version attribution and drift from the Live Version, and over joining speech-to-text and text-to-speech ourselves, which would make turn-taking and latency ours to build.

Because the voice layer doesn't change what the model is asked, calling (on or off, the voice, the spoken greeting) is an Operational Setting, not part of a Version (ADR-0009).

The price: ElevenLabs must reach our API from the public internet, so a local stack can't hold a real Call without a tunnel, and the endpoint ElevenLabs calls is a public route that spends model tokens and must prove which Conversation each request belongs to. Don't "simplify" by letting ElevenLabs hold the prompt or call the model provider itself.
