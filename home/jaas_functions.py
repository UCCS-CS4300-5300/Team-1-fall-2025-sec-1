import os, time, jwt

def generate_jaas_token(room_name, user_id="dev_tester1", user_name="Developer"):
    """Generates a JWT for the user to access the meeting"""

    # Creating JSON Web Token
    payload = {
        "aud": "jitsi",
        "iss": "chat",
        "sub": os.getenv('JAAS_APP_ID'),
        "room": room_name,
        "context": {
            "features": {  
                "recording": True,
                "livestreaming": True,
                "transcription": True,
                "outbound-call": True,
                "sip-outbound-call": False
            },
            "user": {
                "id": user_id,
                "name": user_name,
                "moderator": True
            }
        },
        "exp": int(time.time()) + 3600
    }

    # Get private key from environment
    private_key = os.getenv("JAAS_API_KEY")

    # Sign generated token with key
    token = jwt.encode(payload, private_key, algorithm="RS256", 
        headers={"kid": f"{os.getenv('JAAS_APP_ID')}/{os.getenv('JAAS_API_KEY_ID')}"})
    return token
