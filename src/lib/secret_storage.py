# secret_storage.py
#
# Copyright 2025 Nokse <nokse@posteo.com>
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 3 of the License, or (at
# your option) any later version.
#
# This file is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public
# License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: LGPL-3.0-or-later

from gi.repository import Secret

import json
import os


class SecretStore:
    def __init__(self, _session):
        super().__init__()

        print("initializing secret store")

        self.version = "0.0"
        self.session = _session

        self.token_dictionary = {}
        self.attributes = {"version": Secret.SchemaAttributeType.STRING}

        self.schema = Secret.Schema.new(
            "io.github.nokse22.high-tide", Secret.SchemaFlags.NONE, self.attributes
        )

        self.key = "high-tide-login"
        
        # Ensure the Login keyring is unlocked (https://github.com/Nokse22/high-tide/issues/97)
        # This is also only possible outside of a flatpak.
        if not os.path.exists('/.flatpak-info'):
            service = Secret.Service.get_sync(Secret.ServiceFlags.NONE)
            if service:
                collection = Secret.Collection.for_alias_sync(service, Secret.COLLECTION_DEFAULT, Secret.CollectionFlags.NONE)
                if collection and collection.get_locked():
                    print("Collection is locked, attempting to unlock")
                    service.unlock_sync([collection])

        password = Secret.password_lookup_sync(self.schema, {}, None)
        try:
            if password:
                json_data = json.loads(password)
                self.token_dictionary = json_data

        except Exception as error:
            print("Failed to load secret store, resetting", error)

            self.token_dictionary = {}

    def get(self):
        return (
            self.token_dictionary["token-type"],
            self.token_dictionary["access-token"],
            self.token_dictionary["refresh-token"],
            self.token_dictionary["expiry-time"],
        )

    def clear(self):
        self.token_dictionary.clear()
        self.save()

        Secret.password_clear_sync(self.schema, {}, None)

    def save(self):
        token_type = self.session.token_type
        access_token = self.session.access_token
        refresh_token = self.session.refresh_token
        expiry_time = self.session.expiry_time

        self.token_dictionary = {
            "token-type": token_type,
            "access-token": access_token,
            "refresh-token": refresh_token,
            "expiry-time": str(expiry_time),
        }

        json_data = json.dumps(self.token_dictionary, indent=2)

        Secret.password_store_sync(
            self.schema, {}, Secret.COLLECTION_DEFAULT, self.key, json_data, None
        )
