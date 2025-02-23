import networkx as nx
from collections import Counter
import json
from datetime import datetime

# Step 1: Load the citation graph from a GML file
citation_graph = nx.read_gml('citation_graph.gml')

# Step 2: Function to compute time-based weight
def compute_weight(pubdate, most_recent_date):
    """Compute weight based on publication recency (higher for newer papers)."""
    if not pubdate:
        return 1  # Default weight if no date is available
    
    pub_date_obj = datetime.strptime(pubdate, "%Y-%m-%d")
    delta_days = (most_recent_date - pub_date_obj).days
    return max(1, 1 + (3650 - delta_days) / 3650)  # Scale between 1 and ~2.5

# Step 3: Determine the most recent publication date in the graph
pubdates = [
    datetime.strptime(citation_graph.nodes[n].get('pubdate', "1900-01-01"), "%Y-%m-%d")
    for n in citation_graph.nodes if 'pubdate' in citation_graph.nodes[n]
]
most_recent_date = max(pubdates) if pubdates else datetime.strptime("1900-01-01", "%Y-%m-%d")

# Step 4: BFS function to collect emerging topics with recency weighting
def bfs_emerging_topics(graph, start_node, max_depth=3):
    visited = set()  # Keep track of visited nodes
    queue = [(start_node, 0)]  # (node, depth)

    # Separate counters for different categories
    topic_counts = Counter()
    subfield_counts = Counter()
    field_counts = Counter()
    domain_counts = Counter()

    while queue:
        current_node, depth = queue.pop(0)  # Pop the first element
        
        if current_node not in visited:
            visited.add(current_node)

            # Get the paper's topics and publication date
            topics = graph.nodes[current_node].get('topics', [])
            pubdate = graph.nodes[current_node].get('pubdate', None)

            # Ensure topics is a list (handle string storage)
            if isinstance(topics, str):
                topics = json.loads(topics)

            # Compute weight based on recency
            weight = compute_weight(pubdate, most_recent_date)

            # Count topics with recency weighting
            for topic in topics:
                topic_name = topic["display_name"]
                subfield_name = topic.get("subfield", {}).get("display_name")
                field_name = topic.get("field", {}).get("display_name")
                domain_name = topic.get("domain", {}).get("display_name")

                # Apply weight to topic occurrences
                topic_counts[topic_name] += weight
                if subfield_name:
                    subfield_counts[subfield_name] += weight
                if field_name:
                    field_counts[field_name] += weight
                if domain_name:
                    domain_counts[domain_name] += weight

            # If max_depth is not reached, explore connected nodes (citations)
            if depth < max_depth:
                neighbors = list(graph.neighbors(current_node))
                for neighbor in neighbors:
                    if neighbor not in visited:
                        queue.append((neighbor, depth + 1))

    return topic_counts, subfield_counts, field_counts, domain_counts

# Step 5: Run BFS and get emerging topics
start_node = list(citation_graph.nodes())[0]  # Start with the first paper node
max_depth = 3  # Adjust as needed

# Run BFS to find emerging topics with recency weighting
topic_counts, subfield_counts, field_counts, domain_counts = bfs_emerging_topics(citation_graph, start_node, max_depth)

# Step 6: Print emerging topics, grouped by category
def print_sorted_counts(title, counter):
    print(f"\n{title}:")
    for item, count in counter.most_common():
        print(f"{item}: {count:.2f}")  # Print with two decimal places

print_sorted_counts("Domains", domain_counts)
print_sorted_counts("Topics", topic_counts)
print_sorted_counts("Fields", field_counts)
print_sorted_counts("Subfields", subfield_counts)


