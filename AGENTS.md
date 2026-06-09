# Agent guide — irrigation_unlimited

Primary, tool-agnostic agent guide (read by Cursor, Claude Code, Copilot, Codex, etc.). This file is repo-wide orientation.

**There are no nested `AGENTS.md` files** — the integration is a single Python package with no subsystem deep enough to warrant one yet. Everything lives here.

## What this is

A **Home Assistant custom integration** (Python, distributed via **HACS**) that provides flexible irrigation scheduling. Domain: **`irrigation_unlimited`**. It models a hierarchy of **controllers → zones / sequences → schedules**, drives switch entities on a virtual clock, and exposes a rich service + attribute surface. `iot_class: local_polling`, no cloud.

It is one half of a **backend/frontend pair**:

- **`irrigation-unlimited-card`** (sibling repo, `home-assistant/irrigation-unlimited-card`) — the Lovelace card that visualizes/controls this integration. It reads this integration's **entity attributes** and calls its **services**.
- **`ha-assets`** (sibling repo) — the live HA config; its dashboards, `packages/`, automations, and template sensors consume this integration's **entities, attributes, services, and events**.

A change to this integration's entity/attribute/service/event shape usually requires a matching change in the card and can silently break dashboards/automations in `ha-assets`. See **Ripple awareness** below.

### Fork status (important)

This repo is a **fork of the upstream HACS integration `rgc99/irrigation_unlimited`** (origin remote: `github.com:nantomarioni/irrigation_unlimited`; `manifest.json`/`const.py` still point `documentation`/`issue_tracker`/`codeowners` at `rgc99`). It has **local divergence from upstream** — at minimum:

- A local feature commit `feat: add interleave option for parallel zone scheduling` (the `interleave` config option) at HEAD.
- `manifest.json` here sets **`config_flow: false`** whereas upstream `master` sets `config_flow: true`. This integration is **YAML-configured** (`CONFIG_SCHEMA` under the `irrigation_unlimited:` key in `configuration.yaml`); there is **no UI config flow** in this fork.

When changing behavior, prefer keeping parity with upstream where practical, but treat the local changes (interleave, YAML-only setup) as intentional. If you pull from upstream, re-check `config_flow` and the `interleave` option don't get clobbered. *(There is no `upstream` git remote configured; add one if you need to diff against `rgc99/irrigation_unlimited`.)*

## How to run things

There is **no tox/nox/Makefile/pre-commit**. Use a venv + the requirements files. (`scripts/setup` and `scripts/develop` are for running a live HA dev instance, not for tests — `scripts/setup` also runs `npm install`, which is unrelated to the Python integration.)

```bash
# One-time: create + activate a venv and install test deps
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements_test.txt   # pulls homeassistant + pytest-homeassistant-custom-component, crontab, etc.

# Run the full test suite (config is in pytest.ini: testpaths=tests, asyncio_mode=auto, --cov)
pytest tests/

# CI-equivalent invocation (see .github/workflows/pull.yml)
pytest -qq --timeout=300 --durations=10 -n auto \
  --cov custom_components.irrigation_unlimited \
  -o console_output_style=count -p no:sugar tests

# Run a single file / single test
pytest tests/test_service.py
pytest tests/test_service.py -k test_service_adjust_time

# Coverage with missing-line report
pytest --durations=10 --cov-report term-missing \
  --cov=custom_components.irrigation_unlimited tests
```

- `requirements.txt` pins `homeassistant==2025.3.1` (used by `scripts/develop` for a live instance); `requirements_test.txt` pins `pytest-homeassistant-custom-component==0.13.222` plus `aiohttp_cors`, `crontab`, `pytest-asyncio`. The CI runs tests on **Python 3.13**.
- **Linting/formatting**: CI uses **`black`** (`python3 -m pip install black && black .`). `setup.cfg` also configures **flake8** (max-line-length 88, ignores E501/W503/E203/D202/W504) and **isort** (`known_first_party = custom_components.irrigation_unlimited`), but only `black` runs in CI. There is no `mypy`/type-check step.

### Live dev instance (optional)

```bash
scripts/develop   # boots `hass --config ./config --debug` with custom_components on PYTHONPATH
```

This is for manual testing against a real HA, not part of the quality gate.

## Quality gate (must pass before declaring done)

These mirror `.github/workflows/pull.yml` (PRs) and `push.yml` (`master`/`dev`), which run the same four checks; `cron.yaml` runs the two validate-only checks nightly:

