import requests 

# OpenAlex API endpoint 

OPENALEX_URL = "https://api.openalex.org" 

 

def fetch_data(entity_type, filters, sort_by=None, per_page=25): 

    """ 

    Fetch data from OpenAlex API. 

    :param entity_type: Type of entity to fetch (e.g., 'works', 'authors'). 

    :param filters: Dictionary of filters (e.g., {'publication_year': 2025}). 

    :param sort_by: Sorting criteria (e.g., {'cited_by_count': 'desc'}). 

    :param per_page: Number of results per page. 

    :return: JSON response. 

    """ 

    url = f"{OPENALEX_URL}/{entity_type}" 

    params = { 

        "filter": ",".join([f"{k}:{v}" for k, v in filters.items()]), 

        "sort": ",".join([f"{k}:{v}" for k, v in sort_by.items()]) if sort_by else None, 

        "per-page": per_page, 

    } 

    response = requests.get(url, params=params) 

    if response.status_code == 200: 

        return response.json() 

    else: 

        print(f"Error fetching data: {response.status_code}") 

        return None 

 

# Example: Fetch recent papers from 2025 

filters = {"publication_year": 2025} 

sort_by = {"cited_by_count": "desc"} 

works_data = fetch_data("works", filters, sort_by, per_page=100) 