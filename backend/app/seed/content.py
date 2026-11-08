"""What the demo Organisation holds. All of it is synthetic: Northwind Traders is fictional."""

from collections.abc import Mapping
from dataclasses import dataclass, field

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


HR_AGENT = "HR helper"
# The Agents the demo pages embed: the shop pages (bubble and inline) and the low-budget page.
SHOP_AGENT = "Product FAQ"
BUDGET_AGENT = "Low-budget helper"
BUDGET_TOKENS = 2000
BUDGET_UNAVAILABLE = (
    "Northwind's low-budget helper has used today's budget. Please come back tomorrow."
)
PUBLISH_NOTE = "First release, for the demo pages"

AGENTS = (
    # Its Draft is the one its Version 3 was published from (ticket 10-02).
    SeedAgent(
        HR_AGENT,
        (HR,),
        "You help Northwind Traders staff with questions about the staff handbook. Quote the "
        "handbook, cite the section, and say who in HR to ask when the handbook doesn't cover "
        "the question.",
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

# Northwind's brand: olive green with a saffron accent, set in a serif. The accent is dark enough
# (5.5:1 on the widget's answer bubbles) for citations to meet WCAG 2.2 AA on the demo pages.
THEME = ThemeSettings(
    colours=ThemeColours(
        primary=ColourToken(light="#3f5f2a", dark="#a3c585"),
        on_primary=ColourToken(light="#ffffff", dark="#1b2612"),
        surface=ColourToken(light="#fbf8f1", dark="#1c1f17"),
        on_surface=ColourToken(light="#1f2419", dark="#f2efe6"),
        accent=ColourToken(light="#9a4508", dark="#f6ad55"),
        muted=ColourToken(light="#5b6152", dark="#a8ad9e"),
    ),
    radius=6,
    font=Font.LORA,
    mode=ThemeMode.LIGHT,
    launcher_type=LauncherType.BUBBLE,
    launcher_position=LauncherPosition.BOTTOM_RIGHT,
)


# The seeded history (ticket 10-02): four weeks in the life of the demo Organisation, played
# through the API under a clock set in the past. Days count back from today (day 28 is four weeks
# ago): on day 28 the Organisation is set up, Instructions v1 published, and the Agents published;
# on day 17 the Editor publishes HR helper v2 (terse, without citations); on day 10 the Owner
# reverts it; on day 6 Instructions v2 is published and rolled out to the Low-budget helper,
# leaving the Product FAQ behind; on day 3 the Editor publishes HR helper v3.
HISTORY_DAYS = 28

INSTRUCTIONS_V1 = (
    "Northwind Traders is a small food importer. Write in British English, be friendly and "
    "brief, and only answer from the Knowledge Base."
)
INSTRUCTIONS_V1_NOTE = "House style"
INSTRUCTIONS_V2 = (
    INSTRUCTIONS_V1 + "\n\nNever promise refunds, discounts or exceptions to policy; point to the "
    "policy and the team that can help."
)
INSTRUCTIONS_V2_NOTE = "No promises beyond policy"


@dataclass(frozen=True)
class Release:
    """A Version of the HR helper: what its Draft held when it was published."""

    system_prompt: str
    top_k: int
    citations: bool
    note: str


HR_V1 = Release(
    "You help Northwind Traders staff with questions about the staff handbook.",
    5,
    True,
    "First release",
)
HR_V2 = Release(
    "Answer staff questions in one short sentence. Don't quote the handbook.",
    1,
    False,
    "Shorter answers, without citations",
)
HR_V2_REVERTED_BECAUSE = "Staff found v2's answers too curt"
HR_V3 = Release(AGENTS[0].system_prompt, 5, True, "Cite the handbook and point to HR contacts")
BULK_NOTE = "Instructions v2: no promises beyond policy"


@dataclass(frozen=True)
class Reception:
    """How Visitors took a Version's replies: the chance a reply gets a thumb, the chance a thumb
    is up, the chance a Conversation is rated, and the weights of the scores 1 to 5."""

    vote: float
    thumbs_up: float
    rate: float
    scores: tuple[int, int, int, int, int]


# By Agent and Version number. HR helper v2 is noticeably worse, but not cartoonishly so.
RECEPTION = {
    (HR_AGENT, 1): Reception(0.7, 0.74, 0.45, (3, 7, 15, 40, 35)),
    (HR_AGENT, 2): Reception(0.75, 0.42, 0.5, (15, 25, 30, 20, 10)),
    (HR_AGENT, 3): Reception(0.7, 0.84, 0.45, (2, 3, 10, 35, 50)),
    (SHOP_AGENT, 1): Reception(0.6, 0.8, 0.4, (3, 5, 15, 42, 35)),
}

# What Visitors ask each Agent; answered from the Knowledge Base.
QUESTIONS = {
    HR_AGENT: (
        "How many days of annual leave do I get?",
        "Can I carry leave over to next year?",
        "What should I do if I'm off sick?",
        "How do I claim travel expenses?",
        "Can I work from home?",
        "What are the core working hours?",
        "Can I get a laptop stand for home?",
    ),
    SHOP_AGENT: (
        "Can I return a jar of honey?",
        "How long do refunds take?",
        "My olive oil arrived damaged. What now?",
        "What's new in the spring range?",
        "Do you deliver outside the UK?",
        "Which items can't be returned?",
    ),
}
# How many questions a Visitor asks in one Conversation, and how often.
TURN_WEIGHTS = {1: 5, 2: 3, 3: 2}


@dataclass(frozen=True)
class History:
    """How much history to make: Visitor Conversations per day for each Agent, and the fixed
    random seed that decides their questions, feedback and ratings."""

    conversations_per_day: Mapping[str, int] = field(
        default_factory=lambda: {HR_AGENT: 5, SHOP_AGENT: 3}
    )
    random_seed: int = 1002


HISTORY = History()
