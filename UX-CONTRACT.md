# NutriOS — UX Contract

This contract defines observable behavior across authenticated product routes.

## Session and errors
1. 401: session is absent/expired. Redirect to `/login` and preserve a safe return target when supported.
2. 403: do not redirect. Render an in-context permission state.
3. 408/429/5xx/network: do not redirect. Preserve the App Shell and user input where safe; render retry.
4. Error messages describe the failed action and the next step; avoid generic “algo deu errado” when a useful distinction is known.

## Async states
Every data surface has four explicit states: loading, success, empty and error. Refreshing existing data must not erase usable content unless stale content would be unsafe.

## Navigation
The professional App Shell remains mounted/visually stable across professional modules. The current module is visibly selected. Back navigation inside a workflow returns to the logical parent, not an arbitrary dashboard.

## Forms
Labels remain visible; placeholders are examples, not labels. Validation is adjacent to the field and preserves entered values. Save buttons communicate progress and success. Duplicate submission is prevented for consequential writes.

## Clinical actions
AI-generated summaries/plans are drafts until a clinician explicitly accepts/publishes them. Clinical records and documents expose authorization failures without leaking cross-tenant existence or metadata.

## Financial actions
Currency is formatted in pt-BR/BRL. Destructive or irreversible financial changes require confirmation and explain their consequence.

## Empty states
An empty state contains: what is empty, why it matters when relevant, and one primary next action when an action exists.

## Accessibility
Visible focus, semantic controls, keyboard-operable navigation/modals, sufficient contrast, 44px-class touch targets for primary mobile actions, reduced motion support and meaningful accessible names for icon-only controls.

## Responsive
Mobile prioritizes urgent clinical context and primary actions. Secondary analytics may collapse behind disclosure, but functionality cannot disappear solely because of viewport size.
