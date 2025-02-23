import requests
import time
import json

# Ollama API configuration
OLLAMA_URL = "http://pixelbay.at:11434/api/generate"  # Ensure Ollama is running
OLLAMA_MODEL = "llama3.2:latest"  # Choose an available model (e.g., "gemma:2b", "deepseek-r1:8b")

# Load topics from topics.json and select top 10
def load_top_topics(filename="topics.json", top_n=10):
    """Reads topics from a JSON file and returns the top N topic names based on count."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Sort topics by count (descending) and take top N
        top_topics = sorted(data.items(), key=lambda x: x[1], reverse=True)[:top_n]
        return [topic[0] for topic in top_topics]  # Extract only topic names

    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return []

# Generate topic descriptions using Ollama
def generate_topic_description(topics):
    """
    Calls Ollama to generate a short description for each topic.
    
    :param topics: List of topic names (strings)
    :return: Dictionary mapping topics to generated descriptions
    """
    descriptions = {}

    for topic in topics:
        prompt = f"Provide a concise, one-sentence description for the topic: {topic}."

        try:
            response = requests.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=10  # Set a timeout to prevent issues
            )
            
            # Parse response
            if response.status_code == 200:
                result = response.json()
                description = result.get("response", "No description generated.")
            else:
                description = f"Error: {response.status_code}"

        except requests.exceptions.RequestException as e:
            description = f"Request failed: {str(e)}"

        descriptions[topic] = description
        time.sleep(1)  # Small delay to avoid overwhelming Ollama

    return descriptions

# Save generated descriptions to JSON file
def save_descriptions(filename, descriptions):
    """Saves topic descriptions to a JSON file."""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(descriptions, f, indent=4, ensure_ascii=False)
        print(f"Descriptions saved to {filename}")
    except Exception as e:
        print(f"Error saving {filename}: {e}")

# Main execution
if __name__ == "__main__":
    topics = load_top_topics("topics.json", top_n=10)  # Read and select top 10 topics
    if not topics:
        print("No topics found. Exiting.")
    else:
        print(f"Generating descriptions for the top {len(topics)} topics...")
        descriptions = generate_topic_description(topics)
        
        save_descriptions("top_topic_descriptions.json", descriptions)

        # Print a preview of results
        for topic, desc in descriptions.items():
            print(f"{topic}: {desc}")
