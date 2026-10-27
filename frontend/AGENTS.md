<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

## Air Point architecture
- Keep engine demo state in a shared typed React provider, separate from presentation, so Python integration can replace mock values without changing screens.
- Use individual TanStack content routes within a shared desktop shell; Overview lives at `/` and selection deep-links to the gesture route through validated search state.
- Keep original gesture illustrations as browser-safe SVG components, so the technical visual family stays consistent and portable to a native UI.
- All system actions remain local simulations without services, persistence, or invented bridge protocols; the existing Python engine owns real Windows behavior.
- Bundle UI fonts through local Fontsource CSS imports in the global stylesheet so rendering does not depend on a third-party font service.
