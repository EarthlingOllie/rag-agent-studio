"""The Organisation's Theme: colour tokens, radius, font, mode and launcher.

One Theme per Organisation. Every Member reads it; Owners change it, and each change is an
Audit Event. A change applies as soon as it is saved: nothing is published. Resolving the
Theme into CSS custom properties, and the contrast check, live in the shared UI package
(``frontend/packages/ui``), which the Studio preview and the widget both render with.
"""
