# Design: isolated unknown-error recovery

## State model

`state.unknownErrorStage` is one of `""`, `"video"`, or `"fallback"` and is persisted with the current account session. It is orthogonal to `resultsVisible` and never changes `feedbackLocked` or `loginSucceeded`.

- `""`: existing result choice view; three entry actions are available.
- `"video"`: inline recovery article with the supplied video, retry-success action, and abandon action.
- `"fallback"`: dedicated-account bottom sheet; existing result view remains the owner behind it.

The paid path is a user-selected escape from the recovery branch, not a third result answer and not a replacement outcome.

## DOM topology

Inside `#feedbackPanel`:

1. `#resultActions` evidence + three free/result actions.
2. `#unknownErrorRecovery` video state, sibling to `#resultActions`.

Outside the task panel, as existing overlay siblings:

- `#dedicatedFallbackActionSheet` — first paid-choice sheet.
- `#dedicatedContactActionSheet` — lower-right Chatwoot handoff sheet.
- existing `#benefitModal` remains the rights comparison modal.

The comparison modal is closed before the fallback sheet is restored; overlays never stack.

## Event contracts

- Unknown button: `showUnknownErrorRecovery()`; no `/feedback` call.
- Recovery success: `handleLoginSuccessResult()` is the sole success action shared by the original green button and the video branch.
- Abandon: `openDedicatedFallbackSheet()`; no account feedback and no `revealOne()`.
- Rights comparison: temporarily close fallback sheet, call existing `openBenefitModal()`, then reopen fallback on close.
- Get dedicated: close fallback and open contact sheet; no external purchase navigation.
- Contact `好的`: close contact sheet, call existing `returnHome()`, and announce that the homepage is ready for customer contact. It must not say login/purchase succeeded.

## Focus and support-widget contract

All sheets use the existing bottom-sheet focus/inert pattern. The support widget is hidden while either sheet is open. After contact confirmation, the page reloads to the homepage and Chatwoot is available in its normal lower-right position. The current result-state CSS hiding rule is narrowed so the widget can be seen after a sheet closes only on the new homepage; no existing result-state widget behavior is changed.

## Visual contract

Use the existing graphite surfaces. The third result action gets a localized low-saturation orange warning icon/border, not a bright full-card orange fill. The video content stays compact and normal-flow. The paid sheet has one dominant action (`获取独享账号`) and a quieter rights-comparison action. No pulse, glow, autoplay, or sticky conversion bar is added.
