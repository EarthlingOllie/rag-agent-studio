"""The model gateway: the one place a credential and a model name become a model client."""

import pydantic_ai

# The first-run banner is for people trying Pydantic AI in a terminal, not for a service.
pydantic_ai.BANNER_ENABLED = False
