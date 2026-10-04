# Offline math runtime

- Package: `mathjax` 3.2.2, https://www.npmjs.com/package/mathjax/v/3.2.2
- Artifact: unmodified `package/es5/tex-svg.js` from the pinned npm tarball.
- SHA-256: `d4295dc33744836935c1399feece5159577b34c5c8ffb9f1c6324cd82e03a882`
- License: Apache License 2.0, retained as `LICENSE`.
- Upstream: https://github.com/mathjax/MathJax

Only this prebuilt SVG runtime is bundled. Its base/AMS/newcommand/configmacros
packages and SVG font data operate offline. The publication disables automatic
extension loading and the menu (which otherwise loads additional components).
No package retrieval happens when generating or reading user publications.
