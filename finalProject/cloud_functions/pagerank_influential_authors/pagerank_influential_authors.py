import networkx as nx
from collections import defaultdict
import json

def load_graph(graph_file):
    """
    Load the citation graph from a GML file.
    """
    citation_graph = nx.read_gml(graph_file)
    print(f"Loaded graph with {len(citation_graph.nodes())} nodes and {len(citation_graph.edges())} edges.")
    return citation_graph

def rank_authors_pagerank(graph, alpha=0.85):
    """
    Ranks authors using PageRank based on the citation network.
    Returns a dictionary mapping topics to their most influential authors.
    """
    author_graph = nx.DiGraph()
    author_papers = defaultdict(set)  # {author: {papers}}
    
    # Step 1: Create an author citation graph
    for node in graph.nodes():
        authors = graph.nodes[node].get('authors', [])
        citations = list(graph.neighbors(node))  # Papers cited by this paper

        # Ensure authors is a list (handle string storage)
        if isinstance(authors, str):
            authors = json.loads(authors)

        for author in authors:
            author_name = author.get("display_name", "Unknown Author")
            author_graph.add_node(author_name)
            author_papers[author_name].add(node)

            # Link authors if they are cited by other papers
            for cited_paper in citations:
                cited_authors = graph.nodes[cited_paper].get('authors', [])
                if isinstance(cited_authors, str):
                    cited_authors = json.loads(cited_authors)

                for cited_author in cited_authors:
                    cited_author_name = cited_author.get("display_name", "Unknown Author")
                    author_graph.add_edge(author_name, cited_author_name)  # Directed edge

    # Step 2: Compute PageRank on the author citation graph
    pagerank_scores = nx.pagerank(author_graph, alpha=alpha)

    # Step 3: Assign PageRank scores to topics
    author_topic_scores = defaultdict(lambda: defaultdict(float))  # {topic: {author: score}}

    for node in graph.nodes():
        authors = graph.nodes[node].get('authors', [])
        topics = graph.nodes[node].get('topics', [])

        if isinstance(authors, str):
            authors = json.loads(authors)
        if isinstance(topics, str):
            topics = json.loads(topics)

        for topic in topics:
            topic_name = topic["display_name"]

            for author in authors:
                author_name = author.get("display_name", "Unknown Author")
                author_topic_scores[topic_name][author_name] += pagerank_scores.get(author_name, 0)

    # Step 4: Sort authors within each topic by influence score
    ranked_authors = {
        topic: sorted(author_counter.items(), key=lambda x: x[1], reverse=True)
        for topic, author_counter in author_topic_scores.items()
    }

    return ranked_authors

def print_top_authors(ranked_authors, top_n=5):
    for topic, authors in ranked_authors.items():
        print(f"\n🔹 Top {top_n} Authors for Topic: {topic}")
        for author, score in authors[:top_n]:
            print(f"  {author}: {score:.4f}")  # Show PageRank score

if __name__ == "__main__":
    # Load the citation graph
    citation_graph = load_graph('citation_graph_full.gml')

    # Rank authors based on PageRank
    ranked_authors = rank_authors_pagerank(citation_graph)

    # Print top authors per topic
    print_top_authors(ranked_authors)
