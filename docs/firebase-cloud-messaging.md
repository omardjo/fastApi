# Firebase Cloud Messaging

Backend notifications use Firebase Admin SDK and the `FIREBASE_SERVICE_ACCOUNT_PATH`
environment variable. Do not commit the service account JSON file.

1. Go to Firebase Console -> Riwaq -> Project settings -> Service accounts.
2. Generate a new private key.
3. Save the JSON locally under `secrets/riwaq-firebase-adminsdk.json`.
4. Add `FIREBASE_SERVICE_ACCOUNT_PATH=secrets/riwaq-firebase-adminsdk.json` to `.env`.
5. Install dependencies with `pip install -r requirements.txt`.
6. Run `uvicorn blogapi.main:app --reload`.
7. Test `POST /notifications/test` from Postman using an Android FCM token.

Example request:

```json
{
  "token": "android-fcm-token",
  "title": "FCM test",
  "body": "Hello from Riwaq backend",
  "data": {
    "type": "test",
    "route": "/notifications/test"
  }
}
```

If Firebase is not configured locally, the endpoint returns a skipped response instead
of crashing the FastAPI app.
