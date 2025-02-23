import matplotlib.pyplot as plt
import networkx as nx
import community
import json
import os
from itertools import combinations
from datetime import datetime

def load_graph(gml_path):
    """Load the GML graph with enhanced label handling"""
    G = nx.read_gml(gml_path, label='id')
    
    # Create bidirectional label<->ID mapping
    label_to_id = {}
    for node in G.nodes():
        label = G.nodes[node].get('label', str(node))
        label_to_id[label] = node
    G.graph['label_to_id'] = label_to_id
    G.graph['id_to_label'] = {v: k for k, v in label_to_id.items()}
    
    # Preprocess topics and subfields (existing code)
    topic_map = {}
    subfield_map = {}
    for node in G.nodes():
        topics = G.nodes[node].get('topics', [])
        topic_ids = set()
        subfields = set()
        for topic in topics:
            if 'id' in topic:
                topic_ids.add(topic['id'])
            if 'subfield' in topic:
                subfields.add(topic['subfield']['display_name'])
        topic_map[node] = topic_ids
        subfield_map[node] = subfields
    
    G.graph['topic_map'] = topic_map
    G.graph['subfield_map'] = subfield_map
    return G

def detect_communities(G):
    """Apply Louvain community detection and compute cluster topics."""
    partition = community.best_partition(G)    
    communities = {}
    for node, comm in partition.items():
        communities.setdefault(comm, []).append(node)
    
    # Compute cluster topics
    cluster_topics = {}
    for comm, nodes in communities.items():
        topics = set()
        for node in nodes:
            topics.update(G.graph['topic_map'][node])
        cluster_topics[comm] = topics
    G.graph['partition'] = partition
    G.graph['cluster_topics'] = cluster_topics
    return communities

def find_inter_cluster_gaps(G, communities):
    """Identify gaps between communities with overlapping topics."""
    gaps = []
    for comm1, comm2 in combinations(communities.keys(), 2):
        # Check existing connections
        edges_between = sum(1 for u in communities[comm1] for v in communities[comm2] if G.has_edge(u, v))
        if edges_between > 0:
            continue
        
        # Find common topics
        common_topics = G.graph['cluster_topics'][comm1] & G.graph['cluster_topics'][comm2]
        if not common_topics:
            continue
        
        # Get example authors and topic names
        comm1_authors = [G.nodes[n]['label'] for n in communities[comm1] if common_topics & G.graph['topic_map'][n]]
        comm2_authors = [G.nodes[n]['label'] for n in communities[comm2] if common_topics & G.graph['topic_map'][n]]
        topic_names = set()
        for n in communities[comm1] + communities[comm2]:
            for topic in G.nodes[n]['topics']:
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

def find_isolated_authors(G):
    """Identify isolated authors with relevant topic expertise."""
    isolated = [n for n in G.nodes() if G.degree(n) == 0]
    gaps = []
    for node in isolated:
        candidates = []
        node_topics = G.graph['topic_map'][node]
        for other in G.nodes():
            if other != node and G.degree(other) > 0:
                common = node_topics & G.graph['topic_map'][other]
                if common:
                    candidates.append((other, len(common)))
        
        if candidates:
            candidates.sort(key=lambda x: -x[1])
            top_collabs = [G.nodes[c[0]]['label'] for c in candidates[:5]]
            topic_names = [t['display_name'] for t in G.nodes[node]['topics']]
            gaps.append({
                "gap_type": "Isolated Author",
                "author": G.nodes[node]['label'],
                "topic": topic_names,
                "potential_collaborators": top_collabs,
                "reason": f"Isolated author shares {len(candidates)} topics with others."
            })
    return gaps

def find_topical_gaps(G, min_jaccard=0.5):
    """Find author pairs with high topic similarity but no collaboration."""
    gaps = []
    nodes = list(G.nodes())
    for i in range(len(nodes)):
        for j in range(i+1, len(nodes)):
            u, v = nodes[i], nodes[j]
            if G.has_edge(u, v):
                continue
            
            t1 = G.graph['topic_map'][u]
            t2 = G.graph['topic_map'][v]
            if not t1 or not t2:
                continue
            
            intersection = len(t1 & t2)
            union = len(t1 | t2)
            jaccard = intersection / union if union else 0
            
            if jaccard >= min_jaccard:
                gaps.append({
                    "gap_type": "Topical Gap",
                    "authors": [G.nodes[u]['label'], G.nodes[v]['label']],
                    "topic_overlap": intersection,
                    "reason": f"High topic similarity (Jaccard={jaccard:.2f}) but no collaboration."
                })
    return gaps

def find_underconnected_subfields(G, min_ratio=0.8, min_authors=3):
    """Identify subfields with limited external collaborations."""
    subfields = set()
    for node in G.nodes():
        subfields.update(G.graph['subfield_map'][node])
    
    gaps = []
    for sf in subfields:
        authors = [n for n in G.nodes() if sf in G.graph['subfield_map'][n]]
        if len(authors) < min_authors:
            continue
        
        internal = 0
        external = 0
        for author in authors:
            for neighbor in G.neighbors(author):
                if sf in G.graph['subfield_map'][neighbor]:
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

