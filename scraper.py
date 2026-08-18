import os
import requests
from markdownify import markdownify as md


os.makedirs("articles", exist_ok=True)

def scrape_zendesk_articles():
    # Endpoint Zendesk API OptiSigns
    url = "https://support.optisigns.com/api/v2/help_center/en-us/articles.json"
    
    print(f"Fetching data from {url}...")
    response = requests.get(url)
    
    if response.status_code != 200:
        print("Error occurred while calling the API")
        return

    data = response.json()
    articles = data.get("articles", [])
    
    print(f"Found {len(articles)} articles.")

    for article in articles:
        # Get the necessary fields
        title = article.get("title", "No Title")
        html_body = article.get("body", "")
        article_url = article.get("html_url", "")
        
        # Create slug from article ID to ensure uniqueness
        slug = f"article_{article.get('id')}"
        
        # If body is empty, skip
        if not html_body:
            continue
            
        # convert HTML to Markdown
        # markdownify will convert HTML to Markdown format, and we can specify heading style and code language if needed.
        markdown_content = md(html_body, heading_style="ATX", code_language="text")
        
        # Add Metadata (Source URL) to the beginning of the file for easier citation later
        final_content = f"# {title}\n\n**Article URL:** {article_url}\n\n{markdown_content}"
        
        # save the markdown content to a file
        file_path = f"articles/{slug}.md"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(final_content)
            
        print(f"Saved: {file_path}")

