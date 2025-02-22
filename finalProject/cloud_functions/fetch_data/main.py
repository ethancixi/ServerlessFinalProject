import json
import os

import requests
from google.cloud import storage

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
        "sort": ",".join(
            [f"{k}:{v}" for k, v in sort_by.items()]
        )
        if sort_by
        else None,
        "per-page": per_page,
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching data: {response.status_code}")
        return None


def upload_to_gcs(bucket_name, blob_name, data):
    """
    Upload data to Google Cloud Storage.

    :param bucket_name: Name of the GCS bucket.
    :param blob_name: Path to the blob (file) in the bucket.
    :param data: Data to upload (string).
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    blob.upload_from_string(data, content_type="application/json")
    print(f"Data uploaded to gs://{bucket_name}/{blob_name}")


# Example usage
if __name__ == "__main__":
    # Configuration
    INPUT_BUCKET_NAME = "serverlessfinalproject-raw-data-bucket"  # Replace with your bucket name
    INPUT_BLOB_NAME = (
        "openalex_works.json"  # Replace with your desired blob name
    )

    try:
        # Fetch recent papers from 2025
        filters = {"publication_year": 2025}
        sort_by = {"cited_by_count": "desc"}
        works_data = fetch_data("works", filters, sort_by, per_page=100)

        if works_data:
            # Convert the JSON response to a string
            works_data_json = json.dumps(works_data)

            # Upload the data to GCS
            upload_to_gcs(INPUT_BUCKET_NAME, INPUT_BLOB_NAME, works_data_json)

    except Exception as e:
        print(f"Error: {e}")
