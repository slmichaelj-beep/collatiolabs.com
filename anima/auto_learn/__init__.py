"""anima.auto_learn — Auto Learn v1: SUGGESTION-ONLY.

It observes patterns and proposes — it cannot persist. No direct memory write, no behavior write,
no project-rule write, no sensitive auto-persist, no identity/relationship inference persistence.
The ONLY thing it can do with a suggestion is convert it into a Teaching Mode DRAFT, which then
rides the full approval flow. It never learns from quarantined text, test fixtures, hostile text,
or contaminated assistant output.
"""
from . import api, queue, schema  # noqa: F401
