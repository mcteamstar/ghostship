## 1. Wire env var in config.py

- [x] 1.1 In `transport/config.py` `from_env()`, replace the hardcoded `ga_dashboard_port_range_size=1024` with `ga_dashboard_port_range_size=_env_int("GA_DASHBOARD_PORT_RANGE_SIZE", "1024")`

## 2. Update example config

- [x] 2.1 Add a commented `GA_DASHBOARD_PORT_RANGE_SIZE=1024` entry to `config/ghostship.conf.example`, directly below the existing `GA_DASHBOARD_PORT_RANGE_START` entry

## 3. Add unit test

- [x] 3.1 In `tests/unit/test_config_from_env.py`, add a test asserting `Config.from_env()` with `GA_DASHBOARD_PORT_RANGE_SIZE=50` returns `cfg.ga_dashboard_port_range_size == 50`
- [x] 3.2 Add a test asserting the default value `1024` is used when `GA_DASHBOARD_PORT_RANGE_SIZE` is unset

## 4. Verify

- [x] 4.1 Run `python -m pytest tests/unit/ -x -q` and confirm all tests pass
- [x] 4.2 Confirm `openspec validate --change trn-180-dashboard-port-range-size-config` passes
