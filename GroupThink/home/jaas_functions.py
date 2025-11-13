import os, time, jwt
from django.conf import settings
from pathlib import Path

def generate_jaas_token(room_name, user_id="dev_tester1", user_name="Developer"):
    """Generates a JaaS JWT for the meeting."""

    app_id = os.getenv("JAAS_APP_ID")
    key_id = os.getenv("JAAS_API_KEY_ID")

    key_file = os.getenv("JAAS_KEY_FILE", "jaas_private.pem")
    key_path = Path(settings.BASE_DIR) / key_file

    if not key_path.exists():
        raise RuntimeError(f"JAAS key file not found at {key_path}")

    private_key = key_path.read_text().strip()

    # Basic sanity check so we fail with a clearer error if something is off
    if not private_key.startswith("-----BEGIN") or "PRIVATE KEY-----" not in private_key:
        raise TypeError("JAAS key file does not contain a valid PEM private key")

    payload = {
        "aud": "jitsi",
        "iss": "chat",
        "sub": app_id,
        "room": room_name,
        "context": {
            "features": {
                "recording": True,
                "livestreaming": False,
                "transcription": True,
                "outbound-call": False,
                "sip-outbound-call": False,
            },
            "user": {"id": user_id, "name": user_name, "moderator": True},
        },
        "exp": int(time.time()) + 3600,
    }

    headers = {"kid": f"{app_id}/{key_id}"}
    return jwt.encode(payload, private_key, algorithm="RS256", headers=headers)
