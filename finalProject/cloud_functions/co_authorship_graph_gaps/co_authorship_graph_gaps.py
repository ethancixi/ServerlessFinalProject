import matplotlib.pyplot as plt
import networkx as nx
import community
import json
import os
from itertools import combinations
from datetime import datetime
import functions_framework
from google.cloud import storage
import tempfile

class CoAuthorshipGapAnalyzer:
    def __init__(self, gml_path):
        """Load the GML graph with enhanced label handling"""
        self.G = nx.read_gml(gml_path, label='id')
        
        # Create bidirectional label<->ID mapping
        label_to_id = {}
        for node in self.G.nodes():
            label = self.G.nodes[node].get('label', str(node))
            label_to_id[label] = node
        self.G.graph['label_to_id'] = label_to_id
        self.G.graph['id_to_label'] = {v: k for k, v in label_to_id.items()}
        
        # Preprocess topics and subfields
        topic_map = {}
        subfield_map = {}
        for node in self.G.nodes():
            topics = self.G.nodes[node].get('topics', [])
            topic_ids = set()
            subfields = set()
            for topic in topics:
                if 'id' in topic:
                    topic_ids.add(topic['id'])
                if 'subfield' in topic:
                    subfields.add(topic['subfield']['display_name'])
            topic_map[node] = topic_ids
            subfield_map[node] = subfields
        
        self.G.graph['topic_map'] = topic_map
        self.G.graph['subfield_map'] = subfield_map
        
        # Initialize communities
        self.communities = self.detect_communities()

    def detect_communities(self):
        """Apply Louvain community detection and compute cluster topics."""
        partition = community.best_partition(self.G)    
        communities = {}
        for node, comm in partition.items():
            communities.setdefault(comm, []).append(node)
        
        # Compute cluster topics
        cluster_topics = {}
        for comm, nodes in communities.items():
            topics = set()
            for node in nodes:
                topics.update(self.G.graph['topic_map'][node])
            cluster_topics[comm] = topics
        self.G.graph['partition'] = partition
        self.G.graph['cluster_topics'] = cluster_topics
        return communities

    def find_inter_cluster_gaps(self):
        """Identify gaps between communities with overlapping topics."""
        gaps = []
        for comm1, comm2 in combinations(self.communities.keys(), 2):
            # Check existing connections
            edges_between = sum(1 for u in self.communities[comm1] for v in self.communities[comm2] if self.G.has_edge(u, v))
            if edges_between > 0:
                continue
            
            # Find common topics
            common_topics = self.G.graph['cluster_topics'][comm1] & self.G.graph['cluster_topics'][comm2]
            if not common_topics:
                continue
            
            # Get example authors and topic names
            comm1_authors = [self.G.nodes[n]['label'] for n in self.communities[comm1] if common_topics & self.G.graph['topic_map'][n]]
            comm2_authors = [self.G.nodes[n]['label'] for n in self.communities[comm2] if common_topics & self.G.graph['topic_map'][n]]
            topic_names = set()
            for n in self.communities[comm1] + self.communities[comm2]:
                for topic in self.G.nodes[n]['topics']:
                    if topic['id'] in common_topics:
                        topic_names.add(topic['display_name'])
            
            if comm1_authors and comm2_authors:
                gaps.append({
                    "gap_type": "Inter-Cluster Gap",
                    "clusters": [f"Cluster {comm1}", f"Cluster {comm2}"],
                    "topic_overlap": list(topic_names)[:3],
                    "suggested_authors": [comm1_authors[0], comm2_authors[0]],
                    "reason": f"No collaborations between clusters despite {len(common_topics)} shared topics."
                })
        return gaps

    def find_isolated_authors(self):
        """Identify isolated authors with relevant topic expertise."""
        isolated = [n for n in self.G.nodes() if self.G.degree(n) == 0]
        gaps = []
        for node in isolated:
            candidates = []
            node_topics = self.G.graph['topic_map'][node]
            for other in self.G.nodes():
                if other != node and self.G.degree(other) > 0:
                    common = node_topics & self.G.graph['topic_map'][other]
                    if common:
                        candidates.append((other, len(common)))
            
            if candidates:
                candidates.sort(key=lambda x: -x[1])
                top_collabs = [self.G.nodes[c[0]]['label'] for c in candidates[:5]]
                topic_names = [t['display_name'] for t in self.G.nodes[node]['topics']]
                gaps.append({
                    "gap_type": "Isolated Author",
                    "author": self.G.nodes[node]['label'],
                    "topic": topic_names,
                    "potential_collaborators": top_collabs,
                    "reason": f"Isolated author shares {len(candidates)} topics with others."
                })
        return gaps

    def find_topical_gaps(self, min_jaccard=0.5):
        """Find author pairs with high topic similarity but no collaboration."""
        gaps = []
        nodes = list(self.G.nodes())
        for i in range(len(nodes)):
            for j in range(i+1, len(nodes)):
                u, v = nodes[i], nodes[j]
                if self.G.has_edge(u, v):
                    continue
                
                t1 = self.G.graph['topic_map'][u]
                t2 = self.G.graph['topic_map'][v]
                if not t1 or not t2:
                    continue
                
                intersection = len(t1 & t2)
                union = len(t1 | t2)
                jaccard = intersection / union if union else 0
                
                if jaccard >= min_jaccard:
                    gaps.append({
                        "gap_type": "Topical Gap",
                        "authors": [self.G.nodes[u]['label'], self.G.nodes[v]['label']],
                        "topic_overlap": intersection,
                        "reason": f"High topic similarity (Jaccard={jaccard:.2f}) but no collaboration."
                    })
        return gaps

    def find_underconnected_subfields(self, min_ratio=0.8, min_authors=3):
        """Identify subfields with limited external collaborations."""
        subfields = set()
        for node in self.G.nodes():
            subfields.update(self.G.graph['subfield_map'][node])
        
        gaps = []
        for sf in subfields:
            authors = [n for n in self.G.nodes() if sf in self.G.graph['subfield_map'][n]]
            if len(authors) < min_authors:
                continue
            
            internal = 0
            external = 0
            for author in authors:
                for neighbor in self.G.neighbors(author):
                    if sf in self.G.graph['subfield_map'][neighbor]:
                        internal += 1
                    else:
                        external += 1
            
            total = internal + external
            if total == 0:
                continue
            
            ratio = internal / total
            if ratio > min_ratio and external < 1:
                gaps.append({
                    "gap_type": "Underconnected Subfield",
                    "subfield": sf,
                    "internal_edges": internal,
                    "external_edges": external,
                    "reason": f"Limited cross-subfield collaborations (ratio={ratio:.2f})."
                })
        return gaps

    def find_centrality_gaps(self, percentile=25):
        """Identify authors with low betweenness but multi-cluster topic overlap."""
        betweenness = nx.betweenness_centrality(self.G)
        threshold = sorted(betweenness.values())[len(betweenness)*percentile//100]
        gaps = []
        
        for node in self.G.nodes():
            if betweenness[node] > threshold:
                continue
            
            overlap_count = 0
            home_cluster = self.G.graph['partition'][node]
            for comm in self.communities:
                if comm == home_cluster:
                    continue
                if self.G.graph['topic_map'][node] & self.G.graph['cluster_topics'][comm]:
                    overlap_count += 1
            
            if overlap_count >= 1:
                suggested = []
                for comm in self.communities:
                    if comm == home_cluster or not (self.G.graph['topic_map'][node] & self.G.graph['cluster_topics'][comm]):
                        continue
                    for candidate in self.communities[comm][:2]:
                        if not self.G.has_edge(node, candidate):
                            suggested.append(self.G.nodes[candidate]['label'])
                
                if suggested:
                    gaps.append({
                        "gap_type": "Centrality Gap",
                        "author": self.G.nodes[node]['label'],
                        "potential_collaborators": suggested[:3],
                        "reason": f"Low betweenness but connects {overlap_count} clusters."
                    })
        return gaps

    def visualize_network(self, gaps, output_path):
        """Visualize network with proper colormap usage and strategic labeling."""
        plt.figure(figsize=(25, 25))
        
        # Create layout and community coloring
        pos = nx.spring_layout(self.G, k=0.2, iterations=50)
        partition = self.G.graph['partition']
        
        # Get colormap and generate colors
        cmap = plt.colormaps['tab20']
        num_colors = len(cmap.colors)  # Get number of colors in the colormap
        node_colors = [cmap(partition[node] % num_colors) for node in self.G.nodes()]
        
        # Draw base network
        nx.draw_networkx_nodes(self.G, pos, node_size=80, node_color=node_colors, alpha=0.8)
        nx.draw_networkx_edges(self.G, pos, alpha=0.05)
        
        # Label important nodes
        label_nodes = set()
        for gap in gaps:
            try:
                if gap['gap_type'] == 'Isolated Author':
                    node_id = self.G.graph['label_to_id'].get(gap['author'], None)
                    if node_id:
                        label_nodes.add(node_id)
                        # Handle potential collaborators
                        for collab in gap['potential_collaborators']:
                            collab_id = self.G.graph['label_to_id'].get(collab, None)
                            if collab_id:
                                label_nodes.add(collab_id)
                
                elif gap['gap_type'] == 'Inter-Cluster Gap':
                    for author in gap['suggested_authors']:
                        author_id = self.G.graph['label_to_id'].get(author, None)
                        if author_id:
                            label_nodes.add(author_id)
                
                elif gap['gap_type'] == 'Centrality Gap':
                    author_id = self.G.graph['label_to_id'].get(gap['author'], None)
                    if author_id:
                        label_nodes.add(author_id)
                        for collab in gap['potential_collaborators']:
                            collab_id = self.G.graph['label_to_id'].get(collab, None)
                            if collab_id:
                                label_nodes.add(collab_id)
            
            except KeyError as e:
                print(f"Warning: Missing mapping for {e}, skipping...")
        
        # Clean and draw labels
        label_nodes = {n for n in label_nodes if n is not None}
        labels = {n: self.G.nodes[n]['label'] for n in label_nodes}
        nx.draw_networkx_labels(self.G, pos, labels, 
                              font_size=9, 
                              font_weight='bold', 
                              font_family='sans-serif',
                              alpha=0.9,
                              bbox=dict(facecolor='white', 
                                      edgecolor='none', 
                                      alpha=0.7,
                                      boxstyle='round,pad=0.2'))
        
        # Highlight isolated nodes
        isolated = [n for n in self.G.nodes() if self.G.degree(n) == 0]
        nx.draw_networkx_nodes(self.G, pos, nodelist=isolated, 
                              node_size=200, 
                              node_color='red', 
                              edgecolors='black',
                              linewidths=2)
        
        plt.title("Collaboration Network with Key Gaps Highlighted", fontsize=16)
        plt.axis('off')
        plt.savefig(output_path, bbox_inches='tight', dpi=300)
        plt.close()

    def analyze_all_gaps(self):
        """Run all gap detection algorithms and return combined results."""
        gaps = []
        gaps += self.find_inter_cluster_gaps()
        gaps += self.find_isolated_authors()
        gaps += self.find_topical_gaps()
        gaps += self.find_underconnected_subfields()
        gaps += self.find_centrality_gaps()
        return gaps


class CloudGapAnalyzer:
    def __init__(self, input_file_path, source_bucket, output_bucket="gaps_analysis"):
        """
        Initialize the gap analyzer for cloud function.
        
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

    def analyze_gaps(self):
        """Run the gap analysis and save results to GCS."""
        print("Analyzing co-authorship gaps...")
        
        # Initialize the analyzer with the downloaded graph
        analyzer = CoAuthorshipGapAnalyzer(self.temp_input_file)
        
        # Generate all gaps
        gaps = analyzer.analyze_all_gaps()
        
        # Create timestamp for file naming
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save results to JSON in a temporary file
        json_data = {
            "generated_at": datetime.now().isoformat(),
            "analysis_type": "co_authorship_gap_analysis",
            "total_gaps_identified": len(gaps),
            "gaps": gaps
        }
        
        # Create temp file for JSON results
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as temp_json:
            temp_json_path = temp_json.name
            json.dump(json_data, temp_json, indent=2)
        
        # Create temp file for visualization
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_viz:
            temp_viz_path = temp_viz.name
        
        # Create visualization
        analyzer.visualize_network(gaps, temp_viz_path)
        
        # Upload results to GCS
        storage_client = storage.Client()
        bucket = storage_client.bucket(self.output_bucket)
        
        # Determine output folder name from input file
        output_folder = os.path.basename(self.input_file_path).replace(".gml", "")
        
        # Upload JSON results
        json_blob = bucket.blob(f"{output_folder}/gaps_{timestamp}.json")
        json_blob.upload_from_filename(temp_json_path)
        print(f"Results saved to gs://{self.output_bucket}/{output_folder}/gaps_{timestamp}.json")
        
        # Upload visualization
        viz_blob = bucket.blob(f"{output_folder}/network_{timestamp}.png")
        viz_blob.upload_from_filename(temp_viz_path)
        print(f"Visualization saved to gs://{self.output_bucket}/{output_folder}/network_{timestamp}.png")
        
        # Clean up temporary files
        os.remove(temp_json_path)
        os.remove(temp_viz_path)
        
        return len(gaps)
        
    def cleanup(self):
        """Clean up temporary files."""
        if self.temp_input_file and os.path.exists(self.temp_input_file):
            os.remove(self.temp_input_file)
            print(f"Deleted temporary input file {self.temp_input_file}")


@functions_framework.cloud_event
def analyze_coauthorship_gaps(cloud_event):
    """
    Cloud Function triggered when a co-authorship GML file is uploaded to GCS.
    Analyzes collaboration gaps and saves results to the output bucket.
    
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
    
    print(f"Processing co-authorship gap analysis for: gs://{bucket_name}/{file_path}")
    
    try:
        # Initialize the cloud analyzer
        analyzer = CloudGapAnalyzer(
            input_file_path=file_path,
            source_bucket=bucket_name,
            output_bucket="gaps_analysis"
        )
        
        # Download the input file
        analyzer.download_input_file()
        
        # Run the analysis
        num_gaps = analyzer.analyze_gaps()
        
        print(f"Analysis complete. Found {num_gaps} potential gaps in the collaboration network.")
        
    except Exception as e:
        print(f"Error processing file: {e}")
        raise
        
    finally:
        # Clean up temporary files
        if 'analyzer' in locals():
            analyzer.cleanup()