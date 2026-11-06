"""Eén smalle LLM-aanroep: geen tools, alleen JSON volgens een schema, met een hard budget.

Vóór elke aanroep rekent het budget met de hoogst mogelijke kosten. Past dat niet, dan gaat er niets de deur uit.
"""
import json
import re

PRIJZEN = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}   # $ per miljoen
ONBEKEND = (10.0, 50.0)     # onbekend model (bijvoorbeeld een fallback): reken met de hoogste prijs


ACTIEWOORDEN = re.compile(r"\b(koop|kopen|verkoop|verkopen|buy|sell|order|orders|instappen|shorten)\b", re.I)
LINK = re.compile(r"https?:|www\.", re.I)


def veilige_tekst(tekst, maximum):
    """LLM-tekst die de gebruiker ziet: niet leeg, niet te lang, geen link en geen handelsopdracht."""
    return isinstance(tekst, str) and 0 < len(tekst.strip()) <= maximum and not LINK.search(tekst) and not ACTIEWOORDEN.search(tekst)


class BudgetOp(RuntimeError):
    pass


class GeenAntwoord(RuntimeError):
    pass


def kosten(model, invoer, uitvoer):
    p = PRIJZEN.get(model, ONBEKEND)
    return (invoer * p[0] + uitvoer * p[1]) / 1e6


def anthropic_stuur(model, systeem, gebruiker, schema, max_tokens, effort="low"):
    import anthropic
    client = anthropic.Anthropic(timeout=120.0, max_retries=1)
    extra = {} if "haiku" in model else dict(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    r = client.beta.messages.create(model=model, max_tokens=max_tokens, system=systeem,
                                    messages=[{"role": "user", "content": gebruiker}],
                                    output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}}, **extra)
    tekst = next((b.text for b in r.content if b.type == "text"), "")
    return dict(tekst=tekst, model=r.model, invoer=r.usage.input_tokens, uitvoer=r.usage.output_tokens, stop=r.stop_reason)


class Llm:
    def __init__(self, stuur, model, max_tokens, max_usd, al_besteed=0.0, boek=None):
        self.stuur, self.model, self.max_tokens = stuur, model, max_tokens
        self.max_usd, self.besteed, self.boek = max_usd, al_besteed, boek
        self.deze_ronde = 0.0
        self.modellen = {}

    def vraag(self, systeem, gebruiker, schema, wie="onbekend", effort="low"):
        schatting = (len(systeem) + len(gebruiker) + len(json.dumps(schema))) // 2 + 500     # ruim: minstens 2 tekens per token
        if self.besteed + kosten(self.model, schatting, self.max_tokens) > self.max_usd:
            raise BudgetOp("dagbudget bereikt")
        r = self.stuur(self.model, systeem, gebruiker, schema, self.max_tokens, effort)
        prijs = kosten(r["model"], r["invoer"], r["uitvoer"])
        self.besteed += prijs
        self.deze_ronde += prijs
        self.modellen.setdefault(wie, set()).add(r["model"])
        if self.boek:
            self.boek(r["model"], prijs)
        if r["stop"] != "end_turn":
            raise GeenAntwoord(f"gestopt: {r['stop']}")
        try:
            return json.loads(r["tekst"])
        except ValueError:
            raise GeenAntwoord("geen geldige JSON") from None
