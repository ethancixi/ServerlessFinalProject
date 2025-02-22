import io
import json

import networkx as nx
import pandas as pd
from google.cloud import storage


def fetch_and_process_works_data(bucket_name, blob_name):
    """
    Fetch data from Google Cloud Storage and process it into a pandas DataFrame.

    Args:
        bucket_name (str): Name of the GCS bucket
        blob_name (str): Path to the JSON file in the bucket

    Returns:
        pandas.DataFrame: Processed works data
    """
    # Initialize the GCS client
    storage_client = storage.Client()

    # Get bucket and blob
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    # Download and parse JSON data
    json_data = blob.download_as_string()
    works_data = json.loads(json_data)

    # Extract relevant fields from works data
    works_list = []
    for work in works_data.get("results", []):
        works_list.append(
            {
                "title": work.get("title"),
                "abstract": work.get("abstract"),
                "publication_year": work.get("publication_year"),
                "cited_by_count": work.get("cited_by_count"),
                "authors": [
                    author.get("author", {}).get("display_name")
                    for author in work.get("authorships", [])
                ],
                "keywords": [
                    concept.get("display_name")
                    for concept in work.get("concepts", [])
                ],
            }
        )

    # Convert to DataFrame
    works_df = pd.DataFrame(works_list)
    return works_df


def create_citation_graph(works_data):
    """
    Creates a directed citation graph from the works data.

    Args:
        works_data (dict): The parsed JSON data containing works information.

    Returns:
        networkx.DiGraph: A directed graph representing the citation network.
    """
    citation_graph = nx.DiGraph()

    # Add nodes (papers) and edges (citations)
    for work in works_data.get("results", []):
        paper_id = work.get("id")
        citation_graph.add_node(
            paper_id,
            title=work.get("title"),
            cited_by_count=work.get("cited_by_count"),
        )
        for reference in work.get("referenced_works", []):
            citation_graph.add_edge(paper_id, reference)

    return citation_graph


def save_graph_to_gcs(graph, bucket_name, output_blob_name):
    """
    Saves a NetworkX graph to Google Cloud Storage as a JSON file.

    Args:
        graph (networkx.Graph): The graph to save.
        bucket_name (str): The name of the GCS bucket.
        output_blob_name (str): The path to save the graph in the bucket.
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(output_blob_name)

    # Convert graph to JSON
    graph_data = nx.node_link_data(graph)
    graph_json = json.dumps(graph_data)

    # Upload to GCS
    blob.upload_from_string(graph_json, content_type="application/json")


def save_to_gcs(df, bucket_name, output_blob_name, format="csv"):
    """
    Save the processed DataFrame back to Google Cloud Storage.

    Args:
        df (pandas.DataFrame): DataFrame to save
        bucket_name (str): Name of the GCS bucket
        output_blob_name (str): Path where to save the file
        format (str): Output format ('csv' or 'parquet')
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(output_blob_name)

    # Create a buffer to store the data
    buffer = io.BytesIO()

    # Save to buffer in specified format
    if format.lower() == "csv":
        df.to_csv(buffer, index=False)
    elif format.lower() == "parquet":
        df.to_parquet(buffer)
    else:
        raise ValueError("Format must be either 'csv' or 'parquet'")

    # Upload to GCS
    buffer.seek(0)
    blob.upload_from_file(buffer)


# Example usage
if __name__ == "__main__":
    # Configuration
    INPUT_BUCKET_NAME = "serverlessfinalproject-raw-data-bucket"
    INPUT_BLOB_NAME = "openalex_works.json"
    OUTPUT_BUCKET_NAME = "serverlessfinalproject-citation-graph-bucket"
    OUTPUT_CSV_BLOB_NAME = "preprocessed_data_csv.csv"
    OUTPUT_GRAPH_BLOB_NAME = "preprocessed_data_graph.json"

    try:
        # Fetch data
        storage_client = storage.Client()
        bucket = storage_client.bucket(INPUT_BUCKET_NAME)
        blob = bucket.blob(INPUT_BLOB_NAME)

        # Download and parse JSON data
        json_data = blob.download_as_string()
        works_data = json.loads(json_data)

        # Process data into DataFrame
        works_df = fetch_and_process_works_data(
            INPUT_BUCKET_NAME, INPUT_BLOB_NAME
        )

        # Display the top 5 papers
        print("Top 5 papers:")
        print(works_df.head())

        # Save the processed data back to GCS
        save_to_gcs(
            works_df, OUTPUT_BUCKET_NAME, OUTPUT_CSV_BLOB_NAME, format="csv"
        )
        print(
            f"DataFrame successfully saved to gs://{OUTPUT_BUCKET_NAME}/"
            f"{OUTPUT_CSV_BLOB_NAME}"
        )

        # Create citation graph
        citation_graph = create_citation_graph(works_data)

        # Save the graph to GCS
        save_graph_to_gcs(
            citation_graph, OUTPUT_BUCKET_NAME, OUTPUT_GRAPH_BLOB_NAME
        )
        print(
            f"Graph successfully saved to gs://{OUTPUT_BUCKET_NAME}/"
            f"{OUTPUT_GRAPH_BLOB_NAME}"
        )

    except Exception as e:
        print(f"Error processing data: {str(e)}")