1. **Tests** — `pytest tests/` green (the bulk are timing/regression tests via the virtual-clock harness; see `tests/README.md`). The CI invocation adds `-n auto`, `--timeout=300` (pull) / `--timeout=600` (push, which also passes `--asyncio-mode=auto`), and `--cov`.
2. **Formatting** — `black .` clean.
3. **HACS validation** — CI runs `hacs/action@main` (`category: integration`, `ignore: brands`). Keep `hacs.json` + `manifest.json` valid.
4. **Hassfest validation** — CI runs `home-assistant/actions/hassfest`. Keep `manifest.json` well-formed (domain, version, requirements, dependencies, etc.).

Per `tests/README.md`: **don't change existing tests unless you're certain the expected result is wrong** — they exist for backward-compat. New functionality should add a test (use `tests/test_model.py` + `tests/configs/test_model.yaml` as the template).

## Conventions

- **`VERSION` lives in TWO places that must agree**: `manifest.json` `"version"` and `const.py` `VERSION`. Bump both together; HACS releases off the manifest version (calendar-versioned, e.g. `2025.12.0`).
- **No config flow** in this fork (`config_flow: false`). Configuration is the voluptuous `IRRIGATION_SCHEMA` under the `irrigation_unlimited:` YAML key. New config options = new `CONF_*` const + a schema entry in `schema.py` + plumbing in `irrigation_unlimited.py`.
- **Single platform**: `binary_sensor`. Entities are created in `binary_sensor.async_setup_platform` for every controller/zone/sequence.
- **Naming**: classes are `IU*` (PascalCase). All string keys go through a `const.py` constant — `CONF_*` (config), `SERVICE_*`, `ATTR_*` (entity attributes), `EVENT_*` (fired events), `STATUS_*`, `TIMELINE_*`. Don't inline raw strings; add/use a constant.
- **Logging**: module logger `_LOGGER = logging.getLogger(__package__)`; the startup banner is `STARTUP_MESSAGE` in `const.py`.

### The public surface = the contract with the card + ha-assets

**Entity IDs** (`binary_sensor.<DOMAIN>_<base>`):

| Entity | `unique_id` / base | Example entity_id |
|---|---|---|
| Controller (master) | `c{N}_m` | `binary_sensor.irrigation_unlimited_c1_m` |
| Zone | `c{N}_z{N}` | `binary_sensor.irrigation_unlimited_c1_z1` |
| Sequence | `c{N}_s{N}` | `binary_sensor.irrigation_unlimited_c1_s1` |

(Controller/zone indexes are 1-based in the entity id. `entity_base`/`rename_entities` config can override.)

**Attributes** (`extra_state_attributes` in `binary_sensor.py`, keys from `const.py` `ATTR_*`): e.g. `status`, `enabled`, `suspended`, `index`, `current_zone`/`current_schedule`/`current_name`/`current_start`/`current_duration`/`current_adjustment`, `next_*`, `time_remaining`, `percent_complete`, `adjustment`, `today_total`, `today_volume`, `volume`, `flow_rate`, `zone_count`/`sequence_count`/`schedule_count`, `sequence_status`, `timeline`, `configuration`, `zones`, `repeat`, `iu_id`. **The card reads many of these directly** (`current_adjustment`, `next_adjustment`, `timeline`, `adjustment`, …). Renaming/removing one is a breaking change for the card and any `ha-assets` template that reads it.

