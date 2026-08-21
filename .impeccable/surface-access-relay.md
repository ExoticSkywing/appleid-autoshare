# Surface Brief — Access Relay

## Approved composition

Fusion of `.impeccable/mocks/access-relay-a-monolith.png` and `.impeccable/mocks/access-relay-c-archive.png`: A owns the single dominant credential stage and thumb-zone primary action; C owns the archive/handoff transition after an unsuccessful result.

## Direction contract

The page behaves as a restrained access instrument, not a dashboard, landing page, game, or fake terminal. True black surrounds one smoked graphite credential slab. Hairline titanium seams, clipped corners and controlled edge reflections create precision without literal hardware screws. Before reveal, the slab is an inert relay aperture with one explicit “获取账号” action and a visible Turnstile gate. After reveal, the same footprint becomes the credential: Apple ID and password each have a full-width, 44px-plus copy lane with local copied state. The account never arrives as a list. For unsuccessful feedback, the current slab translates into a thin retired edge and the next credential enters from the archive direction; after success, motion stops and the slab resolves into a calm confirmed state. Semantic color is tiny and status-bound. The permanent safety rule remains the most visible supporting line. Mobile has one vertical focal path; desktop widens negative space rather than adding panels.

## Artifact inventory

| Region | Composition commitment | Medium |
|---|---|---|
| Ambient field | true black, restrained radial light, no decorative grid | CSS |
| Safety notice | permanent and high contrast, no modal | semantic HTML/CSS |
| Credential slab | one dominant smoked graphite shape, clipped corner, hairline seams | semantic HTML/CSS pseudo-elements |
| Scanner | one narrow authored reveal/handoff moment | CSS animation |
| Copy controls | explicit text + consistent authored inline icon, >=44px | HTML + authored SVG geometry |
| Archive edge | at most one thin retired edge, never readable | CSS pseudo-element |
| Result deck | three horizontal controls; secondary two promise automatic replacement | semantic buttons |
| Store exit | quiet before exhaustion, primary when exhausted | API-provided anchor |
| Turnstile | visible official widget with explicit continuation action | third-party widget + HTML button |
| Success proof | stable completed status, no confetti | HTML/CSS |

No raster or generated asset is required for production. The generated comps are art-direction evidence only and must not be shipped. Do not use the Apple logo, screws, radar reticle, faux ventilation, fake terminal decoration, neon glow, card stacks, or particles.

## Responsive / interaction contract

- 320px through desktop; mobile first. Desktop keeps the same single task column with optional side note only if it improves comprehension.
- Honor `prefers-reduced-motion`; replacement remains understandable without animation.
- Preserve current account and copy progress across App switching / reload only for the active browser session; never persist credentials beyond `sessionStorage`. Clear on success or exhaustion.
- Clipboard fallback selects/copies text when Clipboard API fails. Each copy action owns its success/error feedback.
- Network errors do not discard the current credential. Feedback retries target the same result.
- Success does not fetch another ticket/account. Only `shadowrocket_missing` and `login_failed` do.
- `purchase_link` comes from every successful reveal payload and is never hardcoded.
