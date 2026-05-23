from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


class PIIMasker:
    """Detect and mask Personally Identifiable Information in text.

    Strategy (defence-in-depth):
    - Mask PII in input logs BEFORE sending to the LLM.
    - Mask PII in output BEFORE returning to the caller.

    The class attempts to use Microsoft Presidio (production-grade NER).
    If Presidio or its spaCy model is unavailable, it falls back to a
    deterministic regex-based masker suitable for demos.
    """

    def __init__(self) -> None:
        self._use_presidio = False
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
            from presidio_anonymizer.entities import OperatorConfig

            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()
            self._operator_config = {
                "DEFAULT": OperatorConfig("replace", {"new_value": "<PII>"}),
                "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "<PHONE>"}),
                "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "<EMAIL>"}),
                "CREDIT_CARD": OperatorConfig("replace", {"new_value": "<CREDIT_CARD>"}),
                "IP_ADDRESS": OperatorConfig("replace", {"new_value": "<IP_ADDRESS>"}),
                "PERSON": OperatorConfig("replace", {"new_value": "<PERSON>"}),
                "US_SSN": OperatorConfig("replace", {"new_value": "<SSN>"}),
            }
            self._entities = [
                "PHONE_NUMBER", "EMAIL_ADDRESS", "CREDIT_CARD",
                "IP_ADDRESS", "PERSON", "US_SSN",
            ]
            self._use_presidio = True
            logger.info("PIIMasker initialised with Presidio engine.")
        except Exception as exc:
            logger.warning(
                "Presidio unavailable (%s) — falling back to regex masker.", exc
            )

    # ── Regex patterns (fallback) ────────────────────────────────

    _REGEX_PATTERNS: list[tuple[str, str]] = [
        # Email
        (r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "<EMAIL>"),
        # US SSN
        (r"\b\d{3}-\d{2}-\d{4}\b", "<SSN>"),
        # Credit card (basic: 13-19 digits with optional dashes/spaces)
        (r"\b(?:\d[ -]*?){13,19}\b", "<CREDIT_CARD>"),
        # Phone (US/international, 10+ digits with optional separators)
        (r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", "<PHONE>"),
        # IPv4
        (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "<IP_ADDRESS>"),
    ]

    def _regex_mask(self, text: str) -> str:
        """Apply regex-based PII masking (fallback)."""
        for pattern, replacement in self._REGEX_PATTERNS:
            text = re.sub(pattern, replacement, text)
        return text

    # ── Public API ───────────────────────────────────────────────

    def mask(self, text: str) -> str:
        """Mask PII in *text* and return the sanitised version."""
        if not text:
            return text

        if self._use_presidio:
            try:
                results = self._analyzer.analyze(
                    text=text,
                    entities=self._entities,
                    language="en",
                )
                if results:
                    anonymised = self._anonymizer.anonymize(
                        text=text,
                        analyzer_results=results,
                        operators=self._operator_config,
                    )
                    logger.debug("Presidio masked %d PII entities.", len(results))
                    return anonymised.text
                return text
            except Exception as exc:
                logger.warning("Presidio masking failed (%s) — using regex.", exc)

        return self._regex_mask(text)
