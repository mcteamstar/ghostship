# Unit test discovery

Run the supported unit suite from the repository root with:

```bash
python3 -m unittest discover -s tests/unit -p "test_*.py" -t .
```

The `-t .` argument keeps the repository root on `sys.path`, so the relocated
modules resolve the `transport.server` namespace package deterministically. The
usual entry point is `tests/run.sh --unit`.
