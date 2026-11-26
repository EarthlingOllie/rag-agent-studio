# ElevenLabs recordings

HTTP exchanges with the ElevenLabs Agents API, replayed by `tests/unit/test_elevenlabs_voice_layer.py`
through `tests/fakes/http_exchanges.py`'s `Replay`: each request the adapter sends must match the
recorded method, URL, query and JSON body, in order. Keys travel in headers and are never recorded.

They follow the shapes in ElevenLabs' API reference (`/v1/convai/agents`, `/v1/convai/secrets`,
`/v2/voices`, `/v1/convai/conversation/token`). To refresh them from a real account, run the live
test with a key and a directory to record into, then compare and copy the files you need:

```bash
cd backend && SEED_ELEVENLABS_API_KEY=... ELEVENLABS_RECORD=/tmp/elevenlabs \
  uv run pytest -m live --no-cov tests/live/test_elevenlabs_live.py
```
