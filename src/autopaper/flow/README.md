# AutoPaper flows

Two pipelines, two packages:

| Flow | Package | Mission | Documentation |
|------|---------|---------|---------------|
| **Paper input rendering** | `paper_input` | Ingest paper folders → standardized JSON | [paper_input/README.md](paper_input/README.md) |
| **Research** | `research` | Multi-agent AI research → Markdown report | [research/README.md](research/README.md) |

**CLIs**

```bash
autopaper --input examples/neuro_stability    # paper input
research "Market analysis of neural implants"  # research
```

Update the flow README for the pipeline you change.
