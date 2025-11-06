import os, time, jwt

def generate_jaas_token(room_name, user_id="dev_tester1", user_name="Developer"):
    """Generates a JaaS JWT for the meeting."""

    app_id = os.getenv("JAAS_APP_ID")
    key_id = os.getenv("JAAS_API_KEY_ID")

    # Read private key from env and normalize newlines
    private_key = (os.getenv("JAAS_API_KEY") or "").replace("\\n", "\n").strip()

    # Fail fast with a readable message if anything is missing/misformatted
    missing = [k for k, v in {
        "JAAS_APP_ID": app_id,
        "JAAS_API_KEY_ID": key_id,
        "JAAS_API_KEY": private_key
    }.items() if not v]
    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")

    if not private_key.startswith("-----BEGIN") or "PRIVATE KEY-----" not in private_key:
        raise TypeError("JAAS_API_KEY is not a PEM-formatted private key")

    payload = {
        "aud": "jitsi",
        "iss": "chat",
        "sub": app_id,
        "room": room_name,
        "context": {
            "features": {
                "recording": False,
                "livestreaming": False,
                "transcription": False,
                # "transcription": True, <-- remove line above and uncomment to enable transcriptions (disabled right now for cost)
                "outbound-call": False,
                "sip-outbound-call": False,
            },
            "user": {"id": user_id, "name": user_name, "moderator": True},
        },
        "exp": int(time.time()) + 3600,
    }

    headers = {"kid": f"{app_id}/{key_id}"}
    return jwt.encode(payload, private_key, algorithm="RS256", headers=headers)