**Services** (declared in `const.py` `SERVICE_*`, registered in `service.py`, most described in `services.yaml`): `enable`, `disable`, `toggle`, `cancel`, `adjust_time`, `manual_run`, `suspend`, `skip`, `pause`, `resume`, `reload`, `load_schedule`, `get_info` (response-only), `get_status` (response-only). Entity-level services target a `binary_sensor.*` entity; `reload`/`load_schedule`/`get_info`/`get_status` are component-level (`irrigation_unlimited.<service>`). (`skip` is a sequence-only entity service — it's defined as `SERVICE_SKIP` and registered, but is **not** listed in `services.yaml`; the other twelve are.)

**Events** (`const.py` `EVENT_*`, fired on the HA bus): `start`, `finish`, `incomplete`, `valve_on`, `valve_off`, `switch_error`, `sync_error`. `ha-assets` automations may listen for these.

## Where things live

The integration is a single Python package under `custom_components/irrigation_unlimited/`:

```
custom_components/irrigation_unlimited/
├── manifest.json            # HA integration manifest (domain, version, deps, requirements)
├── __init__.py              # async_setup(): YAML setup, builds IUCoordinator, loads binary_sensor platform, registers component services
├── const.py                 # ALL constants: DOMAIN, CONF_*, SERVICE_*, ATTR_*, EVENT_*, STATUS_*, TIMELINE_*, ICON_*, VERSION
├── schema.py                # voluptuous schemas: IRRIGATION_SCHEMA (top-level config) + per-service schemas
├── irrigation_unlimited.py  # THE engine (~250KB): IUCoordinator, IUController, IUZone, IUSequence, runs, scheduling, volume/flow, timeline
├── entity.py                # IUEntity base + IUComponent (the domain component entity) + service dispatch
├── binary_sensor.py         # the ONLY platform: IUMasterEntity / IUZoneEntity / IUSequenceEntity + their extra_state_attributes
├── service.py               # registers entity-level + component-level services (the HA service surface)
├── history.py               # recorder/history integration (volume, flow rate, timeline collection)
├── util.py                  # small helpers (e.g. convert_data for service responses)
├── services.yaml            # HA service descriptors (names, fields, selectors) — the user-facing service UI
└── translations/en.json     # UI strings (en only)
```

Around the package, the repo root also holds `tests/` (the virtual-clock harness + `tests/README.md`), `scripts/` (`setup`/`develop` for a live HA dev instance), `examples/` and `lovelace/` (sample YAML configs + cards), `requirements.txt` / `requirements_test.txt`, `pytest.ini`, `setup.cfg` (flake8 + isort), `hacs.json`, and the `.github/workflows/` (`pull.yml`, `push.yml`, `cron.yaml`).

## Adding / changing a feature — walkthrough

The chain depends on what you're touching; the cross-repo step (5) is the one that bites.

**Adding/changing a service:**
1. Add `SERVICE_<NAME>` to `const.py` (+ any `CONF_*`/`ATTR_*` it needs).
2. Add the voluptuous schema in `schema.py`.
3. Register it in `service.py` (`register_platform_services` for entity-level, `register_component_services` for component-level). Implement the handler / dispatch (often in `irrigation_unlimited.py` via `coordinator.service_call` or the entity `dispatch`).
4. Describe it in `services.yaml` (name, description, fields, selectors) — this is the user-facing service UI in HA.
5. **Cross-repo**: if the card or `ha-assets` should call it, update `irrigation-unlimited-card` and/or `ha-assets`. Conversely, never silently change a service's name/fields the card already calls.
6. Add a test under `tests/` (model after `tests/test_service.py` / `tests/test_model.py`), then run the quality gate.

**Adding/changing an entity attribute:**
1. Add `ATTR_<NAME>` to `const.py`.
2. Compute it on the right class in `irrigation_unlimited.py` (controller/zone/sequence) and surface it in the matching `extra_state_attributes` in `binary_sensor.py`.
3. **Cross-repo**: if the card or an `ha-assets` template/dashboard should display it, update them. Removing/renaming an existing attribute is breaking.
4. Add/extend a test; run the quality gate.

**Bumping the release** (HACS): bump `manifest.json` `version` **and** `const.py` `VERSION` together (calendar version), keep them equal.

## Ripple awareness (the integration ↔ card ↔ ha-assets contract)

- **`irrigation_unlimited` ↔ `irrigation-unlimited-card`** are a backend/frontend pair built around the entity-attribute + service contract above. The card reads attributes (`timeline`, `current_adjustment`, `next_adjustment`, `adjustment`, status, etc.) and calls services (`adjust_time`, `enable`, `disable`, `manual_run`, …). Any change to attribute names/shapes, the `timeline` item shape, entity-id format, or service field names/selectors must be mirrored in the card. Check the card before declaring an entity/service/attribute change done.
- **`ha-assets`** consumes this integration's entities/attributes/services/events in dashboards, `packages/`, template sensors, and automations. Renaming an entity, attribute, service, or event can break those dashboards silently (no compile error — just empty cards or dead automations). The repo's own `tests/README.md` warns the integration runs on a virtual clock but `recorder`/`history` log in real time.
- **HACS distribution**: both this integration and the card are distributed via HACS. Respect calendar-version release discipline (keep `manifest.json`/`const.py` versions in lockstep) so HACS surfaces the update.

See also `home-assistant/AGENTS.md` (group-level ripple notes) one directory up.

## When stuck

- **HA integration mechanics** (manifest, platforms, services, entities): Home Assistant developer docs — https://developers.home-assistant.io/ .
- **This integration's behavior / config options**: the repo `README.md` (large, authoritative) and `info.md`; `examples/` (full YAML configs like `all_the_bells_and_whistles.yaml`) and `lovelace/` (sample cards).
- **Test framework** (`IUExam`, virtual clock, result objects): `tests/README.md` and `tests/iu_test_support.py`; template `tests/test_model.py` + `tests/configs/test_model.yaml`.
- **The card contract**: the sibling `home-assistant/irrigation-unlimited-card` (`src/irrigation-unlimited-card.ts`).
- **Upstream comparison**: `rgc99/irrigation_unlimited` (no git remote configured here — add one to diff).
