#!/usr/bin/env python3
# Copyright 2023 Shayan
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

https://discourse.charmhub.io/t/4208
"""

import logging

import ops
from ops import ActiveStatus, SecretNotFoundError
from ops.charm import ActionEvent

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)

VALID_LOG_LEVELS = ["info", "debug", "warning", "error", "critical"]
PEER = "charm-peer"


class SecretsTestCharm(ops.CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)

        self._secrets = {}
        self._secret_meta = None

        self.framework.observe(self.on.start, self._on_start)

        self.framework.observe(self.on.set_secret_action, self._on_set_secret_action)
        self.framework.observe(self.on.get_secrets_action, self._on_get_secrets_action)
        self.framework.observe(self.on.delete_secrets_action, self._on_delete_secrets_action)
        self.framework.observe(self.on.pseudo_delete_secrets_action, self._on_pseudo_delete_secrets_action)
        self.framework.observe(self.on.forget_all_secrets_action, self._on_forget_all_secrets_action)

    def _on_start(self, event) -> None:
        self.unit.status = ActiveStatus()

    def _on_set_secret_action(self, event: ActionEvent):
        content = event.params
        event.set_results({"secret-id": self.set_secret(content)})

    def _on_get_secrets_action(self, event: ActionEvent):
        """Return the secrets stored in juju secrets backend."""
        event.set_results({"secrets": self.get_secrets()})

    def _on_delete_secrets_action(self, event: ActionEvent):
        keys = event.params.get("keys")
        for key in keys:
            self.delete_secret(key)

    def _on_pseudo_delete_secrets_action(self, event: ActionEvent):
        keys = event.params.get("keys")
        for key in keys:
            self.set_secret({key: "### DELETED ###"})

    def _on_forget_all_secrets_action(self, event: ActionEvent):
        if self.app_peer_data.get("secret-id"):
            del self.app_peer_data["secret-id"]
            self.secret_meta = None

    @property
    def peers(self) -> ops.model.Relation:
        """Retrieve the peer relation (`ops.model.Relation`)."""
        return self.model.get_relation(PEER)

    @property
    def app_peer_data(self) -> dict[str, str]:
        """Application peer relation data object."""
        if self.peers is None:
            return {}
        return self.peers.data[self.app]

    @property
    def secret_meta(self):
        if not self._secret_meta:
            secret_id = self.app_peer_data.get("secret-id")
            if not secret_id:
                return
            try:
                self._secret_meta = self.model.get_secret(id=secret_id)
            except SecretNotFoundError:
                return
        return self._secret_meta

    @secret_meta.setter
    def secret_meta(self, secret):
        if secret:
            self.app_peer_data["secret-id"] = secret.id
        else:
            del self.app_peer_data["secret-id"]
        self._secret_meta = secret

    @property
    def cached_secrets(self):
        if not self._secrets and self.secret_meta:
            content = self.secret_meta.get_content()
            if content:
                self._secrets = content
        return self._secrets

    def append_cached_secret(self, new_content):
        self._secrets.update(new_content)

    def create_cached_secret(self, content):
        self._secrets = content

    def remove_cached_secret(self, key):
        if key in self._secrets:
            del self._secrets[key]

    def get_secrets(self) -> dict[str, str]:
        """Get the secrets stored in juju secrets backend."""
        return self.cached_secrets

    def set_secret(self, new_content: dict) -> None:
        """Set the secret in the juju secret storage."""

        if self.cached_secrets:
            self.append_cached_secret(new_content)
            self.secret_meta.set_content(self.cached_secrets)
            logger.info(f"Set secret {self.secret_meta.id} to {self.cached_secrets}")
        else:
            self.create_cached_secret(new_content)
            self.secret_meta = self.app.add_secret(self.cached_secrets)
            logger.info(f"Added secret {self.secret_meta.id} with {new_content}")

        return self.secret_meta.id

    def delete_secret(self, key: str) -> None:
        """Remove a secret."""
        if not self.cached_secrets:
            logging.error("Can't delete any secrets as we have none defined")

        self.remove_cached_secret(key)
        logger.info(f"Removing {key} from secret {self.secret_meta.id}")

        if self.cached_secrets:
            self.secret_meta.set_content(self.cached_secrets)
            logger.info(f"Remaining content is {list(self.cached_secrets.keys())}")
        else:
            self.secret_meta.remove_all_revisions()
            self.secret_meta = None
            logger.info("No secrets remained")


if __name__ == "__main__":  # pragma: nocover
    ops.main(SecretsTestCharm)