def find_centrality_gaps(G, communities, percentile=25):
    """Identify authors with low betweenness but multi-cluster topic overlap."""
    betweenness = nx.betweenness_centrality(G)
    threshold = sorted(betweenness.values())[len(betweenness)*percentile//100]
    gaps = []
    
    for node in G.nodes():
        if betweenness[node] > threshold:
            continue
        
        overlap_count = 0
        home_cluster = G.graph['partition'][node]
        for comm in communities:
            if comm == home_cluster:
                continue
            if G.graph['topic_map'][node] & G.graph['cluster_topics'][comm]:
                overlap_count += 1
        
        if overlap_count >= 1:
            suggested = []
            for comm in communities:
                if comm == home_cluster or not (G.graph['topic_map'][node] & G.graph['cluster_topics'][comm]):
                    continue
                for candidate in communities[comm][:2]:
                    if not G.has_edge(node, candidate):
                        suggested.append(G.nodes[candidate]['label'])
            
            if suggested:
                gaps.append({
                    "gap_type": "Centrality Gap",
                    "author": G.nodes[node]['label'],
                    "potential_collaborators": suggested[:3],
                    "reason": f"Low betweenness but connects {overlap_count} clusters."
                })
    return gaps


def visualize_network(G, communities, gaps, output_path):
    """Visualize network with proper colormap usage and strategic labeling."""
    plt.figure(figsize=(25, 25))
    
    # Create layout and community coloring
    pos = nx.spring_layout(G, k=0.2, iterations=50)
    partition = G.graph['partition']
    
    # Get colormap and generate colors
    cmap = plt.colormaps['tab20']
    num_colors = len(cmap.colors)  # Get number of colors in the colormap
    node_colors = [cmap(partition[node] % num_colors) for node in G.nodes()]
    
    # Draw base network
    nx.draw_networkx_nodes(G, pos, node_size=80, node_color=node_colors, alpha=0.8)
    nx.draw_networkx_edges(G, pos, alpha=0.05)
    
    # Label important nodes (existing code)
    label_nodes = set()
    for gap in gaps:
        try:
            if gap['gap_type'] == 'Isolated Author':
                node_id = G.graph['label_to_id'].get(gap['author'], None)
                if node_id:
                    label_nodes.add(node_id)
                    # Handle potential collaborators
                    for collab in gap['potential_collaborators']:
                        collab_id = G.graph['label_to_id'].get(collab, None)
                        if collab_id:
                            label_nodes.add(collab_id)
            
            elif gap['gap_type'] == 'Inter-Cluster Gap':
                for author in gap['suggested_authors']:
                    author_id = G.graph['label_to_id'].get(author, None)
                    if author_id:
                        label_nodes.add(author_id)
            
            elif gap['gap_type'] == 'Centrality Gap':
                author_id = G.graph['label_to_id'].get(gap['author'], None)
                if author_id:
                    label_nodes.add(author_id)
                    for collab in gap['potential_collaborators']:
                        collab_id = G.graph['label_to_id'].get(collab, None)
                        if collab_id:
                            label_nodes.add(collab_id)
        
        except KeyError as e:
            print(f"Warning: Missing mapping for {e}, skipping...")
    
    # Clean and draw labels (existing code)
    label_nodes = {n for n in label_nodes if n is not None}
    labels = {n: G.nodes[n]['label'] for n in label_nodes}
    nx.draw_networkx_labels(G, pos, labels, 
                           font_size=9, 
                           font_weight='bold', 
                           font_family='sans-serif',
                           alpha=0.9,
                           bbox=dict(facecolor='white', 
                                   edgecolor='none', 
                                   alpha=0.7,
                                   boxstyle='round,pad=0.2'))
    
    # Highlight isolated nodes (existing code)
    isolated = [n for n in G.nodes() if G.degree(n) == 0]
    nx.draw_networkx_nodes(G, pos, nodelist=isolated, 
                          node_size=200, 
                          node_color='red', 
                          edgecolors='black',
                          linewidths=2)
    
    plt.title("Collaboration Network with Key Gaps Highlighted", fontsize=16)
    plt.axis('off')
    plt.savefig(output_path, bbox_inches='tight', dpi=300)
    plt.close()

if __name__ == "__main__":
    G = load_graph("co_authorship_graph.gml")
    communities = detect_communities(G)
    
    # Generate analysis results
    gaps = []


    gaps += find_inter_cluster_gaps(G, communities)
    gaps += find_isolated_authors(G)
    gaps += find_topical_gaps(G)
    gaps += find_underconnected_subfields(G)
    gaps += find_centrality_gaps(G, communities)
    
    # Create output directory
    output_dir = "gaps_analysis"
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save JSON report
    json_path = f"{output_dir}/gaps_{timestamp}.json"
    with open(json_path, 'w') as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "analysis_type": "co_authorship_gap_analysis",
            "total_gaps_identified": len(gaps),
            "gaps": gaps
        }, f, indent=2)
    
    # Generate and save visualization
    img_path = f"{output_dir}/network_{timestamp}.png"
    visualize_network(G, communities, gaps, img_path)
    

    print(f"Analysis complete. Results saved to:\n- {json_path}\n- {img_path}")
