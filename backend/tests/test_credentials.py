import unittest
from unittest.mock import patch

from cryptography.fernet import InvalidToken

from app.config import Settings
from app.credentials import decrypt_secret, encrypt_secret


class CredentialEncryptionTests(unittest.TestCase):
    def test_existing_ciphertext_uses_the_original_secret_key(self) -> None:
        original = Settings(_env_file=None, secret_key="original-key")
        with patch("app.credentials.get_settings", return_value=original):
            ciphertext = encrypt_secret("saved-credential")

        rotated = Settings(
            _env_file=None,
            secret_key="rotated-login-key",
            credential_encryption_key="original-key",
        )
        with patch("app.credentials.get_settings", return_value=rotated):
            self.assertEqual(decrypt_secret(ciphertext), "saved-credential")

        wrong_key = Settings(
            _env_file=None,
            secret_key="original-key",
            credential_encryption_key="different-key",
        )
        with patch("app.credentials.get_settings", return_value=wrong_key):
            with self.assertRaises(InvalidToken):
                decrypt_secret(ciphertext)


if __name__ == "__main__":
    unittest.main()
