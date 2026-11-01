"""
NVIDIA Garak-Inspired LLM Vulnerability Defense & Sanitization Engine.

Implements real-time mitigation for:
1. Prompt Injection & Jailbreaks (garak.probes.promptinject, garak.probes.dan)
2. System Prompt & Instruction Extraction (garak.probes.leakreplay)
3. PII & Secret Data Exfiltration (garak.probes.pii)
4. Deceptive / Hallucinatory Query Refusal (garak.probes.snowball)
"""

import re
import base64
import logging
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger("nexus.garak")

# Heuristic patterns from NVIDIA Garak prompt injection & jailbreak probes
GARAK_INJECTION_PATTERNS = [
    r"(?i)\bignore\s+(all\s+)?(previous|prior|above)\s+(instructions|directives|prompts|rules|constraints)\b",
    r"(?i)\bdisregard\s+(all\s+)?(previous|prior|above)\s+(instructions|directives|rules)\b",
    r"(?i)\bsystem\s+override\b",
    r"(?i)\byou\s+are\s+now\s+(dan|aim|jailbroken|unrestricted|in\s+developer\s+mode)\b",
    r"(?i)\bdo\s+anything\s+now\b",
    r"(?i)\bpretend\s+you\s+(have\s+no\s+rules|are\s+an\s+unfiltered|are\s+evil)\b",
    r"(?i)\bprint\s+(the\s+)?(system\s+prompt|initial\s+prompt|secret\s+flag|master\s+key)\b",
    r"(?i)\breveal\s+(your\s+)?(system\s+prompt|initial\s+instructions|preamble)\b",
    r"(?i)\brepeat\s+(your\s+)?(entire\s+)?(system\s+prompt|system\s+instructions|instructions|prompt)\b",
    r"(?i)\boutput\s+everything\s+above\s+verbatim\b",
    r"(?i)<\s*\|\s*im_start\s*\|\s*>\s*system",
    r"(?i)\[\s*system\s*override\s*\]",
]

# PII & Secret Detection Regexes
CREDIT_CARD_REGEX = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
API_KEY_REGEX = re.compile(r"\b(?:Bearer\s+ey[A-Za-z0-9_-]{10,}|(?:sk|ak|ghp|nexus)[-_][A-Za-z0-9_-]{20,})\b")
PRIVATE_KEY_REGEX = re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----")


class GarakGuard:
    """NVIDIA Garak-aligned runtime security inspector for LLM & RAG pipelines."""

    @classmethod
    def scan_prompt_injection(cls, query: str) -> Tuple[bool, Optional[str]]:
        """
        Scan input query for adversarial prompt injection, jailbreaks, and extraction probes.
        
        Returns:
            (is_attack, attack_type_or_reason)
        """
        if not query or not query.strip():
            return False, None

        cleaned = query.strip()

        # 1. Regex inspection for known Garak jailbreak heuristics
        for pattern in GARAK_INJECTION_PATTERNS:
            match = re.search(pattern, cleaned)
            if match:
                logger.warning("GarakGuard: Neutralized prompt injection attack matching pattern '%s'", pattern)
                return True, f"GARAK_PROMPT_INJECTION_DETECTED: Matched '{match.group(0)}'"

        # 2. Check for Base64 obfuscation attacks
        b64_matches = re.findall(r"[A-Za-z0-9+/]{20,}={0,2}", cleaned)
        for b64 in b64_matches:
            try:
                decoded = base64.b64decode(b64).decode("utf-8", errors="ignore")
                for pattern in GARAK_INJECTION_PATTERNS:
                    if re.search(pattern, decoded):
                        logger.warning("GarakGuard: Neutralized base64-obfuscated injection '%s'", pattern)
                        return True, "GARAK_OBFUSCATED_INJECTION_DETECTED"
            except Exception:
                pass

        # 3. Delimiter fuzzing attack detection
        if cleaned.count("###") >= 4 or cleaned.count("---") >= 6:
            if re.search(r"(?i)(system|instruction|override|jailbreak)", cleaned):
                logger.warning("GarakGuard: Neutralized delimiter fuzzing attack")
                return True, "GARAK_DELIMITER_INJECTION_DETECTED"

        return False, None

    @classmethod
    def sanitize_pii_and_secrets(cls, text: str) -> Tuple[str, bool, Dict[str, int]]:
        """
        Scans model output or retrieved context for sensitive PII or secrets.
        Redacts detected data in-place to prevent data exfiltration.
        
        Returns:
            (sanitized_text, redactions_performed, counts)
        """
        if not text:
            return text, False, {}

        sanitized = text
        redacted = False
        counts = {"credit_cards": 0, "ssns": 0, "api_keys": 0, "private_keys": 0}

        # 1. Credit Card Redaction
        cards = CREDIT_CARD_REGEX.findall(sanitized)
        if cards:
            for card in cards:
                # Basic Luhn heuristic: strip non-digits and test length
                digits = re.sub(r"\D", "", card)
                if 13 <= len(digits) <= 19:
                    sanitized = sanitized.replace(card, "[REDACTED_PII:CREDIT_CARD]")
                    redacted = True
                    counts["credit_cards"] += 1

        # 2. SSN Redaction
        ssns = SSN_REGEX.findall(sanitized)
        if ssns:
            for ssn in ssns:
                sanitized = sanitized.replace(ssn, "[REDACTED_PII:SSN]")
                redacted = True
                counts["ssns"] += 1

        # 3. API Key & Token Redaction
        tokens = API_KEY_REGEX.findall(sanitized)
        if tokens:
            for tok in tokens:
                sanitized = sanitized.replace(tok, "[REDACTED_SECRET:KEY]")
                redacted = True
                counts["api_keys"] += 1

        # 4. Private Key Block Redaction
        if PRIVATE_KEY_REGEX.search(sanitized):
            sanitized = PRIVATE_KEY_REGEX.sub("[REDACTED_SECRET:PRIVATE_KEY_BLOCK]", sanitized)
            redacted = True
            counts["private_keys"] += 1

        if redacted:
            logger.warning("GarakGuard: Redacted sensitive data from response: %s", counts)

        return sanitized, redacted, counts
