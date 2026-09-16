from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

import os
import stripe

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or "sk_test_placeholder"

CATALOG = [
    {
        "emergent_product_id": "revisione_referti",
        "name": "Revisione Referti e Riassunto Storia Clinica",
        "tax_code": "txcd_10000000",
        "prices": [{"lookup_key": "revisione_referti", "amount": 5000, "currency": "eur"}],
    },
    {
        "emergent_product_id": "consulto_video",
        "name": "Consulto Video Online (30 minuti)",
        "tax_code": "txcd_10000000",
        "prices": [{"lookup_key": "consulto_video", "amount": 5000, "currency": "eur"}],
    },
    {
        "emergent_product_id": "integrazione_dossier",
        "name": "Integrazione Dossier Clinico",
        "tax_code": "txcd_10000000",
        "prices": [{"lookup_key": "integrazione_dossier", "amount": 2500, "currency": "eur"}],
    },
]


def ensure_tax_settings():
    s = stripe.tax.Settings.retrieve()
    if s.head_office and getattr(s.head_office, "address", None):
        return
    stripe.tax.Settings.modify(
        head_office={"address": {"country": "IT", "line1": "Via Roma 1",
                                 "city": "Milano", "state": "MI", "postal_code": "20121"}},
        defaults={"tax_behavior": "exclusive"})


def get_or_create_product(entry):
    for p in stripe.Product.list(active=True).auto_paging_iter():
        if p.to_dict().get("metadata", {}).get("emergent_product_id") == entry["emergent_product_id"]:
            return p
    return stripe.Product.create(
        name=entry["name"], tax_code=entry.get("tax_code"),
        metadata={"managed_by": "filoclinico", "emergent_product_id": entry["emergent_product_id"]})


def ensure_price(product, p):
    existing = stripe.Price.list(lookup_keys=[p["lookup_key"]], active=True, limit=1).data
    if existing and (existing[0].unit_amount != p["amount"] or existing[0].currency != p["currency"]):
        stripe.Price.modify(existing[0].id, active=False)
        existing = []
    if not existing:
        stripe.Price.create(product=product.id, unit_amount=p["amount"],
                            currency=p["currency"], lookup_key=p["lookup_key"],
                            transfer_lookup_key=True)


if __name__ == "__main__":
    account = stripe.Account.retrieve()
    print("Account country:", account.get("country"))
    ensure_tax_settings()
    for entry in CATALOG:
        product = get_or_create_product(entry)
        for p in entry["prices"]:
            ensure_price(product, p)
        print("OK:", entry["emergent_product_id"])
    print("Catalogo Stripe pronto.")
