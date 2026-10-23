# Scholarship AI Analyst

Hackathon prototype (Track 3, client: Harvard University): a web app with an
AI analyst that helps a scholarship endowment decide how to invest a gift and
how much it can pay out every year, using public data.

Team: Samaira Khan · Morgan Derveaux · Charlotte Faux · Lakshman Pathikonda ·
Saikiran Sarangi

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env        # then fill in your API keys
streamlit run app.py        # web app on http://localhost:8501
python -m pytest            # offline tests
```

## Where things are

| Folder | Content |
|---|---|
| `app.py` | the Streamlit web app |
| `scholarfund/` | the engine: simulation, ethics screen, AI explanations, data sources |
| `webapp/` | glue between the web app and the engine, AI chat |
| `tests/` | automated tests |
| `docs/` | full documentation (French) and presentation/demo scripts |
| `templates/` | original hackathon template (Azure OpenAI examples) |

Full documentation: [docs/explications.md](docs/explications.md).

Educational prototype. Not financial advice.
