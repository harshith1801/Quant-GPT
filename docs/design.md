# Quant GPT: the evidence desk

## Focused reference study

Reviewed October 2, 2026, before implementation:

- [Linear, March 2026 interface refresh](https://linear.app/now/behind-the-latest-design-refresh): receding navigation, predictable structure and carefully controlled contrast. Inspected the actual interface comparison images in the browser.
- [Linear's redesign process](https://linear.app/now/how-we-redesigned-the-linear-ui): density, hierarchy and state coverage matter more than isolated screens.
- [Raycast](https://www.raycast.com/): a persistent, keyboard-first command entry and visible task progress.
- [Robinhood Legend](https://robinhood.com/us/en/support/articles/get-started-with-robinhood-legend/): contextual market inspection and linked workspace interactions. We do not copy a trading layout or add order entry.
- [TradingView Lightweight Charts](https://www.tradingview.com/lightweight-charts/): chart behavior, crosshair precision and responsive rendering.
- [Community critique of generic AI dashboards](https://uxskill.laithjunaidy.com/blog/ai-dashboard-design-generic.html) and [repeated AI interface patterns](https://docs.bswen.com/blog/2026-03-20-ai-generated-ui-anti-patterns/): avoid equal-weight card grids, decorative gradients and oversized landing-page spacing in research tools.

The design borrows principles rather than layouts. Godly was also attempted but inaccessible during the study.

## Identity

A cut-square Q with intersecting coordinate strokes. The cross recurs in source links and section labels; four short signal bars indicate analysis activity. Graphite surfaces, cool white editorial text, small Plex Mono coordinates, and a pale ice-blue accent. Financial red/green communicates direction only.

The main canvas uses an open folio layout with thin separators. The company/date layer is compact; the chart is integrated into the page; narrative claims carry inline financial emphasis and citation controls. There is no KPI card grid, chat bubble stream, fabricated confidence score or decorative animation.

## Interaction

- Cmd/Ctrl+K focuses the persistent research command. Enter submits; Shift+Enter adds a line.
- Suggested commands are ticker-aware. Analysis stages reflect actual server work, not artificial percentages.
- Source controls reveal the corresponding excerpt, date, report period, accession and original SEC link.
- Chart crosshair exposes price/date; range controls change the actual visible data, and touch supports horizontal inspection.
- On narrow screens the evidence desk becomes an expandable layer, not another section stacked below everything.
- Provider unavailable states remain explicit. No unavailable price is rendered as zero, and missing news is not neutral sentiment.
- Motion respects reduced-motion preferences. Type, spaces, colors and borders are centralized in CSS tokens.

## Architecture decision

Keep validated financial behavior in Python and add a narrow FastAPI boundary. Presentation parses only the verified answer's existing statements and source identifiers; it neither asks another model to rewrite them nor invents figures. A React application can manage charts, source reveal, keyboard focus and responsive layout without Streamlit reruns. The original Streamlit interface remains available for fallback.
