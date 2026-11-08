# Implementation plan

1. Add the supplied MP4 under `static/assets/` and update the result markup with the isolated warning action, video recovery state, fallback sheet, and contact sheet.
2. Extend `state`, session restore/save, result rendering, and overlay handlers. Share the original login-success handler between the green result action and video recovery success.
3. Add scoped theme rules for warning result state, video layout, fallback/contact sheets, and mobile overflow/reduced-motion behavior. Bump cache versions.
4. Add focused WebKit/Firefox probes covering initial three-action result, video branch, fallback sheet, rights return, contact handoff, homepage reset, focus, media controls, and overflow.
5. Build Docker, read back live assets, run focused tests and relevant existing tests, inspect screenshots, then commit/push only after the artifact is verified.
