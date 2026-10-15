# PJM presentation

[Editable PowerPoint](PJM_GBE_Assessment.pptx) and [PDF](PJM_GBE_Assessment.pdf):37 slides covering data cleaning, weather, A/B/C operating evidence and conditional trades. The accompanying [results](../results/presentation/slide_text.md) and [numeric summary](../results/presentation/results_summary.json) support the slides. [Sources](sources.md) identify the inputs and public references.

Prices are dated 14 October 2026. The 15 October forecast snapshot covers 16 October. The complete snapshot arrived after B's auction. Anonymous equipment and executable two-contract quotes remain unknown.

Edit native text, tables, charts and embedded chart data directly in PowerPoint. To rebuild from source, supply the external frozen deck_content.json checked by source/input_manifest.json and the installed artifact runtime. Set PJM_DECK_INPUT_DIR, ARTIFACT_TOOL_UTILS, PRESENTATIONS_SKILL_DIR, RUNTIME_PYTHON, RUNTIME_NODE, RUNTIME_NODE_MODULES and optional PJM_DECK_BUILD_DIR. Expose the runtime packages to source/. Run build_deck.mjs, finalize.mjs, render_final.mjs and build_pdf.py in order. Use a fresh build directory. The source reads a dynamic slide list; it has no slide-count cap. The exported PPTX contains only visible slide content and editable chart workbooks.
