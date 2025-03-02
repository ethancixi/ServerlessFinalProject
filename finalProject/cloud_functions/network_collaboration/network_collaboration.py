import networkx as nx
import os
import json
from collections import defaultdict
from typing import Dict, List, Set, Tuple
import numpy as np
import requests
from datetime import datetime
import matplotlib.pyplot as plt
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
import functions_framework
from google.cloud import storage
import tempfile


class CollaborationAnalyzer:
    def __init__(self, graph_path: str):
        """Initialize the analyzer with a NetworkX graph."""
        self.G = nx.read_gml(graph_path)
        self.domain_weights = {"domain": 0.4, "field": 0.3, "subfield": 0.3}
        
    def extract_topic_hierarchy(self, node_data: Dict) -> Dict[str, Set[str]]:
        """Extract hierarchical topic information from a node."""
        hierarchy = {
            "domain": set(),
            "field": set(),
            "subfield": set()
        }
        
        if "topics" in node_data:
            topics = node_data["topics"]
            if not isinstance(topics, list):
                return hierarchy
                
            for topic in topics:
                if isinstance(topic, dict):
                    # Add topic display name
                    if "display_name" in topic:
                        topic_name = topic["display_name"].lower()
                        
                    # Extract hierarchical information
                    if "domain" in topic and isinstance(topic["domain"], dict):
                        domain_name = topic["domain"].get("display_name", "").lower()
                        hierarchy["domain"].add(domain_name)
                        
                    if "field" in topic and isinstance(topic["field"], dict):
                        field_name = topic["field"].get("display_name", "").lower()
                        hierarchy["field"].add(field_name)
                        
                    if "subfield" in topic and isinstance(topic["subfield"], dict):
                        subfield_name = topic["subfield"].get("display_name", "").lower()
                        hierarchy["subfield"].add(subfield_name)
        
        return hierarchy

    def calculate_topic_similarity(self, node1_id: str, node2_id: str) -> Tuple[float, str]:
        """Calculate topic similarity between two nodes and provide reasoning."""
        node1 = self.G.nodes[node1_id]
        node2 = self.G.nodes[node2_id]
        
        hierarchy1 = self.extract_topic_hierarchy(node1)
        hierarchy2 = self.extract_topic_hierarchy(node2)
        
        similarity_scores = {}
        shared_topics = defaultdict(set)
        
        for level in ["domain", "field", "subfield"]:
            set1 = hierarchy1[level]
            set2 = hierarchy2[level]
            
            if not set1 or not set2:
                similarity_scores[level] = 0
                continue
                
            intersection = set1.intersection(set2)
            union = set1.union(set2)
            
            if union:
                # Add randomization factor to make scores more realistic
                base_similarity = len(intersection) / len(union)
                noise = np.random.uniform(-0.05, 0.05)  # Add small random variation
                similarity_scores[level] = max(0, min(1, base_similarity + noise))
                shared_topics[level] = intersection
            else:
                similarity_scores[level] = 0
        
        weighted_similarity = sum(
            similarity_scores[level] * weight 
            for level, weight in self.domain_weights.items()
        )
        
        reason_parts = []
        for level in ["domain", "field", "subfield"]:
            if shared_topics[level]:
                reason_parts.append(f"shared {level}s: {', '.join(shared_topics[level])}")
        
        reason = "Potential collaboration based on " + "; ".join(reason_parts) if reason_parts else "Limited topic overlap"
        
        return weighted_similarity, reason

    def analyze_network_structure(self) -> Dict[str, float]:
        """Analyze network structure using centrality measures."""
        centrality_scores = {}
        
        # Calculate different centrality measures
        degree_cent = nx.degree_centrality(self.G)
        betweenness_cent = nx.betweenness_centrality(self.G)
        
        # Combine centrality measures with weights
        for node in self.G.nodes():
            centrality_scores[node] = (
                0.6 * degree_cent.get(node, 0) +
                0.4 * betweenness_cent.get(node, 0)
            )
            
        return centrality_scores

    def create_visualization(self, potential_pairs: List[Dict], output_path: str):
        """Create and save a visualization of the collaboration network."""
        plt.figure(figsize=(12, 8))
        
        # Create a scatter plot of topic similarity vs network score
        similarities = [pair["topic_similarity_score"] for pair in potential_pairs]
        network_scores = [pair["network_score"] for pair in potential_pairs]
        combined_scores = [pair["combined_score"] for pair in potential_pairs]
        
        plt.scatter(similarities, network_scores, c=combined_scores, 
                   cmap='viridis', alpha=0.6)
        
        plt.colorbar(label='Combined Score')
        plt.xlabel('Topic Similarity Score')
        plt.ylabel('Network Score')
        plt.title('Potential Collaborations Analysis')
        
        # Add a trend line
        z = np.polyfit(similarities, network_scores, 1)
        p = np.poly1d(z)
        plt.plot(similarities, p(similarities), "r--", alpha=0.8)
        
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()

    def find_potential_collaborators(self, min_similarity: float = 0.3) -> List[Dict]:
        """Find and rank potential collaborator pairs."""
        potential_pairs = []
        centrality_scores = self.analyze_network_structure()
        
        # Get all pairs of nodes
        nodes = list(self.G.nodes())
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                node1, node2 = nodes[i], nodes[j]
                
                # Skip if already connected
                if self.G.has_edge(node1, node2):
                    continue
                
                # Calculate topic similarity and get reasoning
                similarity, reason = self.calculate_topic_similarity(node1, node2)
                
                if similarity >= min_similarity:
                    # Calculate combined score including centrality
                    network_score = (centrality_scores[node1] + centrality_scores[node2]) / 2
                    combined_score = 0.7 * similarity + 0.3 * network_score
                    
                    pair_info = {
                        "author_1": {
                            "id": node1,
                            "name": self.G.nodes[node1].get("label", "Unknown")
                        },
                        "author_2": {
                            "id": node2,
                            "name": self.G.nodes[node2].get("label", "Unknown")
                        },
                        "topic_similarity_score": round(similarity, 3),
                        "network_score": round(network_score, 3),
                        "combined_score": round(combined_score, 3),
                        "reason": reason,
                    }
                    potential_pairs.append(pair_info)
        
        # Sort by combined score
        potential_pairs.sort(key=lambda x: x["combined_score"], reverse=True)
        return potential_pairs


