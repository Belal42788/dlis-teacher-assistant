# DLIS family app for Android

The parents' and students' portal (`portal/`) packed as an Android app, so families get an app icon and a full-screen app
instead of a web page. There is no second copy of the portal: the build copies `portal/` into `www/` and wraps it.

Build it: GitHub -> Actions -> **Build Android app** -> Run workflow. When it is green, open the run and download the
artifact **DLIS-Android-APK** (a zip with `app-debug.apk`). Copy the APK to a phone and open it (Android asks once to allow
installing from this source). To update the app, build again and install the new APK over the old one.

Nothing private is inside: the portal's `config.js` only holds the school server's public address and public key.
