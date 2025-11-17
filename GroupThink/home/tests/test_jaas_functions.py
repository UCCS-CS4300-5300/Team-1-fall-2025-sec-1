from django.test import TestCase
from unittest.mock import patch
from pathlib import Path

from django.conf import settings

from home.jaas_functions import generate_jaas_token, _load_private_key


class JaasFunctionTests(TestCase):
    """For testing various functions required for JaaS (Jitsi as a Service)"""

    @patch("home.jaas_functions.jwt.encode")
    @patch("home.jaas_functions.time.time", return_value=1000000)
    @patch.dict(
        "os.environ",
        {
            "JAAS_APP_ID": "test_app_id",
            "JAAS_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----FAKEKEY-----END PRIVATE KEY-----",
            "JAAS_API_KEY_ID": "fake_key_id",
        },
        clear=True,
    )
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

    # --- _load_private_key branch coverage ---

    @patch.dict(
        "os.environ",
        {"JAAS_PRIVATE_KEY": "not a valid pem"},
        clear=True,
    )
    def test_load_private_key_invalid_env_raises_typeerror(self):
        """If JAAS_PRIVATE_KEY is set but not a PEM, raise TypeError."""
        with self.assertRaises(TypeError):
            _load_private_key()

    @patch.dict("os.environ", {}, clear=True)
    def test_load_private_key_missing_env_and_file_raises_runtimeerror(self):
        """If no env and no key file exist, raise RuntimeError."""
        key_path = Path(settings.BASE_DIR) / "jaas_private.pem"
        if key_path.exists():
            key_path.unlink()

        with self.assertRaises(RuntimeError):
            _load_private_key()

    @patch.dict("os.environ", {}, clear=True)
    def test_load_private_key_reads_from_file_when_present(self):
        """If env is missing but file exists, it should read from file."""
        key_path = Path(settings.BASE_DIR) / "jaas_private.pem"
        key_contents = "-----BEGIN PRIVATE KEY-----\nFAKE-FILE-KEY\nPRIVATE KEY-----"
        key_path.write_text(key_contents)

        try:
            pem = _load_private_key()
            self.assertEqual(pem, key_contents)
        finally:
            if key_path.exists():
                key_path.unlink()

    # --- generate_jaas_token error path + defaults/flags ---

    @patch.dict(
        "os.environ",
        {
            # only private key present, missing app_id / key_id
            "JAAS_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----FAKEKEY-----END PRIVATE KEY-----"
        },
        clear=True,
    )
    def test_generate_jaas_token_missing_ids_raises_runtimeerror(self):
        """If JAAS_APP_ID or JAAS_API_KEY_ID are missing, raise RuntimeError."""
        with self.assertRaises(RuntimeError):
            generate_jaas_token("room123")

    @patch("home.jaas_functions.jwt.encode")
    @patch("home.jaas_functions.time.time", return_value=1000000)
    @patch.dict(
        "os.environ",
        {
            "JAAS_APP_ID": "test_app_id",
            "JAAS_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----FAKEKEY-----END PRIVATE KEY-----",
            "JAAS_API_KEY_ID": "fake_key_id",
        },
        clear=True,
    )
    def test_generate_jaas_token_defaults_and_feature_flags(
        self, mock_time, mock_jwt_encode
    ):
        """When using defaults, ensure user defaults + feature flags are set correctly."""
        mock_jwt_encode.return_value = "fake_jwt"

        # no explicit user_id/user_name → uses defaults in function
        generate_jaas_token("defaultRoom")

        args, kwargs = mock_jwt_encode.call_args
        payload = args[0]

        # default user values
        self.assertEqual(payload["context"]["user"]["id"], "dev_tester1")
        self.assertEqual(payload["context"]["user"]["name"], "Developer")

        features = payload["context"]["features"]
        self.assertTrue(features["recording"])
        self.assertFalse(features["livestreaming"])
        self.assertTrue(features["transcription"])
        self.assertFalse(features["outbound-call"])
        self.assertFalse(features["sip-outbound-call"])
