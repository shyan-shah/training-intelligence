"""Training Intelligence analytics engine.

Everything in this package is deterministic. No LLM touches a number: each
value the page renders traces back to a formula in one of these modules, and
each formula reads its thresholds from athlete_settings rather than hardcoding.
"""
__all__ = ["load", "recovery", "body", "verdict", "streaks", "insights", "validate", "dedupe"]
