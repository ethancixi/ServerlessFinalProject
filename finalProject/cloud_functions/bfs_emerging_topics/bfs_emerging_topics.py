import networkx as nx
from collections import Counter
from datetime import datetime

# Step 1: Load the citation graph from a GML file
citation_graph = nx.read_gml('citation_graph.gml')

# Function to calculate recency score based on the publication year
def calculate_recency(pubdate):
    # Calculate how many years ago the paper was published
    current_year = datetime.now().year
    paper_year = int(pubdate[:4])  # Extract the year from the publication date string (YYYY-MM-DD)
    recency_score = current_year - paper_year  # More recent papers have lower scores (e.g., 0 for the current year)
    return recency_score

# Step 2: BFS function to collect emerging topics with recency adjustment
def bfs_emerging_topics(graph, start_node, max_depth=3):
    visited = set()  # Set to keep track of visited nodes
    queue = [(start_node, 0)]  # Queue to handle BFS, starting with the initial node and depth 0
    emerging_topics = Counter()  # To count topics' occurrences across papers

    while queue:
        current_node, depth = queue.pop(0)  # Pop the first element
        
        if current_node not in visited:
            visited.add(current_node)

            # Get the topics of the current paper (node) including subfields, fields, and domains
            topics = graph.nodes[current_node].get('topics', [])
            
            # Get the recency score for the current paper
            pubdate = graph.nodes[current_node].get('pubdate', "1900-01-01")  # Default to a very old date if not found
            recency_score = calculate_recency(pubdate)
            
            # For each topic, subfield, field, and domain, update the counter with a weighted score
            for topic in topics:
                topic_name = topic["display_name"]
                subfield_name = topic["subfield"]["display_name"] if "subfield" in topic else None
                field_name = topic["field"]["display_name"] if "field" in topic else None
                domain_name = topic["domain"]["display_name"] if "domain" in topic else None
                
                # Adjust the topic count based on the recency score (more recent papers get higher weight)
                weight = 1 / (recency_score + 1)  # Lower recency score means more weight
                
                # Count occurrences of the topics, subfields, fields, and domains with weight adjustment
                emerging_topics[topic_name] += weight
                if subfield_name:
                    emerging_topics[subfield_name] += weight
                if field_name:
                    emerging_topics[field_name] += weight
                if domain_name:
                    emerging_topics[domain_name] += weight

            # If max_depth is not reached, continue exploring connected nodes (citations)
            if depth < max_depth:
                neighbors = list(graph.neighbors(current_node))  # Get neighbors (citations)
                for neighbor in neighbors:
                    if neighbor not in visited:
                        queue.append((neighbor, depth + 1))  # Add the neighbor to the queue

    return emerging_topics

# Step 3: Run BFS and get emerging topics starting from a given node
start_node = list(citation_graph.nodes())[0]  # Start with the first paper node in the graph
max_depth = 3  # Maximum depth for BFS traversal (you can adjust based on your needs)

# Run BFS to find emerging topics
emerging_topics = bfs_emerging_topics(citation_graph, start_node, max_depth)

# Step 4: Print the emerging topics, sorted by their weighted frequency
print("Emerging Topics (sorted by weighted frequency):")
for topic, weight in emerging_topics.most_common():
    print(f"{topic}: {weight:.4f}")
