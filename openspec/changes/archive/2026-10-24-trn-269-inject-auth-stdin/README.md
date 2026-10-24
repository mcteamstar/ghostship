# trn-269-inject-auth-stdin

Switch inject_auth.py to read the kiro-cli auth payload from stdin instead of argv, closing the /proc/pid/cmdline exposure gap for kiro SQLite row data.
