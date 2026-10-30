#!/bin/sh
# The browser file is i18n.js; Node needs .mjs, so we check a temporary copy.
cd "$(dirname "$0")/.." || exit 1
cp app/web/js/i18n.js app/web/js/i18n.mjs
node scripts/check_i18n.mjs; code=$?
rm -f app/web/js/i18n.mjs
exit $code
