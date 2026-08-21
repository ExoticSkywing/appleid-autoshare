# Apple ID AutoShare — Product Context

## Product truth

A Chinese, mobile-first access relay that helps a nontechnical visitor obtain one shared Apple ID that can log into the App Store and download Shadowrocket. The service reveals one credential at a time, uses the visitor’s real result as quality feedback, and keeps trying until the target is reached or the visitor chooses a paid dedicated account.

## Audience and situation

- A visitor usually arrives from a phone and may switch repeatedly between the browser and App Store.
- They may not understand Apple ID mechanics, browser sessions, verification widgets, or error categories.
- They are impatient, wary of unsafe login instructions, and likely to abandon after repeated failures.
- The interface must keep the current credential and progress intact when the page is backgrounded and reopened.

## Success and evidence

The target is not “receive an account.” The target is: **the account signs in and the visitor can obtain Shadowrocket**.

Front-end result language is fixed:

1. **成功达成目标** — account can sign in and Shadowrocket is available. Submit feedback and end the flow.
2. **没能达成目标** — account can sign in but Shadowrocket is unavailable. Submit feedback and automatically reveal another account.
3. **登录不上** — sign-in fails, password is rejected, or verification blocks access. Submit feedback and automatically reveal another account.

The completion proof is an explicit final state: “目标已达成”. It must not expose the password in the completion receipt.

## Fallback conversion

A visitor may stop trying at any time. The backend returns the configured HTTPS store URL with every reveal response. The frontend never hard-codes it. The purchase route becomes the primary action when the account pool is exhausted and remains a quiet secondary exit while an account is available.

## Safety boundary

The interface must permanently communicate: only sign in inside the App Store; never sign in to iCloud or iPhone Settings. Credentials are sensitive and must never be placed in query strings, analytics, logs, or browser-persistent storage.

## Interaction priority

Task completion > state certainty > error recovery > reading load > decoration.

- One account only; no browsing a list.
- Account and password have separate, large one-tap copy controls with persistent copied evidence.
- Verification, reveal, feedback, replacement, exhaustion, and completion are distinct visible states.
- Errors identify the failed operation and offer a direct retry.
- Page backgrounding must not reset the live state.
- Reduced motion removes the ceremonial movement but preserves every state cue.

## Visual authority

**Access Relay**: a restrained, dark precision instrument. A smoked credential plate resolves from shadow during the rare reveal moment; a narrow scanner line and status lock communicate readiness. Once credentials appear, theatrical effects withdraw and the surface serves copying and feedback.

Use true black, graphite, titanium, smoked translucent surfaces, cool white text, and low-saturation semantic status color. Avoid cyberpunk neon, casinos, games, hacker-console costume, random particles, confetti, decorative glass-card stacks, and WebGL unless later evidence proves it materially improves the task.

## Platform and delivery

- Static HTML, CSS, and dependency-free JavaScript served by the existing FastAPI app.
- Primary target: mobile Safari/WebKit; must also pass Firefox and desktop Chromium.
- No external font dependency in the critical path.
- Respect safe areas, 200% zoom, 320px reflow, keyboard navigation, and `prefers-reduced-motion`.
