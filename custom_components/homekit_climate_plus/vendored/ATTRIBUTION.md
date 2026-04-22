# Vendored Code Attribution

Files in this directory are vendored from
[`home-assistant/core`](https://github.com/home-assistant/core), licensed
under the Apache License, Version 2.0.

All three files were copied from Home Assistant release **2026.4.3**, which
pins to commit SHA:

```
1fec38ef28c33ec8fe6e0ec6a33a1ca144b1cc24
```

| Local file | Upstream path | Direct link |
|---|---|---|
| [`type_thermostats.py`](./type_thermostats.py) | `homeassistant/components/homekit/type_thermostats.py` | [view](https://github.com/home-assistant/core/blob/1fec38ef28c33ec8fe6e0ec6a33a1ca144b1cc24/homeassistant/components/homekit/type_thermostats.py) |
| [`accessories.py`](./accessories.py) | `homeassistant/components/homekit/accessories.py` | [view](https://github.com/home-assistant/core/blob/1fec38ef28c33ec8fe6e0ec6a33a1ca144b1cc24/homeassistant/components/homekit/accessories.py) |
| [`util.py`](./util.py) | `homeassistant/components/homekit/util.py` | [view](https://github.com/home-assistant/core/blob/1fec38ef28c33ec8fe6e0ec6a33a1ca144b1cc24/homeassistant/components/homekit/util.py) |

Each vendored `.py` file has been prepended with an `Adapted for
homekit_climate_plus` header recording the source path and upstream commit
SHA.

## Modifications from upstream

To keep the vendored package runnable without vendoring every transitive
helper module, these relative imports were rewritten to point at Home
Assistant's live `homekit` integration modules:

- `from .const import …` → `from homeassistant.components.homekit.const import …`
- `from .iidmanager import …` → `from homeassistant.components.homekit.iidmanager import …`
- `from .models import …` → `from homeassistant.components.homekit.models import …`

Sibling relative imports within the vendored package (`from .accessories
import …`, `from .util import …`) were left unchanged; they resolve to
our own vendored copies.

### Syntax fix in `util.py`

Two occurrences of `except ValueError, TypeError:` (Python 2 syntax, a
`SyntaxError` under Python 3) in `convert_to_float` and `coerce_int` were
replaced with the valid Python 3 form `except (ValueError, TypeError):`.
The bug is present in upstream HA 2026.4.3 and on `dev`; behaviour of
both functions is unchanged. Report upstream if not already filed.

No other changes were made to the upstream source.

## Re-syncing

To re-sync vendored code against a newer Home Assistant release:

1. Identify the new target release tag (e.g. `2026.5.0`).
2. Look up its commit SHA: `gh api repos/home-assistant/core/git/refs/tags/<tag>`.
3. Re-download the three files from that SHA.
4. Re-apply the header and import-rewrite patches.
5. Update this file's version + SHA.
6. Bump our package minor version (e.g. `0.1.0` → `0.2.0`).
7. Note the resync in `CHANGELOG.md` under a "Vendored" subsection.
