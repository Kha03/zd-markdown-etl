import requests

def find_page_containing_keyword(keyword):
    
    url = "https://support.optisigns.com/api/v2/help_center/en-us/articles.json"
    page_count = 1

    print(f"Finding article containing '{keyword}' on the entire system...\n")

    while url:
        response = requests.get(url)
        
        if response.status_code != 200:
            print(f"Error calling API at page {page_count}")
            break

        data = response.json()
        articles = data.get("articles", [])

        for article in articles:
            title = article.get("title", "")
            
            if keyword.lower() in title.lower():
                print(f"✅ SUCCESS: Found article '{title}'")
                print(f"-> Located on PAGE: {page_count}")
                print(f"-> Article Link: {article.get('html_url')}")
                
                # Return the page number as soon as the article is found
                return page_count

        print(f"Finished scanning page {page_count}, not found. Moving to page {page_count + 1}...")
        url = data.get("next_page")
        page_count += 1

    print("\n❌ Sorry, the keyword was not found in any articles.")
    return -1

# Test with an important keyword from the test article
keyword_to_find = "How to use YouTube with OptiSigns"
page_number = find_page_containing_keyword(keyword_to_find)