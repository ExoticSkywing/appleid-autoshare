from __future__ import annotations

import base64
import json
from app.config import Settings
from app.services.pow import PowVerifier


def test_pow_verifier_flow(settings: Settings) -> None:
    verifier = PowVerifier(settings)

    # 1. Create challenge
    challenge = verifier.create_challenge()
    assert challenge["algorithm"] == "SHA-256"
    assert "salt" in challenge
    assert "signature" in challenge
    assert "challenge" in challenge

    # 2. Solve challenge
    import hashlib
    salt = challenge["salt"]
    target = challenge["challenge"]
    max_num = challenge["maxnumber"]
    found_number = None
    for n in range(max_num + 1):
        if hashlib.sha256(f"{salt}{n}".encode()).hexdigest() == target:
            found_number = n
            break

    assert found_number is not None

    # 3. Verify valid solution
    payload = base64.b64encode(json.dumps({
        "algorithm": challenge["algorithm"],
        "challenge": challenge["challenge"],
        "number": found_number,
        "salt": challenge["salt"],
        "signature": challenge["signature"],
    }).encode()).decode()

    valid, err = verifier.verify_solution(payload)
    assert valid is True
    assert err is None

    # 4. Verify invalid solution
    invalid_payload = base64.b64encode(json.dumps({
        "algorithm": challenge["algorithm"],
        "challenge": challenge["challenge"],
        "number": found_number + 1,
        "salt": challenge["salt"],
        "signature": challenge["signature"],
    }).encode()).decode()

    invalid, err = verifier.verify_solution(invalid_payload)
    assert invalid is False
    assert err == "solution_incorrect"
