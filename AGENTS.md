# Agent guide — irrigation_unlimited

Primary agent guide for this repo. No nested `AGENTS.md` files — the integration is a single Python package; everything lives here.

## What this is

A **Home Assistant custom integration** (Python, distributed via **HACS**) that provides flexible irrigation scheduling. Domain: **`irrigation_unlimited`**. It models a hierarchy of **controllers → zones / sequences → schedules**, drives switch entities on a virtual clock, and exposes a rich service + attribute surface. `iot_class: local_polling`, no cloud.

It is one half of a **backend/frontend pair**:

- **`irrigation-unlimited-card`** — the Lovelace card that visualizes/controls this integration (reads its **entity attributes**, calls its **services**).
- **`ha-assets`** — the live HA config; dashboards, `packages/`, automations and template sensors consume the **entities, attributes, services and events**.

A shape change here usually needs a matching card change and can silently break `ha-assets`. See **Ripple awareness**.

### Fork status (important)

Fork of the upstream HACS integration **`rgc99/irrigation_unlimited`** (`manifest.json`/`const.py` still point `documentation`/`issue_tracker`/`codeowners` at `rgc99`). Intentional local divergence:

- The **`interleave`** config option (`CONF_INTERLEAVE`, parallel zone scheduling).
- **`config_flow: false`** — YAML-configured only (`IRRIGATION_SCHEMA` under the `irrigation_unlimited:` key); upstream has a UI config flow.

Keep parity with upstream where practical; when pulling upstream, re-check neither gets clobbered. No `upstream` git remote is configured — add one to diff.

## How to run things

No tox/nox/Makefile/pre-commit — a venv + the requirements files (`scripts/setup` / `scripts/develop` run a live HA dev instance, not tests).

```bash
python3 -m venv venv && source venv/bin/activate && pip3 install -r requirements_test.txt
pytest tests/                                   # pytest.ini: testpaths=tests, asyncio_mode=auto, --cov
pytest -qq --timeout=300 --durations=10 -n auto --cov custom_components.irrigation_unlimited \
  -o console_output_style=count -p no:sugar tests   # CI-equivalent (.github/workflows/pull.yml)
pytest tests/test_service.py -k test_service_adjust_time
black .                                         # the only linter CI runs
scripts/develop                                 # optional: hass --config ./config --debug
```

`requirements_test.txt` pins `pytest-homeassistant-custom-component==0.13.222`; CI tests on **Python 3.13**. `setup.cfg` configures flake8/isort too, but only `black` runs in CI; no mypy.

## Quality gate

Mirrors `.github/workflows/pull.yml` (PRs) and `push.yml` (`master`/`dev`); `cron.yaml` runs the two validations nightly:

1. **Tests** — `pytest tests/` green (mostly timing/regression tests on the virtual-clock harness; `tests/README.md`).
2. **Formatting** — `black .` clean.
3. **HACS validation** — `hacs/action@main` (`category: integration`, `ignore: brands`): keep `hacs.json` + `manifest.json` valid.
4. **Hassfest** — the official `hassfest` GitHub Action: keep `manifest.json` well-formed.

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

Repo root: `tests/` (virtual-clock harness + `tests/README.md`), `scripts/`, `examples/` + `lovelace/` (sample configs + cards), `packages/` + `pyscript/`, `pytest.ini`, `setup.cfg`, `hacs.json`, `.github/workflows/`.

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

## Ripple awareness

Open the other side before declaring a contract change done.

- **`irrigation-unlimited-card`** — github.com/nantomarioni/irrigation-unlimited-card — expected at `../irrigation-unlimited-card`. Backend/frontend pair around the surface above: the card (`src/irrigation-unlimited-card.ts`) reads attributes (`timeline`, `current_adjustment`, `next_adjustment`, `adjustment`, status…) and calls services (`adjust_time`, `enable`, `disable`, `manual_run`, …). Attribute names/shapes, the `timeline` item shape, the entity-id format and service field names/selectors must be mirrored there.
- **`ha-assets`** — github.com/nantomarioni/ha-assets — expected at `../ha-assets`. Consumes entities/attributes in dashboards and its own `cards/irrigation-status` + `cards/irrigation-config`, and `automations/swv.yaml` listens for the **`irrigation_unlimited_valve_on`** event (fields `entity_id`, `duration`) to drive Zigbee valves. Renames break it silently (empty cards, dead automations). Verified against `2025.12.0`.
- **HACS**: both repos release by calendar version; keep `manifest.json`/`const.py` in lockstep so HACS surfaces the update.

## When stuck

- **HA integration mechanics** (manifest, platforms, services, entities): Home Assistant developer docs — https://developers.home-assistant.io/ .
- **This integration's behavior / config options**: the repo `README.md` (large, authoritative) and `info.md`; `examples/` (full YAML configs like `all_the_bells_and_whistles.yaml`) and `lovelace/` (sample cards).
- **Test framework** (`IUExam`, virtual clock, result objects): `tests/README.md` and `tests/iu_test_support.py`; template `tests/test_model.py` + `tests/configs/test_model.yaml`.
- **The card contract**: `../irrigation-unlimited-card/src/irrigation-unlimited-card.ts`.
- **Upstream comparison**: `rgc99/irrigation_unlimited` (no git remote configured here — add one to diff).
