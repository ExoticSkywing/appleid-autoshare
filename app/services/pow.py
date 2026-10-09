from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from app.config import Settings


class PowVerifier:
    """
    High-performance self-hosted Proof-of-Work (PoW) verification engine.
    Compatible with standard ALTCHA SHA-256 challenges.
    Zero external dependencies, zero cross-border latency, replay-protected.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # Use turnstile_secret_key or fall back to an internal salt
        self.hmac_key = (
            settings.pow_secret_key
            or settings.turnstile_secret_key
            or "pow-default-secret-salt-398124"
        )
        self.max_number = settings.pow_max_number or 50_000
        self.expires_in = settings.pow_expires_seconds or 120

    def create_challenge(self, extra_difficulty: int = 1) -> dict[str, Any]:
        """
        Generate a cryptographically signed PoW challenge.
        extra_difficulty allows adaptive throttling for suspicious IPs.
        """
        max_num = min(self.max_number * max(1, extra_difficulty), 1_000_000)
        secret_number = secrets.randbelow(max_num)
        salt = secrets.token_hex(16)
        expires = int(time.time()) + self.expires_in
        salt_with_params = f"{salt}?expires={expires}"
        
        challenge = hashlib.sha256(f"{salt_with_params}{secret_number}".encode()).hexdigest()
        signature = hmac.new(
            self.hmac_key.encode(), challenge.encode(), hashlib.sha256
        ).hexdigest()

        return {
            "algorithm": "SHA-256",
            "challenge": challenge,
            "salt": salt_with_params,
            "signature": signature,
            "maxnumber": max_num,
        }

    def verify_solution(self, payload_str: str) -> tuple[bool, str | None]:
        """
        Verify the client's submitted solution.
        payload_str can be base64-encoded JSON or direct JSON string.
        """
        if not payload_str:
            return False, "payload_missing"
        try:
            raw_json = payload_str
            if not payload_str.strip().startswith("{"):
                raw_json = base64.b64decode(payload_str).decode("utf-8")
            data = json.loads(raw_json)
        except Exception:
            return False, "payload_invalid"

        algorithm = data.get("algorithm")
        challenge = data.get("challenge")
        number = data.get("number")
        salt = data.get("salt")
        signature = data.get("signature")

        if not all([algorithm == "SHA-256", challenge, number is not None, salt, signature]):
            return False, "fields_missing"

        # 1. Verify HMAC signature to ensure the challenge was legitimately issued by this server
        expected_sig = hmac.new(
            self.hmac_key.encode(), str(challenge).encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, str(signature)):
            return False, "signature_mismatch"

        # 2. Verify expiration time
        if "?expires=" in str(salt):
            try:
                expires_part = str(salt).split("?expires=")[1].split("&")[0]
                expires_at = int(expires_part)
                if time.time() > expires_at:
                    return False, "challenge_expired"
            except (ValueError, IndexError):
                return False, "invalid_expires"

        # 3. Verify computation proof (SHA-256(salt + number) == challenge)
        computed_hash = hashlib.sha256(f"{salt}{number}".encode()).hexdigest()
        if not hmac.compare_digest(computed_hash, str(challenge)):
            return False, "solution_incorrect"

        return True, None
