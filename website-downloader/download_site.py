import asyncio
import os
from website_downloader import WebsiteDownloader

async def download_all_pages():
    # Define the site structure
    pages = {
        '': 'index.html',                    # Main English page
        'ru': 'ru/index.html',               # Main Russian page
        'musician': 'musician/index.html',    # Musician film EN
        'musician-ru': 'musician/ru/index.html', # Musician film RU
        'post': 'post/index.html',           # Postproduction
        'commercial': 'commercial/index.html', # Commercial
        'portfolio': 'portfolio/index.html',  # Portfolio
        'ccc': 'brother/index.html',         # Brother film
        'bs': 'bs/index.html',  # Brother Stories EN
        'bs-ru': 'bs/ru/index.html' # Brother Stories RU
    }
    
    base_url = "https://aborovikov.com"
    
    for path, output_file in pages.items():
        url = f"{base_url}/{path}" if path else base_url
        output_dir = os.path.join('dist', os.path.dirname(output_file))
        
        print(f"\nDownloading {url} to {output_dir}")
        downloader = WebsiteDownloader(url, output_dir)
        await downloader.download_website()

if __name__ == "__main__":
    asyncio.run(download_all_pages()) 