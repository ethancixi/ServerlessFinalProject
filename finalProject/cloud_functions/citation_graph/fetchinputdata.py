import json
import requests
import networkx as nx
import matplotlib.pyplot as plt

# Step 1: Load JSON from file
with open("publications.json", "r", encoding="utf-8") as file:
    data = json.load(file)  # Parse JSON into a dictionary

# Extract the 'results' array
results = data.get("results", [])  # Use .get() to avoid KeyError

# Step 2: Transform the data into structured format
transformed_data = [
    {
        "ID": item["id"],  # Full URL e.g., "https://openalex.org/works/W4405893659"
        "Title": item["title"],
        "Topics": item.get("topics", []),
        "Concepts": item.get("concepts", []),
        "RelatedWork": item.get("related_works", []),
        "CountsByYear": item.get("counts_by_year", []),
        "RelatedPapers": [],
        "DetailedTopics": [],
        "PublicationDate": item.get("publication_date", "0001-01-01"),
    }
    for item in results
]

# Step 3: Create a list of all IDs (extract just the last part from the URL)
ids = [paper["ID"].split('/')[-1] for paper in transformed_data]  # Extracting W4405893659

# Step 4: Fetch the title for each publication via the API
def fetch_publication_details(pub_id):
    # Construct the URL
    url = f"https://api.openalex.org/works/{pub_id}"
    
    # Log the request URL
    print(f"Requesting: {url}")  # Log the URL to the console
    
    # Make the API request
    response = requests.get(url)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch data for {pub_id}")
        return None

# Step 5: Fetch titles for all publications and update the transformed_data
for paper in transformed_data:
    for topic in paper.get("Topics", []):
        topic_info = {
            "id": topic["id"],
            "display_name": topic["display_name"],
            "subfield": {
                "id": topic["subfield"]["id"] if "subfield" in topic else None,
                "display_name": topic["subfield"]["display_name"] if "subfield" in topic else None
            },
            "field": {
                "id": topic["field"]["id"] if "field" in topic else None,
                "display_name": topic["field"]["display_name"] if "field" in topic else None
            },
            "domain": {
                "id": topic["domain"]["id"] if "domain" in topic else None,
                "display_name": topic["domain"]["display_name"] if "domain" in topic else None
            }
        }
        paper["DetailedTopics"].append(topic_info)

    for related_paper in paper["RelatedWork"]:
        # Extract the related publication ID
        related_pub_id = related_paper.split('/')[-1]

        # Fetch publication details for each related work
        publication_details = fetch_publication_details(related_pub_id)

        detailed_topics = []
        for topic in publication_details.get("Topics", []):
            topic_info = {
                "id": topic["id"],
                "display_name": topic["display_name"],
                "subfield": {
                    "id": topic["subfield"]["id"] if "subfield" in topic else None,
                    "display_name": topic["subfield"]["display_name"] if "subfield" in topic else None
                },
                "field": {
                    "id": topic["field"]["id"] if "field" in topic else None,
                    "display_name": topic["field"]["display_name"] if "field" in topic else None
                },
                "domain": {
                    "id": topic["domain"]["id"] if "domain" in topic else None,
                    "display_name": topic["domain"]["display_name"] if "domain" in topic else None
                }
            }
            detailed_topics.append(topic_info)

        # If data is successfully fetched, add it to the related papers
        if publication_details:
            relatedPaper = {
                "ID": publication_details["id"],
                "Title": publication_details["title"],
                "DetailedTopics": detailed_topics,
                "PublicationDate": publication_details["publication_date"]
            }
            paper["RelatedPapers"].append(relatedPaper)

# Now you should have the updated list of related papers with titles
print(json.dumps(transformed_data, indent=4))

# Create and visualize the citation graph
citation_graph = nx.DiGraph()

# Add nodes and edges to the graph
for paper in transformed_data:
    citation_graph.add_node(paper["ID"], title=paper["Title"], topics=paper["DetailedTopics"], pubdate=paper["PublicationDate"])

    # Add edges (citing relationships) and ensure unique entries in the related papers
    unique_related_papers = {related_paper["ID"]: related_paper for related_paper in paper["RelatedPapers"]}.values()

    for related_paper in unique_related_papers:
        # Extract the ID part of the URL
        cited_paper_id = related_paper["ID"].split('/')[-1]  # Extract just the ID part

        if cited_paper_id not in citation_graph:
            citation_graph.add_node(cited_paper_id, title=related_paper["Title"], topics=related_paper["DetailedTopics"], pubdate=related_paper["PublicationDate"])

        citation_graph.add_edge(paper["ID"], cited_paper_id)

# Create labels for the graph
labels = {node: citation_graph.nodes[node].get("title", "No Title Available") for node in citation_graph.nodes}

# Visualize the graph
plt.figure(figsize=(12, 8))
pos = nx.spring_layout(citation_graph, seed=42)  # Layout for positioning nodes

# Draw nodes
nx.draw_networkx_nodes(citation_graph, pos, node_size=2000, node_color="lightblue")

# Draw edges
nx.draw_networkx_edges(citation_graph, pos, arrowstyle="->", arrowsize=10, edge_color="gray")

# Draw labels with a fallback for missing titles
nx.draw_networkx_labels(citation_graph, pos, labels, font_size=8, font_weight="bold")

# Save graph to GML file
nx.write_gml(citation_graph, "citation_graph.gml")

# This generates a Viewable Graph
#plt.title("Citation Graph")
#plt.axis("off")
#plt.show()
