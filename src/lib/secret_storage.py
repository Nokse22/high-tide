import gi
gi.require_version('Secret', '1')

from gi.repository import Secret

import json

class SecretStore():
    def __init__(self, _session):
        super().__init__()

        print("initializing secret store")

        self.version = "0.0"
        self.session = _session

        self.token_dictionary = {}
        self.attributes = {
            "version": Secret.SchemaAttributeType.STRING
        }

        self.schema = Secret.Schema.new(
            "io.github.nokse22.high-tide",
            Secret.SchemaFlags.NONE,
            self.attributes
        )

        self.key = "high-tide-login"

        password = Secret.password_lookup_sync(
            self.schema,
            {},
            None
        )

        try:
            if password:
                json_data = json.loads(password)
                self.token_dictionary = json_data

        except Exception as error:
            print("Failed to load secret store, resetting", error)

            self.token_dictionary = {}

    def get(self):
        return (self.token_dictionary["token-type"],
                self.token_dictionary["access-token"],
                self.token_dictionary["refresh-token"],
                self.token_dictionary["expiry-time"])

    def clear(self):
        self.token_dictionary.clear()
        self.save()

        Secret.password_clear_sync(
            self.schema,
            {},
            None
        )

    def save(self):
        token_type = self.session.token_type
        access_token = self.session.access_token
        refresh_token = self.session.refresh_token
        expiry_time = self.session.expiry_time

        self.token_dictionary = {
            "token-type": token_type,
            "access-token": access_token,
            "refresh-token": refresh_token,
            "expiry-time": str(expiry_time)
        }

        json_data = json.dumps(self.token_dictionary, indent=2)

        Secret.password_store_sync(
            self.schema,
            {},
            Secret.COLLECTION_DEFAULT,
            self.key,
            json_data,
            None
        )
