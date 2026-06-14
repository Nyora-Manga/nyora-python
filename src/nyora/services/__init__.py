"""Service wrappers for Nyora helper endpoints.

Each service groups a related slice of the helper REST API into typed methods
and is attached to a :class:`nyora.client.Nyora` instance as an attribute
(``client.sources``, ``client.manga``, ``client.library``,
``client.downloads``, ``client.backup``, ``client.system``). Methods issue
requests through the owning client and decode responses into
:mod:`nyora.models` dataclasses.
"""
