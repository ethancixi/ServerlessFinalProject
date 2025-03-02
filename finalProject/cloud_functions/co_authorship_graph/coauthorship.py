import networkx as nx
import matplotlib.pyplot as plt
from collections import defaultdict
import requests
import time
from typing import Dict, List, Set
import os
import json
import tempfile
import re
import functions_framework
from google.cloud import storage


class CoAuthorshipNetwork:
    def __init__(self, input_file_path: str, source_bucket: str, output_bucket: str = "coauthorshipgraph"):
        """
        Initialize the co-authorship network processor.
        
        Args:
            input_file_path: Path to the input file within the source bucket
            source_bucket: Name of the bucket containing the input file
            output_bucket: Name of the bucket to store results
        """
        self.input_file_path = input_file_path
        self.source_bucket = source_bucket
        self.output_bucket = output_bucket
        self.graph = nx.Graph()  # Undirected graph for co-authorship
        self.author_data = {}    # Cache for author details
        self.topic_cache = {}    # Cache for aggregated topics
        self.temp_input_file = None  # Path to temporary local input file
        
    def download_input_file(self):
        """Download the input GML file from Google Cloud Storage to a temp file."""
        storage_client = storage.Client()
        bucket = storage_client.bucket(self.source_bucket)
        blob = bucket.blob(self.input_file_path)
        
        # Create a temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".gml")
        self.temp_input_file = temp_file.name
        temp_file.close()
        
        # Download the file
        blob.download_to_filename(self.temp_input_file)
        print(f"Downloaded gs://{self.source_bucket}/{self.input_file_path} to {self.temp_input_file}")
        
        return self.temp_input_file
        
    def load_citation_graph(self) -> nx.DiGraph:
        """Load citation graph from the downloaded GML file."""
        print("Loading citation graph from GML...")
        return nx.read_gml(self.temp_input_file)

    def fetch_author_details(self, author_id: str) -> dict:
        """Fetch detailed author information from OpenAlex API."""
        if author_id in self.author_data:
            return self.author_data[author_id]

        url = f"https://api.openalex.org/authors/{author_id}"
        print(f"Fetching author details: {url}")
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                self.author_data[author_id] = response.json()
                time.sleep(0.1)  # Rate limiting
                return self.author_data[author_id]
        except requests.exceptions.RequestException as e:
            print(f"Error fetching author details: {e}")
        
        return None

    def extract_authors_from_papers(self, citation_graph: nx.DiGraph) -> Dict[str, List[str]]:
        """Extract author information from paper nodes."""
        paper_authors = defaultdict(list)
        author_papers = defaultdict(list)
        
        # Assume each paper node has an 'authors' attribute list
        for node in citation_graph.nodes(data=True):
            paper_id = node[0]
            paper_data = node[1]
            
            # Extract authors from OpenAlex API for each paper
            try:
                paper_url = f"https://api.openalex.org/works/{paper_id}"
                response = requests.get(paper_url)
                if response.status_code == 200:
                    paper_details = response.json()
                    authors = paper_details.get('authorships', [])
                    
                    # Record paper-author relationships
                    for authorship in authors:
                        author_id = authorship.get('author', {}).get('id', '').split('/')[-1]
                        if author_id:
                            paper_authors[paper_id].append(author_id)
                            author_papers[author_id].append(paper_id)
                    
                time.sleep(0.1)  # Rate limiting
            except Exception as e:
                print(f"Error fetching paper details for {paper_id}: {e}")
                
        return paper_authors, author_papers

    def aggregate_topics(self, citation_graph: nx.DiGraph, paper_ids: List[str]) -> List[dict]:
        """Aggregate topics from all papers by an author."""
        if tuple(paper_ids) in self.topic_cache:
            return self.topic_cache[tuple(paper_ids)]

        topic_frequency = defaultdict(int)
        topic_details = {}
        
        for paper_id in paper_ids:
            if paper_id in citation_graph:
                paper_data = citation_graph.nodes[paper_id]
                topics = paper_data.get('topics', [])
                
                # Handle both string and list representations of topics
                if isinstance(topics, str) and topics == "_networkx_list_start":
                    continue
                    
                for topic in topics:
                    if isinstance(topic, dict):
                        topic_id = topic.get('id', '')
                        if topic_id:
                            topic_frequency[topic_id] += 1
                            if topic_id not in topic_details:
                                topic_details[topic_id] = {
                                    'id': topic_id,
                                    'display_name': topic.get('display_name', ''),
                                    'domain': topic.get('domain', {}),
                                    'field': topic.get('field', {}),
                                    'subfield': topic.get('subfield', {})
                                }

        # Sort topics by frequency and keep top 5
        top_topics = sorted(topic_frequency.items(), key=lambda x: x[1], reverse=True)[:5]
        aggregated_topics = [topic_details[topic_id] for topic_id, _ in top_topics]
        
        self.topic_cache[tuple(paper_ids)] = aggregated_topics
        return aggregated_topics

    def build_graph(self):
        """Construct the co-authorship network from citation graph."""
        print("Building co-authorship network...")
        
        # Download input file
        self.download_input_file()
        
        # Load citation graph
        citation_graph = self.load_citation_graph()
        
        # Extract author information
        paper_authors, author_papers = self.extract_authors_from_papers(citation_graph)
        
        # Track collaborations
        collaborations = defaultdict(int)
        
        # Build collaboration data
        for paper_id, authors in paper_authors.items():
            for i, author1 in enumerate(authors):
                for author2 in authors[i+1:]:
                    collaborations[(min(author1, author2), max(author1, author2))] += 1

        # Add nodes for each author
        for author_id in author_papers:
            details = self.fetch_author_details(author_id)
            
            # Add node with attributes
            self.graph.add_node(
                author_id,
                label=details.get('display_name', 'Unknown') if details else 'Unknown',
                institution=details.get('last_known_institution', {}).get('display_name', 'Unknown') if details else 'Unknown',
                topics=self.aggregate_topics(citation_graph, author_papers[author_id]),
                pub_count=len(author_papers[author_id])
            )

        # Add weighted edges for collaborations
        for (author1, author2), weight in collaborations.items():
            self.graph.add_edge(author1, author2, weight=weight)

    def save_graph(self, output_path: str):
        """Save the graph in GML format to Google Cloud Storage."""
        print(f"Saving graph to gs://{self.output_bucket}/{output_path}...")
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".gml") as temp_file:
            nx.write_gml(self.graph, temp_file.name)
            temp_file_path = temp_file.name
        
        try:
            # Upload to GCS
            storage_client = storage.Client()
            bucket = storage_client.bucket(self.output_bucket)
            blob = bucket.blob(output_path)
            
            blob.upload_from_filename(temp_file_path)
            print(f"Graph saved to gs://{self.output_bucket}/{output_path}")
            
        finally:
            # Clean up temporary file
            os.remove(temp_file_path)
            print(f"Deleted temporary file {temp_file_path}")

    def visualize_graph(self, output_path: str):
        """Generate and save visualization to Google Cloud Storage."""
        print("Generating visualization...")
        
        # Clear any existing plots
        plt.clf()
        plt.close('all')
        
        # Create new figure
        fig = plt.figure(figsize=(15, 10))
        
        # Position nodes using force-directed layout
        pos = nx.spring_layout(self.graph, k=1, iterations=50)
        
        # Calculate node sizes based on publication count
        node_sizes = [self.graph.nodes[node]["pub_count"] * 100 for node in self.graph.nodes()]
        
        # Calculate edge widths based on collaboration weight
        edge_widths = [self.graph.edges[edge]["weight"] for edge in self.graph.edges()]
        
        # Draw the network
        nx.draw_networkx_nodes(self.graph, pos, node_size=node_sizes, 
                         node_color="lightblue", alpha=0.6)
        nx.draw_networkx_edges(self.graph, pos, width=edge_widths, 
                         alpha=0.5, edge_color="gray")
        
        # Add labels for larger nodes only (more publications)
        labels = {node: self.graph.nodes[node]["label"] 
                for node in self.graph.nodes()
                if self.graph.nodes[node]["pub_count"] > 5}
        nx.draw_networkx_labels(self.graph, pos, labels, font_size=8)
        
        plt.title("Co-authorship Network")
        plt.axis("off")
        
        # Create a temporary file for the visualization
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
            temp_file_path = temp_file.name
        
        # Save to temporary file
        plt.savefig(temp_file_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        
        try:
            # Upload to GCS
            storage_client = storage.Client()
            bucket = storage_client.bucket(self.output_bucket)
            blob = bucket.blob(output_path)
            
            blob.upload_from_filename(temp_file_path)
            print(f"Visualization saved to gs://{self.output_bucket}/{output_path}")
            
        finally:
            # Clean up temporary file
            os.remove(temp_file_path)
            print(f"Deleted temporary file {temp_file_path}")
            
    def save_network_stats(self, output_path: str):
        """Save network statistics as JSON to Google Cloud Storage."""
        # Generate stats
        stats = {
            "number_of_authors": self.graph.number_of_nodes(),
            "number_of_collaborations": self.graph.number_of_edges(),
            "average_collaborations_per_author": 2 * self.graph.number_of_edges() / self.graph.number_of_nodes()
        }
        
        # Upload to GCS
        storage_client = storage.Client()
        bucket = storage_client.bucket(self.output_bucket)
        blob = bucket.blob(output_path)
        
        blob.upload_from_string(json.dumps(stats, indent=4), content_type="application/json")
        print(f"Statistics saved to gs://{self.output_bucket}/{output_path}")
        
    def cleanup(self):
        """Clean up temporary files."""
        if self.temp_input_file and os.path.exists(self.temp_input_file):
            os.remove(self.temp_input_file)
            print(f"Deleted temporary input file {self.temp_input_file}")


@functions_framework.cloud_event
def process_gml_file(cloud_event):
    """
    Cloud Function triggered when a new GML file is uploaded to GCS.
    Builds a co-authorship network and saves results to the output bucket.
    
    Args:
        cloud_event: The Cloud Event that triggered this function
    """
    data = cloud_event.data
    bucket_name = data["bucket"]
    file_path = data["name"]
    
    # Only process GML files from the expected bucket
    if bucket_name != "processeddata_sds" or not file_path.endswith(".gml"):
        print(f"Skipping non-target file: gs://{bucket_name}/{file_path}")
        return
    
    print(f"Processing GML file: gs://{bucket_name}/{file_path}")
    
    try:
        # Extract folder name for output
        base_name = os.path.basename(file_path)
        output_folder = re.sub(r"\s+", "_", base_name.replace(".gml", ""))
        
        # Initialize and build the network
        network = CoAuthorshipNetwork(
            input_file_path=file_path,
            source_bucket=bucket_name,
            output_bucket="coauthorshipgraph"
        )
        
        # Build the co-authorship network
        network.build_graph()
        
        # Save results to output bucket
        network.save_graph(f"{output_folder}/co_authorship_graph.gml")
        network.visualize_graph(f"{output_folder}/co_authorship_network.png")
        network.save_network_stats(f"{output_folder}/network_stats.json")
        
        # Print basic network statistics
        print("\nNetwork Statistics:")
        print(f"Number of authors: {network.graph.number_of_nodes()}")
        print(f"Number of collaborations: {network.graph.number_of_edges()}")
        print(f"Average collaborations per author: {2 * network.graph.number_of_edges() / network.graph.number_of_nodes():.2f}")
        
    except Exception as e:
        print(f"Error processing file: {e}")
        raise
        
    finally:
        # Clean up temporary files
        if 'network' in locals():
            network.cleanup()
