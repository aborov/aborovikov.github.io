import asyncio
import os
from website_downloader import WebsiteDownloader
from download_musician import MusicianDownloader

async def download_complete_site():
    # Define the site structure
    pages = {
        '': 'index.html',
        'ru': 'ru/index.html',
        'musician': 'musician/index.html',
        'musician-ru': 'musician/ru/index.html',
        'post': 'post/index.html',
        'commercial': 'commercial/index.html',
        'portfolio': 'portfolio/index.html',
        'ccc': 'brother/index.html',  # Brother film
        'bs': 'bs/index.html',
        'bs-ru': 'bs/ru/index.html'
    }
    
    base_url = "https://aborovikov.com"
    base_output_dir = "dist"
    
    # Clean up existing dist directory
    if os.path.exists(base_output_dir):
        import shutil
        shutil.rmtree(base_output_dir)
    os.makedirs(base_output_dir, exist_ok=True)
    
    # Download each page
    for path, output_file in pages.items():
        url = f"{base_url}/{path}" if path else base_url
        output_dir = os.path.join(base_output_dir, os.path.dirname(output_file))
        
        print(f"\nDownloading page: {url} to {output_dir}")
        
        # Use MusicianDownloader for musician pages and brother film page
        if 'musician' in path or path == 'ccc':
            downloader = MusicianDownloader(url, output_dir)
        else:
            downloader = WebsiteDownloader(url, output_dir)
        
        await downloader.download_website()

if __name__ == "__main__":
    asyncio.run(download_complete_site()) 