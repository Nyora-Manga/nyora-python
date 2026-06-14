# API reference

Auto-generated reference for every public symbol in the **Nyora library**
(`import nyora`). Each section renders the live docstrings of a module. For
narrative usage, see the [library guide](../guide/library.md).

## Package overview

The top-level `nyora` package re-exports the primary client, the helper REST
clients, the OTA manager, the embedded server, the model dataclasses, and the
exception hierarchy. Each re-exported symbol is documented in full under its
canonical module section below.

```{eval-rst}
.. automodule:: nyora
   :no-members:
```

## `nyora.direct`

The default, self-contained client and its in-process services.

```{eval-rst}
.. automodule:: nyora.direct
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource
```

## `nyora.client`

The helper-backed REST clients (`Nyora`, `AsyncNyora`).

```{eval-rst}
.. automodule:: nyora.client
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

## `nyora.ota`

Over-the-air parser-bundle and source-catalog management.

```{eval-rst}
.. automodule:: nyora.ota
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource
```

## `nyora.server`

The stdlib HTTP server exposing the helper-compatible REST contract.

```{eval-rst}
.. autoclass:: nyora.server.NyoraServer
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource
```

## `nyora.runtime`

The embedded QuickJS parser runtime that backs the direct client and the server.

```{eval-rst}
.. automodule:: nyora.runtime
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

Helper-discovery configuration: environment variables and the port file.

```{eval-rst}
.. automodule:: nyora.config
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource
```

## Services

The service objects attached to the helper client (`nyora.client.Nyora`).

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

Includes `BackupService`, `SyncService`, `LocalService`, `TrackerService`, and
`SystemService`.

```{eval-rst}
.. automodule:: nyora.services.backup
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource
```
