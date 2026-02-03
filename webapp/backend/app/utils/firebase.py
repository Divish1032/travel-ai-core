"""
Firebase Admin SDK integration.

This module provides Firebase Authentication token verification
and user management using the Firebase Admin SDK.
"""

import firebase_admin
from firebase_admin import credentials, auth
from typing import Dict

from app.config import settings


class FirebaseAdmin:
    """
    Singleton class for Firebase Admin SDK integration.

    Handles Firebase app initialization and token verification.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        """Singleton pattern implementation."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self) -> None:
        """
        Initialize Firebase Admin SDK.

        Only initializes once per application lifecycle.
        Uses service account credentials from FIREBASE_CREDENTIALS_PATH.
        """
        if self._initialized:
            return

        # Check if Firebase credentials path exists
        import os
        if not os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
            print(f"⚠️  Firebase credentials not found at: {settings.FIREBASE_CREDENTIALS_PATH}")
            print("⚠️  Authentication endpoints will not work until Firebase is configured")
            print("⚠️  See: https://console.firebase.google.com/ to set up Firebase")
            self._initialized = False
            return

        try:
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred)
            self._initialized = True
            print("✓ Firebase Admin SDK initialized successfully")
        except Exception as e:
            print(f"✗ Firebase Admin SDK initialization failed: {e}")
            self._initialized = False

    async def verify_token(self, id_token: str) -> Dict:
        """
        Verify Firebase ID token and return decoded claims.

        Args:
            id_token: Firebase ID token from client

        Returns:
            Decoded token claims containing user information

        Raises:
            ValueError: If token is invalid or expired
        """
        try:
            # Verify the ID token while checking if the token is revoked
            decoded_token = auth.verify_id_token(id_token, check_revoked=True)
            return decoded_token
        except auth.RevokedIdTokenError:
            raise ValueError("Token has been revoked")
        except auth.ExpiredIdTokenError:
            raise ValueError("Token has expired")
        except auth.InvalidIdTokenError:
            raise ValueError("Invalid token")
        except Exception as e:
            raise ValueError(f"Token verification failed: {str(e)}")

    def get_user(self, uid: str):
        """
        Get user information from Firebase by UID.

        Args:
            uid: Firebase user UID

        Returns:
            UserRecord object from Firebase

        Raises:
            ValueError: If user not found
        """
        try:
            return auth.get_user(uid)
        except Exception as e:
            raise ValueError(f"Failed to get user: {str(e)}")


# Global Firebase Admin instance
firebase_admin_instance = FirebaseAdmin()
