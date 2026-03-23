# Color Planning

Use this reference when the skill/LLM needs to generate category-based color plans.

## Plan-Driven Interface

The renderer is execution-only. Category logic must come from `color-plan.json`:

```json
{
  "color_mode": "category",
  "category_source": "group",
  "category_assignments": {
    "n_user": "access",
    "n_gateway": "access",
    "n_retriever": "retrieval",
    "n_llm": "generation",
    "n_observe": "ops"
  },
  "category_colors": {
    "access": "#56B4E9",
    "retrieval": "#009E73",
    "generation": "#E69F00",
    "ops": "#CC79A7"
  },
  "theme_overrides": {
    "background": "#F8FAFC",
    "edge_color": "#475569",
    "node_border": "#1E293B",
    "node_text": "#0F172A"
  }
}
```

## Curated Palettes (for LLM selection)

- `okabe-ito`: `#56B4E9 #E69F00 #009E73 #0072B2 #D55E00 #CC79A7 #F0E442 #999999`
- `tol-bright`: `#4477AA #EE6677 #228833 #CCBB44 #66CCEE #AA3377 #BBBBBB`
- `tableau10`: `#4E79A7 #F28E2C #E15759 #76B7B2 #59A14F #EDC949 #AF7AA1 #FF9DA7 #9C755F #BAB0AB`
- `brewer-set2`: `#66C2A5 #FC8D62 #8DA0CB #E78AC3 #A6D854 #FFD92F #E5C494 #B3B3B3`

Selection guidance:

- Accessibility-first: `okabe-ito`
- Dense system diagrams: `tol-bright`
- Many categories: `tableau10`
- Soft paper style: `brewer-set2`

## Source Links

- Okabe-Ito: https://easystats.github.io/see/reference/okabeito_colors.html
- Paul Tol qualitative: https://sronpersonalpages.nl/~pault/#sec:qualitative
- Tableau 10 (d3): https://raw.githubusercontent.com/d3/d3-scale-chromatic/main/src/categorical/Tableau10.js
- ColorBrewer Set2 (d3): https://raw.githubusercontent.com/d3/d3-scale-chromatic/main/src/categorical/Set2.js
