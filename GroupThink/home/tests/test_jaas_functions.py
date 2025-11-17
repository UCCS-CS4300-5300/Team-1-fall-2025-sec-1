from django.test import TestCase
import jwt
from unittest.mock import patch
from home.jaas_functions import generate_jaas_token

class JaasFunctionTests(TestCase):
    """For testing various functions required for JaaS (Jitsi as a Service)"""

    @patch("home.jaas_functions.jwt.encode")
    @patch("home.jaas_functions.time.time", return_value=1000000)
    @patch.dict("os.environ", {
        "JAAS_APP_ID": "test_app_id",
        "JAAS_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----FAKEKEY-----END PRIVATE KEY-----",
        "JAAS_API_KEY_ID": "fake_key_id"
    })
    def test_generate_token_builds_correct_payload(self, mock_time, mock_jwt_encode):
        """Ensure the payload and signing details are correct."""

        mock_jwt_encode.return_value = "fake_jwt_token"

        token = generate_jaas_token("demoRoom", user_id="test_user", user_name="Tester")

        # Should return the encoded token
        self.assertEqual(token, "fake_jwt_token")

        # jwt.encode should have been called once
        mock_jwt_encode.assert_called_once()

        # Extract the arguments passed to jwt.encode
        args, kwargs = mock_jwt_encode.call_args
        payload = args[0]
        key = args[1]
        algorithm = kwargs.get("algorithm")
        headers = kwargs.get("headers")

        # Payload assertions
        self.assertEqual(payload["aud"], "jitsi")
        self.assertEqual(payload["iss"], "chat")
        self.assertEqual(payload["sub"], "test_app_id")
        self.assertEqual(payload["room"], "demoRoom")
        self.assertEqual(payload["context"]["user"]["id"], "test_user")
        self.assertEqual(payload["context"]["user"]["name"], "Tester")
        self.assertTrue(payload["context"]["user"]["moderator"])
        self.assertEqual(payload["exp"], 1000000 + 3600)

        # Signing and headers
        self.assertEqual(key, "-----BEGIN PRIVATE KEY-----FAKEKEY-----END PRIVATE KEY-----")
        self.assertEqual(algorithm, "RS256")
        self.assertEqual(headers, {"kid": "test_app_id/fake_key_id"})