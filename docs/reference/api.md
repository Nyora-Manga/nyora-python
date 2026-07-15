# API reference

Auto-generated reference for every public symbol in the **Nyora library**
(`import nyora`). Each section renders the live docstrings of a module. For
narrative usage, see the [library guide](../guide/library.md).

## Package overview

The top-level `nyora` package re-exports the client, the async client, the
sync client, the model dataclasses, and the exception hierarchy. Each
re-exported symbol is documented in full under its canonical module section
below.

```{eval-rst}
.. automodule:: nyora
   :no-members:
```

## `nyora.client`

The clients (`Nyora`, `AsyncNyora`) — a bare `Nyora()` auto-launches a bundled local engine, or point it at a server via `base_url` / `nyora config set-url`.

```{eval-rst}
.. automodule:: nyora.client
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource
```

## `nyora.sync`

Cloud account and library sync (`NyoraSync`) against the Nyora sync server.

```{eval-rst}
.. automodule:: nyora.sync
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource
```

## `nyora.models`

Typed dataclasses returned throughout the SDK.

```{eval-rst}
.. automodule:: nyora.models
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource
```

## `nyora.errors`

The SDK exception hierarchy.

```{eval-rst}
.. automodule:: nyora.errors
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource
```

## `nyora.config`

Endpoint-discovery configuration: environment variables and the port file.

```{eval-rst}
.. automodule:: nyora.config
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource
```

## Services

The service objects attached to the client (`nyora.client.Nyora`).

### `nyora.services.sources`

```{eval-rst}
.. automodule:: nyora.services.sources
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource
```

### `nyora.services.manga`

```{eval-rst}
.. automodule:: nyora.services.manga
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource
```

### `nyora.services.library`

```{eval-rst}
.. automodule:: nyora.services.library
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource
```

### `nyora.services.downloads`

```{eval-rst}
.. automodule:: nyora.services.downloads
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource
```

### `nyora.services.backup`

Includes `BackupService`, `LocalService`, `TrackerService`, and `SystemService`.

```{eval-rst}
.. automodule:: nyora.services.backup
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource
```
