# Vendored JavaScript

Served locally so the app makes no third-party requests and works offline. Copied
unmodified from the npm tarballs, which were checked against the registry's `integrity`
hashes before extracting.

| File | Package | License |
| --- | --- | --- |
| `chart.umd.min.js` | chart.js 4.5.1, `dist/chart.umd.min.js` (`sha512-GIjfiT9dbmHRiYi6Nl2yFCq7kkwdkp1W/lp2J99rX0yo9tgJGn3lKQATztIjb5tVtevcBtIdICNWqlq5+E8/Pw==`) | MIT, `chart.js-LICENSE.md` |
| `chartjs-adapter-date-fns.bundle.min.js` | chartjs-adapter-date-fns 3.0.0, `dist/chartjs-adapter-date-fns.bundle.min.js` (`sha512-Rs3iEB3Q5pJ973J93OBTpnP7qoGwvq3nUnoMdtxO+9aoJof7UFcRbWcIDteXuYd1fgAvct/32T9qaLyLuZVwCg==`) | MIT, `chartjs-adapter-date-fns-LICENSE.md`. The bundle includes date-fns, also MIT. |

To update: download the new tarballs from `https://registry.npmjs.org/<package>/latest`,
verify each against its `dist.integrity`, copy the same files, and update this table.
