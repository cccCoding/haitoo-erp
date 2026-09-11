import unittest
from unittest.mock import patch

from cryptography.fernet import InvalidToken
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import credentials
from app.config import Settings
from app.credential_key_cli import rotate_stored_credentials
from app.database import Base
from app.models import Company, UserAIProviderCredential


class CredentialKeyTests(unittest.TestCase):
    def settings(self, *, jwt: str, current: str, legacy: str | None = None) -> Settings:
        return Settings(
            secret_key=jwt,
            credential_encryption_key=current,
            legacy_credential_encryption_key=legacy,
        )

    def test_jwt_and_credential_keys_cannot_be_identical(self) -> None:
        with self.assertRaisesRegex(ValidationError, "不能相同"):
            self.settings(jwt="same-key", current="same-key")

    def test_jwt_secret_change_does_not_affect_credential_decryption(self) -> None:
        first = self.settings(jwt="jwt-one", current="credential-key")
        second = self.settings(jwt="jwt-two", current="credential-key")
        with patch.object(credentials, "get_settings", return_value=first):
            encrypted = credentials.encrypt_secret("provider-secret")
        with patch.object(credentials, "get_settings", return_value=second):
            self.assertEqual(credentials.decrypt_secret(encrypted), "provider-secret")

    def test_legacy_key_is_used_only_when_explicitly_configured(self) -> None:
        old = self.settings(jwt="jwt", current="old-credential-key")
        with patch.object(credentials, "get_settings", return_value=old):
            encrypted = credentials.encrypt_secret("provider-secret")

        new_without_legacy = self.settings(jwt="jwt", current="new-credential-key")
        with patch.object(credentials, "get_settings", return_value=new_without_legacy):
            with self.assertRaises(InvalidToken):
                credentials.decrypt_secret(encrypted)

        new_with_legacy = self.settings(
            jwt="jwt",
            current="new-credential-key",
            legacy="old-credential-key",
        )
        with patch.object(credentials, "get_settings", return_value=new_with_legacy):
            self.assertEqual(credentials.decrypt_secret(encrypted), "provider-secret")

    def test_rotation_reencrypts_all_stored_credentials_with_current_key(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        old = self.settings(jwt="jwt", current="old-credential-key")
        with patch.object(credentials, "get_settings", return_value=old):
            company_secret = credentials.encrypt_secret("miaoshou-secret")
            user_secret = credentials.encrypt_secret("ai-secret")

        with Session(engine) as db:
            db.add(Company(name="Test", miaoshou_secret_encrypted=company_secret))
            db.add(UserAIProviderCredential(
                company_id=1,
                user_id=1,
                provider="grsai",
                secret_encrypted=user_secret,
            ))
            db.commit()

            rotating = self.settings(
                jwt="jwt",
                current="new-credential-key",
                legacy="old-credential-key",
            )
            with patch.object(credentials, "get_settings", return_value=rotating):
                self.assertEqual(rotate_stored_credentials(db), (1, 1))
                db.commit()

            current_only = self.settings(jwt="changed-jwt", current="new-credential-key")
            with patch.object(credentials, "get_settings", return_value=current_only):
                company = db.query(Company).one()
                credential = db.query(UserAIProviderCredential).one()
                self.assertEqual(credentials.decrypt_secret(company.miaoshou_secret_encrypted), "miaoshou-secret")
                self.assertEqual(credentials.decrypt_secret(credential.secret_encrypted), "ai-secret")
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
