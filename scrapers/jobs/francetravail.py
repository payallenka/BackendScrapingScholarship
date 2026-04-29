"""
Ingest jobs from France Travail API and store in jobs table.
Requires OAuth2 token management.
"""
import requests
from datetime import datetime
from scrapers.normalizer import NormalizedJob
from backend.database import upsert_jobs
import os

API_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
CLIENT_ID = os.getenv("FRANCETRAVAIL_CLIENT_ID")
CLIENT_SECRET = os.getenv("FRANCETRAVAIL_CLIENT_SECRET")
TOKEN_URL = "https://entreprise.pole-emploi.fr/connexion/oauth2/access_token?realm=/partenaire"


def get_access_token():
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": "api_offresdemploiv2 o2dsoffre"
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_francetravail_jobs():
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    params = {"motsCles": "visa", "range": "0-49"}  # Example: fetch first 50 jobs with 'visa' keyword
    resp = requests.get(API_URL, headers=headers, params=params)
    data = resp.json()
    jobs = []
    now = datetime.utcnow().isoformat()
    for item in data.get("resultats", []):
        jobs.append(NormalizedJob(
            id=str(item.get("id")),
            title=item.get("intitule"),
            company=item.get("entreprise", {}).get("nom"),
            location=item.get("lieuTravail", {}).get("libelle"),
            contract_type=item.get("typeContratLibelle"),
            salary_min=None,
            salary_max=None,
            currency=None,
            description=item.get("description"),
            tags=[],
            source="francetravail",
            apply_url=item.get("origineOffre", {}).get("urlOrigine"),
            posted_at=item.get("dateCreation"),
            ingested_at=now,
            logo_url=None,
            extra_data=item
        ))
    return jobs

if __name__ == "__main__":
    jobs = fetch_francetravail_jobs()
    upsert_jobs(jobs)
    print(f"Ingested {len(jobs)} jobs from France Travail.")
