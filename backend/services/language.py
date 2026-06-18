"""LanguageRegistry — single source of truth for language-dependent pipeline decisions.

No node ever writes a language code literally; everything goes through this registry.
"""
from __future__ import annotations
from dataclasses import dataclass
from backend.config import AVAILABLE_LANGUAGES, DEFAULT_ANSWER_LANG


@dataclass(frozen=True)
class LangDef:
    """Immutable per-language configuration: analyzer flags, sparse field name, and prompt key."""

    code: str
    decompound: bool
    sparse_field: str
    prompt_key: str


class LanguageRegistry:
    """Single source of truth for all pipeline language decisions.

    No node ever writes a language code literally; everything goes through here.
    """

    def __init__(self):
        """Build the internal lang map from AVAILABLE_LANGUAGES and validate prompt files."""
        self._langs: dict[str, LangDef] = {}
        for code, decompound, sparse_field, prompt_key in AVAILABLE_LANGUAGES:
            self._langs[code] = LangDef(
                code=code,
                decompound=decompound,
                sparse_field=sparse_field,
                prompt_key=prompt_key,
            )
        self._validate()

    # ── public API ──────────────────────────────────────────────────────────

    def all(self) -> list[LangDef]:
        """Return all registered language definitions in insertion order."""
        return list(self._langs.values())

    def get(self, code: str) -> LangDef:
        """Return the LangDef for ``code``, or the German default if unknown."""
        if code not in self._langs:
            return self._langs[DEFAULT_ANSWER_LANG]
        return self._langs[code]

    def sparse_fields(self) -> list[str]:
        """Names of all per-language sparse vector fields (e.g. ["sparse_de", "sparse_en"])."""
        return [d.sparse_field for d in self._langs.values()]

    def resolve_answer_lang(self, detected: str | None, explicit: str | None = None) -> str:
        """Priority: explicit instruction in query > detected > German default."""
        if explicit and explicit in self._langs:
            return explicit
        if detected and detected in self._langs:
            return detected
        return DEFAULT_ANSWER_LANG

    def active_languages(self, user_ticks: list[str]) -> list[LangDef]:
        """German always active; add user-ticked languages that exist in registry."""
        codes = {"de"} | {c for c in user_ticks if c in self._langs}
        return [self._langs[c] for c in codes]

    # ── internal ────────────────────────────────────────────────────────────

    def _validate(self):
        """Warn loudly if any active language is missing its expected prompt files."""
        from pathlib import Path
        import warnings
        missing = []
        for ld in self._langs.values():
            for purpose in ("answer", "abstain"):
                p = Path("prompts") / f"{purpose}_{ld.prompt_key}.txt"
                if not p.exists():
                    missing.append(str(p))
        if missing:
            warnings.warn(
                f"LanguageRegistry: missing prompt files: {missing}. "
                "Language support will be incomplete.",
                stacklevel=2,
            )


# Module-level singleton
registry = LanguageRegistry()
