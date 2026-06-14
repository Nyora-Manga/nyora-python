# Over-the-air (OTA) updates

Nyora delivers its JavaScript parser bundle and source catalog **over the air**,
so you get new sources and parser fixes without upgrading the `nyora` package.
`nyora.ota.OtaManager` fetches a signed manifest from the public OTA feed,
verifies each artifact by SHA-256, and caches the bundle, catalog, and manifest
atomically in a per-user directory. When nothing is cached, reads transparently
fall back to the assets shipped inside the package, so the SDK works fully
**offline on first run**.

## The feed and artifacts

The OTA feed lives at:

```
https://Hasan72341.github.io/nyora-ota-parsers
```

The manager works with three artifacts:

| Artifact | Filename | Purpose |
| --- | --- | --- |
| Manifest | `manifest.json` | Version number plus per-artifact `url` and `sha256`. |
| Parser bundle | `parsers.bundle.js` | The JavaScript parser bundle run by the runtime. |
| Source catalog | `sources.json` | The catalog of available sources. |

The manifest contains an integer `version` and `bundle`/`sources` entries, each
with a `url` and an optional `sha256` checksum.

## Cache location

Cached artifacts live under the per-user cache directory (resolved by
`platformdirs`):

```
<user cache dir>/nyora/ota/
  manifest.json
  parsers.bundle.js
  sources.json
```

Read `OtaManager().cache_dir` to get the exact path on your platform. You can
override it by constructing `OtaManager(cache_dir=Path(...))`.

### Offline fallback

If a cached artifact is missing, the manager reads the copy **bundled inside the
package** (`nyora.assets`). This is why a fresh install works with no network:
the shipped bundle and catalog are used until you pull an update.

## From the default client

The simplest path is through `nyora.Nyora`, which owns an `OtaManager` as
`client.ota` and adds two convenience methods.

### Check without applying

```python
from nyora import Nyora

with Nyora() as client:
    available, installed, latest = client.check_update()
    print(available, installed, latest)
```

`check_update()` returns `(available, installed_version, latest_version)`.
Versions are `None` when unknown (nothing installed yet, or the manifest could
not be reached). Network and manifest errors are treated as "no update
available" rather than raising, so it is safe to call opportunistically.

### Apply an update

```python
from nyora import Nyora

with Nyora() as client:
    result = client.update()           # or client.update(force=True)
    print("updated:", result.updated)
    print("version:", result.version)
```

`client.update(*, force=False)` downloads and verifies the latest artifacts,
writes them to the cache, **and reloads the embedded runtime** so the new
parsers are live in the same process. With `force=True` it re-downloads even when
already current. It returns an `OtaUpdateResult`.

## Using `OtaManager` directly

```python
from nyora.ota import OtaManager

ota = OtaManager(timeout=30.0)
print("cache dir:", ota.cache_dir)

available, installed, latest = ota.is_update_available()
if available:
    result = ota.update()
    print("updated to", result.version, "at", result.bundle_path)
```

```{note}
`OtaManager.update()` only writes the cache — it does **not** reload any running
runtime. If you call it on a bare manager while a `Nyora` client is live, call
`client._runtime.reload()` or just use `client.update()` instead, which does
both.
```

### `OtaManager` methods

- `cache_dir` (property) — the directory where artifacts are cached.
- `fetch_manifest() -> dict` — download and parse the remote manifest. Raises
  `nyora.NyoraError` if it cannot be fetched or is not a JSON object.
- `installed_version() -> int | None` — the version currently cached, or `None`.
- `is_update_available() -> tuple[bool, int | None, int | None]` — returns
  `(available, installed, latest)`; never raises on network/manifest errors.
- `update(*, force=False) -> OtaUpdateResult` — download, SHA-256-verify, and
  atomically write the artifacts. Raises `nyora.NyoraError` on fetch failure or a
  checksum mismatch.
- `read_bundle_text() -> str` — the parser bundle text (cached, else bundled
  fallback).
- `read_sources_text() -> str` — the source-catalog JSON (cached, else bundled
  fallback).

### `OtaUpdateResult`

The dataclass returned by `update()`:

| Field | Type | Meaning |
| --- | --- | --- |
| `updated` | `bool` | `True` if new artifacts were written; `False` if already current. |
| `version` | `int` | The manifest version now installed in the cache. |
| `bundle_path` | `Path` | Path to the cached parser bundle. |
| `sources_path` | `Path` | Path to the cached source catalog. |

## Integrity and atomicity

- **SHA-256 verification.** When the manifest entry includes a `sha256`, the
  downloaded bytes are hashed and compared; a mismatch raises
  `nyora.NyoraError` and nothing is written.
- **Atomic writes.** Each artifact is written to a temp file in the cache
  directory and then `os.replace`d into place, so a cache file is never left
  half-written.
- **No-op when current.** Without `force`, if the installed version is at least
  the latest and both cached files exist, `update()` returns
  `OtaUpdateResult(updated=False, ...)` without downloading.

## From the CLI

The `nyora-cli update` command runs the same flow as `Nyora().update()`. See the
CLI docs for its flags and output. The helper client also exposes the helper's
own OTA status via `client.system.ota_status()` and `client.system.ota_check()`
(see the [library guide](library.md)); those query the **helper's** feed, not
this in-process manager.

## Related

- [Library guide](library.md) — `Nyora.update()` / `check_update()` in context.
- [API reference](../reference/api.md) — autodoc for `nyora.ota`.
