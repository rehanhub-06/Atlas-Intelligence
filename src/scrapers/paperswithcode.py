import httpx

async def fetch_pwc_papers(client: httpx.AsyncClient, page=1, per_page=50):
    resp = await client.get("https://paperswithcode.com/api/v1/papers/",
                             params={"page": page, "items_per_page": per_page})
    resp.raise_for_status()
    return resp.json()["results"]
