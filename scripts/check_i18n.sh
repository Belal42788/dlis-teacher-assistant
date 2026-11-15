#!/bin/sh
# The browser files are i18n_en.js / i18n_ar.js; Node needs .mjs, so we check temporary copies.
cd "$(dirname "$0")/.." || exit 1
for l in en ar; do cp app/web/js/i18n_$l.js app/web/js/i18n_$l.mjs; done
node scripts/check_i18n.mjs; code=$?
rm -f app/web/js/i18n_en.mjs app/web/js/i18n_ar.mjs
exit $code
