import arxiv

def fetch_arxiv_papers(query="cat:cs.AI", max_results=1000):
    search = arxiv.Search(
        query=query, 
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )
    client = arxiv.Client()
    for r in client.results(search):
        yield {
            "title": r.title,
            "authors": [a.name for a in r.authors],
            "paper_url": r.entry_id,
            "published_date": r.published,
            "github_url": None,
        }
