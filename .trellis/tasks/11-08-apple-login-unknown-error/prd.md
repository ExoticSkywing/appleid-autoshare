# Apple login unknown error recovery and dedicated account fallback

## Goal
Give the newly observed Apple temporary-risk / unknown-error case its own path. Do not classify it as a bad shared account and do not send it through account replacement. Help the user retry from the supplied video, reconnect a successful retry to the existing login-success path, and offer a paid dedicated Apple ID + Shadowrocket fallback only when the user explicitly gives up.

## Requirements

- Keep the existing success result and shared-account replacement result as separate actions.
- Add a third, warning-styled result action for `验证失败 / 发生未知错误`.
- The warning action opens an in-flow video recovery state, preserving the current account and result context.
- Use the supplied tutorial video as a user-controlled, inline, `playsinline` video; do not autoplay or force full-screen.
- Recovery success must reuse the original success behavior, not create a second success implementation.
- Recovery abandonment must not call shared-account replacement or record login success. It opens a dedicated-account fallback sheet.
- The fallback sheet must explain the dedicated non-shared Apple ID with purchased Shadowrocket as a paid alternative, with calm urgency and no unsupported absolute promise.
- The fallback sheet has two distinct actions: reuse the existing rights-comparison surface, and open a second guidance sheet for obtaining the dedicated account through the lower-right customer widget.
- The rights comparison must return to the fallback sheet rather than stack two overlays.
- The customer guidance sheet must explicitly point to the lower-right customer widget. Its `好的` action ends this attempt and returns to the homepage without claiming login or purchase success.
- Preserve the existing store banner, external-link icon, account replacement flow, sign-out gate, Chatwoot parameters, and target-app completion flow.
- Under 320px/393px, no horizontal overflow, isolated controls remain keyboard reachable, dialogs trap focus and restore focus where appropriate, and reduced motion does not remove the actions.

## Copy contract

- Result warning: `验证失败 / 发生未知错误` with supporting copy `这是 Apple 的临时验证异常，不是换号入口`.
- Video heading: `遇到未知错误，先按视频重试`.
- Video instruction: `按视频关闭错误提示，再回到登录页点击“继续”重试。完成后务必回到这里。`
- Recovery success: `已显示账号，继续` / `仅限 App Store 已显示左图账号`.
- Recovery abandon: `放弃重试，开启专享备用方案` / `非共享 Apple ID · 已购小火箭`.
- Fallback sheet: `不用再反复尝试，换用自己的小火箭账号`.
- Contact sheet: `点击右下角客服，获取独享账号`; `好的`.

## Acceptance Criteria

- [x] Clean novice result state exposes exactly three result actions with distinct semantics.
- [x] Clicking unknown error hides the result-choice group and shows the video recovery state; no feedback request or replacement request is made.
- [x] Video success action follows the same code path as the original success action.
- [x] Abandon action opens the fallback sheet and leaves the shared account untouched.
- [x] Rights comparison opens the existing comparison modal and closes back to the fallback sheet.
- [x] Get dedicated account opens the customer guidance sheet; `好的` clears the session and returns to `/`.
- [x] Restored sessions converge on result, video, and fallback states without exposing stale store CTAs.
- [x] WebKit and Firefox probes at 393px and 320px pass visibility, focus, overflow, no-console-error, and video-control checks.
- [x] Docker build, health, and live asset/version readback pass.
