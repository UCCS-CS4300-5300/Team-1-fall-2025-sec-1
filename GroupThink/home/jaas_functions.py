import os, time, jwt
from django.conf import settings
from pathlib import Path

def _load_private_key(key_file_name="jaas_private.pem"):
    # prefer explicit env that contains PEM content
    pem_env = os.environ.get("JAAS_PRIVATE_KEY")
    if pem_env:
        pem = pem_env.strip()
        if not pem.startswith("-----BEGIN") or "PRIVATE KEY-----" not in pem:
            raise TypeError("JAAS_PRIVATE_KEY env does not contain a valid PEM private key")
        return pem

    # fallback to file at BASE_DIR / key_file_name
    key_file = os.getenv("JAAS_KEY_FILE", key_file_name)
    key_path = Path(settings.BASE_DIR) / key_file

    if key_path.exists():
        pem = key_path.read_text().strip()
        if not pem.startswith("-----BEGIN") or "PRIVATE KEY-----" not in pem:
            raise TypeError(f"JAAS key file at {key_path} does not contain a valid PEM private key")
        return pem

    # neither env nor file present -> helpful error
    raise RuntimeError(
        "JAAS private key not found. Provide JAAS_PRIVATE_KEY (PEM content) as an env var "
        "or place the PEM file at: " + str(key_path)
    )

def generate_jaas_token(room_name, user_id="dev_tester1", user_name="Developer"):
    """Generates a JaaS JWT for the meeting."""
    app_id = os.getenv("JAAS_APP_ID")
    key_id = os.getenv("JAAS_API_KEY_ID")

    if not app_id or not key_id:
        raise RuntimeError("JAAS_APP_ID or JAAS_API_KEY_ID environment variables are missing")

    private_key = _load_private_key()  # returns PEM string

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