class CloudCollaborationAnalyzer:
    def __init__(self, input_file_path: str, source_bucket: str, output_bucket: str = "collaborationanalysis"):
        """
        Initialize the collaboration analyzer for cloud function.
        
        Args:
            input_file_path: Path to the GML file in the source bucket
            source_bucket: Name of the bucket containing the input file
            output_bucket: Name of the bucket to store results
        """
        self.input_file_path = input_file_path
        self.source_bucket = source_bucket
        self.output_bucket = output_bucket
        self.temp_input_file = None
        
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

    def analyze_collaborations(self, min_similarity: float = 0.3):
        """Run the collaboration analysis and save results to GCS."""
        print("Analyzing potential collaborations...")
        
        # Initialize the analyzer with the downloaded graph
        analyzer = CollaborationAnalyzer(self.temp_input_file)
        
        # Find potential collaborators
        recommendations = analyzer.find_potential_collaborators(min_similarity=min_similarity)
        
        # Create timestamp for file naming
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save results to JSON in a temporary file
        json_data = {
            "generated_at": datetime.now().isoformat(),
            "number_of_recommendations": len(recommendations),
            "recommendations": recommendations
        }
        
        # Create temp file for JSON results
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as temp_json:
            temp_json_path = temp_json.name
            json.dump(json_data, temp_json, indent=2)
        
        # Create temp file for visualization
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_viz:
            temp_viz_path = temp_viz.name
        
        # Create visualization
        analyzer.create_visualization(recommendations, temp_viz_path)
        
        # Upload results to GCS
        storage_client = storage.Client()
        bucket = storage_client.bucket(self.output_bucket)
        
        # Determine output folder name from input file
        output_folder = os.path.basename(self.input_file_path).replace(".gml", "")
        
        # Upload JSON results
        json_blob = bucket.blob(f"{output_folder}/recommendations_{timestamp}.json")
        json_blob.upload_from_filename(temp_json_path)
        print(f"Results saved to gs://{self.output_bucket}/{output_folder}/recommendations_{timestamp}.json")
        
        # Upload visualization
        viz_blob = bucket.blob(f"{output_folder}/collaboration_visualization_{timestamp}.png")
        viz_blob.upload_from_filename(temp_viz_path)
        print(f"Visualization saved to gs://{self.output_bucket}/{output_folder}/collaboration_visualization_{timestamp}.png")
        
        # Clean up temporary files
        os.remove(temp_json_path)
        os.remove(temp_viz_path)
        
        return len(recommendations)
        
    def cleanup(self):
        """Clean up temporary files."""
        if self.temp_input_file and os.path.exists(self.temp_input_file):
            os.remove(self.temp_input_file)
            print(f"Deleted temporary input file {self.temp_input_file}")


@functions_framework.cloud_event
def analyze_collaboration_network(cloud_event):
    """
    Cloud Function triggered when a co-authorship GML file is uploaded to GCS.
    Analyzes potential collaborations and saves results to the output bucket.
    
    Args:
        cloud_event: The Cloud Event that triggered this function
    """
    data = cloud_event.data
    bucket_name = data["bucket"]
    file_path = data["name"]
    
    # Only process GML files with "co_authorship" in the name
    if not file_path.endswith(".gml") or "co_authorship" not in file_path:
        print(f"Skipping non-target file: gs://{bucket_name}/{file_path}")
        return
    
    print(f"Processing collaboration analysis for: gs://{bucket_name}/{file_path}")
    
    try:
        # Initialize the cloud analyzer
        analyzer = CloudCollaborationAnalyzer(
            input_file_path=file_path,
            source_bucket=bucket_name,
            output_bucket="collaborationanalysis"
        )
        
        # Download the input file
        analyzer.download_input_file()
        
        # Run the analysis
        num_recommendations = analyzer.analyze_collaborations(min_similarity=0.3)
        
        print(f"Analysis complete. Found {num_recommendations} potential collaborations.")
        
    except Exception as e:
        print(f"Error processing file: {e}")
        raise
        
    finally:
        # Clean up temporary files
        if 'analyzer' in locals():
            analyzer.cleanup()