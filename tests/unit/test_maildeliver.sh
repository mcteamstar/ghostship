#!/usr/bin/env bash
# test_maildeliver.sh — verify recipient BASE validation in maildeliver and
# sendmail-local (trn-217 path-traversal fix).
#
# Strategy: run the real scripts against a sandbox so no real /var/mail is
# touched. We point delivery at a temp dir by overriding the mail root via a
# wrapper copy of each script with /var/mail/ rewritten to $MAILROOT, so valid
# addresses actually create files and invalid ones must create nothing.
#
# Each script is tested for:
#   - valid addresses  -> exit 0 (and, for valid, a file is delivered)
#   - invalid addresses -> exit 1 and NOTHING written outside the mail root
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
MAILDELIVER_SRC="$REPO_DIR/crews/_base/admission/maildeliver"
SENDMAIL_SRC="$REPO_DIR/crews/_base/admission/sendmail-local"

if [[ ! -f "$MAILDELIVER_SRC" || ! -f "$SENDMAIL_SRC" ]]; then
    echo "FAIL: cannot locate scripts under $REPO_DIR/crews/_base/admission/" >&2
    exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Sandbox layout:
#   $WORK/bin   — sandboxed copies of the scripts under test
#   $WORK/root  — stands in for the filesystem root the scripts write under;
#                 $MAILROOT ($WORK/root/var/mail) is the legitimate mail root,
#                 anything else under $WORK/root is a traversal escape.
mkdir -p "$WORK/bin"
MAILROOT="$WORK/root/var/mail"
mkdir -p "$MAILROOT"

# Build sandboxed copies with /var/mail/ redirected into the sandbox and the
# maildeliver path in sendmail-local pointed at our sandboxed maildeliver.
MAILDELIVER="$WORK/bin/maildeliver"
SENDMAIL="$WORK/bin/sendmail-local"
sed "s#/var/mail/#$MAILROOT/#g" "$MAILDELIVER_SRC" > "$MAILDELIVER"
sed -e "s#/var/mail/#$MAILROOT/#g" \
    -e "s#/usr/local/bin/maildeliver#$MAILDELIVER#g" \
    "$SENDMAIL_SRC" > "$SENDMAIL"
chmod +x "$MAILDELIVER" "$SENDMAIL"

PASS=0
FAIL=0

# count files anywhere under the sandbox mail root
mail_file_count() {
    find "$MAILROOT" -type f 2>/dev/null | wc -l | tr -d ' '
}

# count files written under the sandbox fs-root but OUTSIDE the mail root — a
# path-traversal escape would land here (e.g. $WORK/root/tmp/x). The script
# copies live under $WORK/bin and are deliberately excluded.
escaped_file_count() {
    find "$WORK/root" -type f -not -path "$MAILROOT/*" 2>/dev/null | wc -l | tr -d ' '
}

reset_sandbox() {
    rm -rf "$WORK/root"
    mkdir -p "$MAILROOT"
}

# assert_valid <script> <address>  -> expects exit 0 and >=1 delivered file
assert_valid() {
    local script="$1" addr="$2"
    reset_sandbox
    if echo "test body" | "$script" "$addr" >/dev/null 2>&1; then
        local n
        n="$(mail_file_count)"
        if [[ "$n" -ge 1 ]]; then
            echo "PASS: $(basename "$script") accepted valid '$addr' (delivered $n file)"
            PASS=$((PASS + 1))
        else
            echo "FAIL: $(basename "$script") exit 0 for '$addr' but delivered no file" >&2
            FAIL=$((FAIL + 1))
        fi
    else
        echo "FAIL: $(basename "$script") rejected valid '$addr' (expected exit 0)" >&2
        FAIL=$((FAIL + 1))
    fi
}

# assert_invalid <script> <address> -> expects exit 1 and zero files written
assert_invalid() {
    local script="$1" addr="$2"
    reset_sandbox
    local rc=0
    echo "test body" | "$script" "$addr" >/dev/null 2>&1 || rc=$?
    local total escaped
    total="$(mail_file_count)"
    escaped="$(escaped_file_count)"
    if [[ "$rc" -ne 0 && "$total" -eq 0 && "$escaped" -eq 0 ]]; then
        echo "PASS: $(basename "$script") rejected invalid '$addr' (exit $rc, no files)"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $(basename "$script") mishandled invalid '$addr' (exit=$rc files=$total escaped=$escaped)" >&2
        FAIL=$((FAIL + 1))
    fi
}

echo "=== maildeliver: valid addresses ==="
assert_valid "$MAILDELIVER" "ghost@localhost"
assert_valid "$MAILDELIVER" "ghost+abc@localhost"
assert_valid "$MAILDELIVER" "raven@localhost"

echo "=== maildeliver: invalid addresses ==="
assert_invalid "$MAILDELIVER" "../../tmp/x@localhost"
assert_invalid "$MAILDELIVER" "../etc/passwd@localhost"
assert_invalid "$MAILDELIVER" "@localhost"
assert_invalid "$MAILDELIVER" "Ghost@localhost"
assert_invalid "$MAILDELIVER" "ghost @localhost"

# Task 3.2 — sendmail-local must also reject path-traversal addresses and
# accept valid ones (defense-in-depth before delegating to maildeliver).
echo "=== sendmail-local: valid addresses ==="
assert_valid "$SENDMAIL" "raven@localhost"
assert_valid "$SENDMAIL" "ghost+task123@localhost"

echo "=== sendmail-local: invalid addresses ==="
assert_invalid "$SENDMAIL" "../../tmp/evil@localhost"
assert_invalid "$SENDMAIL" "../etc/passwd@localhost"
assert_invalid "$SENDMAIL" "@localhost"
assert_invalid "$SENDMAIL" "Ghost@localhost"

echo
echo "=== Summary: $PASS passed, $FAIL failed ==="
if [[ "$FAIL" -ne 0 ]]; then
    exit 1
fi
exit 0
