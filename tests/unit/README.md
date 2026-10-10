# Unit test discovery

Run the supported unit suite from the repository root with:

```bash
python3 -m unittest discover -s tests/unit -p "test_*.py" -t .
```

The `-t .` argument keeps the repository root on `sys.path`, so the relocated
modules resolve the `transport.server` namespace package deterministically. The
usual entry point is `tests/run.sh --unit`.

## Shell unit tests

Some unit tests are shell scripts rather than pytest modules (they exercise the
container admission shell scripts directly) and are not discovered by pytest.
`tests/run.sh --unit` runs them alongside the pytest suite. Run one directly
with `bash tests/unit/<name>.sh`.

- `test_maildeliver.sh` — verifies recipient BASE validation in
  `crews/_base/admission/maildeliver` and `sendmail-local`: valid persona
  addresses deliver and exit 0, while path-traversal and other malformed
  recipients are rejected with exit 1 and write no files (trn-217).
