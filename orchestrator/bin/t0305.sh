#!/bin/bash
# Runs backend pytest for ticket 03-05 against its own Postgres/Redis containers.
cd /tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad/wt-03-05/backend
export TEST_OBJECT_STORE_URL=http://localhost:44990 TEST_DATABASE_URL=postgresql+asyncpg://studio:studio@localhost:44432/studio_test TEST_REDIS_URL=redis://localhost:44379/15
exec uv run pytest -p no:cacheprovider "$@"
