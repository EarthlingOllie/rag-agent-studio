"""What the demo Organisation holds. All of it is synthetic: Northwind Traders is fictional."""

from dataclasses import dataclass

from app.agents.models import TOKEN_BUDGET_DEFAULT
from app.credentials.registry import Provider
from app.embed.service import DEFAULT_UNAVAILABLE_TEXT
from app.theme.fonts import Font
from app.theme.schema import (
    ColourToken,
    LauncherPosition,
    LauncherType,
    ThemeColours,
    ThemeMode,
    ThemeSettings,
)


@dataclass(frozen=True)
class Account:
    name: str
    email: str
    password: str


ORGANISATION_NAME = "Northwind Traders"
# Demo accounts with published passwords: the seed prints them and the README shows them.
OWNER = Account("Nadia Novak", "owner@northwind.example", "northwind-owner-demo")
EDITOR = Account("Eli Edwards", "editor@northwind.example", "northwind-editor-demo")

DEMO_CREDENTIAL = "Northwind demo model"
# The demo provider checks nothing; any key of the allowed length will do.
DEMO_KEY = "demo-no-key-needed"
DEMO_MODEL = "demo-chat"
# The chat model a real credential from the environment answers with, unless one is named.
REAL_DEFAULT_MODELS = {Provider.ANTHROPIC: "claude-haiku-4-5", Provider.OPENAI: "gpt-4.1-mini"}

PROJECT_NAME = "Northwind Handbook"
PROJECT_DESCRIPTION = "Staff handbook and product information for Northwind Traders (synthetic)."
HR, PRODUCTS = "HR", "Products"


@dataclass(frozen=True)
class SeedDocument:
    filename: str
    tags: tuple[str, ...]


# In ``seed/documents``. The returns policy's footnote is a planted indirect prompt injection.
DOCUMENTS = (
    SeedDocument("northwind-staff-handbook.md", (HR,)),
    SeedDocument("northwind-returns-policy.md", (PRODUCTS,)),
    SeedDocument("northwind-product-faq.docx", (PRODUCTS,)),
    SeedDocument("northwind-spring-range.pptx", (PRODUCTS,)),
)
INJECTED_DOCUMENT = "northwind-returns-policy.md"


@dataclass(frozen=True)
class Embedding:
    """An Agent the demo pages embed: published once, its Allowed Origins the shop origin."""

    daily_token_budget: int = TOKEN_BUDGET_DEFAULT
    unavailable_text: str = DEFAULT_UNAVAILABLE_TEXT


@dataclass(frozen=True)
class SeedAgent:
    name: str
    tags: tuple[str, ...]
    system_prompt: str
    greeting: str
    # Set for the Agents the demo pages embed (ticket 10-03).
    embedding: Embedding | None = None


# The Agents the demo pages embed: the shop pages (bubble and inline) and the low-budget page.
SHOP_AGENT = "Product FAQ"
BUDGET_AGENT = "Low-budget helper"
BUDGET_TOKENS = 2000
BUDGET_UNAVAILABLE = (
    "Northwind's low-budget helper has used today's budget. Please come back tomorrow."
)
PUBLISH_NOTE = "First release, for the demo pages"

AGENTS = (
    SeedAgent(
        "HR helper",
        (HR,),
        "You help Northwind Traders staff with questions about the staff handbook.",
        "Hi! Ask me about leave, expenses or working from home.",
    ),
    SeedAgent(
        SHOP_AGENT,
        (PRODUCTS,),
        "You answer customers' questions about Northwind Traders products, orders and returns.",
        "Hello! Ask me about our products, delivery or returns.",
        Embedding(),
    ),
    # The low-budget page's Agent: a tiny daily Token Budget that the page's button spends, so
    # the unavailable state and the Studio's alert can be shown in one click.
    SeedAgent(
        BUDGET_AGENT,
        (PRODUCTS,),
        "You answer customers' questions about Northwind Traders products, orders and returns.",
        "Hello! I have a very small daily budget. Ask me something quickly!",
        Embedding(daily_token_budget=BUDGET_TOKENS, unavailable_text=BUDGET_UNAVAILABLE),
    ),
)

# Northwind's brand: olive green with a saffron accent, set in a serif.
THEME = ThemeSettings(
    colours=ThemeColours(
        primary=ColourToken(light="#3f5f2a", dark="#a3c585"),
        on_primary=ColourToken(light="#ffffff", dark="#1b2612"),
        surface=ColourToken(light="#fbf8f1", dark="#1c1f17"),
        on_surface=ColourToken(light="#1f2419", dark="#f2efe6"),
        accent=ColourToken(light="#b45309", dark="#f6ad55"),
        muted=ColourToken(light="#5b6152", dark="#a8ad9e"),
    ),
    radius=6,
    font=Font.LORA,
    mode=ThemeMode.LIGHT,
    launcher_type=LauncherType.BUBBLE,
    launcher_position=LauncherPosition.BOTTOM_RIGHT,
)
