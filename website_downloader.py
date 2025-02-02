import asyncio
from playwright.async_api import async_playwright
import os
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
import mimetypes
import re
import logging
import time
import hashlib
import aiofiles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebsiteDownloader:
    def __init__(self, base_url, output_dir, scroll_timeout=60, interaction_timeout=60):
        self.base_url = base_url
        self.output_dir = output_dir
        self.base_domain = urlparse(base_url).netloc
        self.downloaded_urls = set()
        self.resource_mapping = {}
        self.scroll_timeout = scroll_timeout
        self.interaction_timeout = interaction_timeout
        self.resources_to_download = set()
        
    def get_original_image_url(self, url):
        """Convert thumbnail URL to original image URL while preserving structure"""
        parsed = urlparse(url)
        path_parts = parsed.path.split('/')
        
        # Keep original path structure but remove resize parameters
        if 'thb.tildacdn.net' in url:
            # Remove resize parameters but keep the path
            clean_path = re.sub(r'/-/resize[^/]+/', '/', parsed.path)
            return f"https://static.tildacdn.net{clean_path}"
        return url

    async def download_resource(self, url, session, max_retries=3, retry_delay=1):
        """Download resource with simplified structure"""
        try:
            parsed = urlparse(url)
            
            # Handle relative Tilda URLs
            if url.startswith('/'):
                url = f"https://static.tildacdn.net{url}"
            
            # Clean up URL by removing timestamp parameters but keep other query params
            if 't=' in url:
                url = re.sub(r't=\d+', '', url).rstrip('?&')
            
            if url == self.base_url or url.startswith('data:'):
                return url

            # Get original filename and clean it
            original_filename = os.path.basename(parsed.path).split('?')[0]
            if not original_filename:
                original_filename = 'index'
            
            # Determine file type and directory
            content_type = mimetypes.guess_type(url)[0]
            subdir, ext = self.get_file_type_info(content_type, parsed.path)
            if not subdir:
                return url
            
            # For thumbnails, use a separate directory
            is_thumbnail = 'thb.tildacdn.net' in url or '/20x/' in url or '/-/resize' in url
            if is_thumbnail and subdir == 'images':
                subdir = 'images/thumbnails'
            
            # Always append hash for noroot.png files
            if original_filename == 'noroot.png':
                url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                filename = f"noroot_{url_hash}{ext}"
            else:
                # Try using original filename first
                base_filename = os.path.splitext(original_filename)[0]
                filename = f"{base_filename}{ext}"
                local_path = os.path.join(subdir, filename)
                full_path = os.path.join(self.output_dir, local_path)
                
                # If filename exists (and it's not noroot.png), append hash
                if os.path.exists(full_path) or local_path in self.resource_mapping.values():
                    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                    filename = f"{base_filename}_{url_hash}{ext}"

            local_path = os.path.join(subdir, filename)
            full_path = os.path.join(self.output_dir, local_path)
            
            # Create directory if needed
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            # Download if we haven't already
            if url not in self.downloaded_urls:
                for attempt in range(max_retries):
                    try:
                        async with session.get(url) as response:
                            if response.status == 200:
                                content = await response.read()
                                async with aiofiles.open(full_path, 'wb') as f:
                                    await f.write(content)
                                self.downloaded_urls.add(url)
                                self.resource_mapping[url] = local_path
                                break
                    except Exception as e:
                        if attempt == max_retries - 1:
                            print(f"Failed to download {url}: {str(e)}")
                            return url
                        await asyncio.sleep(retry_delay)

            return local_path

        except Exception as e:
            logger.error(f"Error downloading {url}: {str(e)}")
            return url

    def process_css_url(self, url):
        """Process URLs found in CSS files"""
        if url.startswith('data:') or url.startswith('http'):
            return url
        return f'../{self.resource_mapping.get(urljoin(self.base_url, url), url)}'

    async def process_html(self, content):
        """Process HTML content and remove Tilda dependencies"""
        soup = BeautifulSoup(content, 'html.parser')
        
        # Remove Tilda-specific scripts
        for script in soup.find_all('script'):
            if script.get('src'):
                src = script['src']
                if 'tilda' in src.lower():
                    if src.startswith('http'):
                        url = src
                    else:
                        url = f"https://static.tildacdn.net{src}"
                    
                    # Add to resources to download
                    if url not in self.resource_mapping:
                        self.resources_to_download.add(url)
                        local_path = f"js/{os.path.basename(urlparse(url).path)}"
                        self.resource_mapping[url] = local_path
                        script['src'] = local_path
        
        # Remove Tilda-specific meta tags
        for meta in soup.find_all('meta'):
            if meta.get('content') and 'tildacdn' in meta.get('content'):
                meta.decompose()
        
        # Remove Tilda favicon
        for link in soup.find_all('link'):
            if link.get('href') and 'tildafavicon' in link['href']:
                link.decompose()
        
        # Remove Tilda data attributes
        for element in soup.find_all(True):
            attrs_to_remove = [attr for attr in element.attrs if 'tilda' in attr.lower()]
            for attr in attrs_to_remove:
                del element[attr]
        
        # Process elements with style attributes containing background-image
        elements_with_style = soup.find_all(lambda tag: tag.get('style') and 'background-image' in tag['style'])
        for element in elements_with_style:
            style = element['style']
            url_match = re.search(r'background-image:\s*url\([\'"]?(.*?)[\'"]?\)', style)
            if url_match:
                original_url = url_match.group(1)
                if original_url in self.resource_mapping:
                    new_url = self.resource_mapping[original_url]
                    element['style'] = style.replace(original_url, new_url)

        # Update resource references
        for tag, attr in [
            ('link', 'href'),
            ('script', 'src'),
            ('img', 'src'),
            ('source', {'src', 'srcset'}),
            ('meta', 'content'),
            ('div', {'data-original', 'data-content-cover-bg', 'data-img-zoom'}),
        ]:
            for element in soup.find_all(tag):
                if attr == {'src', 'srcset'} and element.get('srcset'):
                    srcset = element['srcset'].split(',')
                    new_srcset = []
                    for src_desc in srcset:
                        src, *desc = src_desc.strip().split()
                        if src in self.resource_mapping:
                            new_srcset.append(f"{self.resource_mapping[src]} {' '.join(desc)}")
                    if new_srcset:
                        element['srcset'] = ', '.join(new_srcset)
                
                for a in (attr if isinstance(attr, set) else {attr}):
                    if element.get(a):
                        url = element[a]
                        if url in self.resource_mapping:
                            element[a] = self.resource_mapping[url]
        
        return str(soup)

    async def download_website(self):
        """Main method to download the website and all its resources"""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            
            page = await context.new_page()
            
            try:
                # Set a shorter navigation timeout
                page.set_default_navigation_timeout(30000)
                page.set_default_timeout(30000)
                
                # Go to page and wait for initial load
                await page.goto(self.base_url, wait_until='domcontentloaded')
                
                # Wait for essential content
                try:
                    await page.wait_for_selector('body', timeout=10000)
                except Exception as e:
                    logger.warning(f"Timeout waiting for body, continuing anyway: {str(e)}")
                
                await self.simulate_user_interaction(page)
                
                # Collect resources using both methods
                resources = await self.collect_resources(page)
                content = await page.content()
                
                # Download all resources
                async with aiohttp.ClientSession() as session:
                    tasks = [self.download_resource(url, session) for url in resources]
                    await asyncio.gather(*tasks)
                
                # Process and save HTML
                processed_html = await self.process_html(content)
                os.makedirs(self.output_dir, exist_ok=True)
                async with aiofiles.open(os.path.join(self.output_dir, 'index.html'), 'w', encoding='utf-8') as f:
                    await f.write(processed_html)
            
            except Exception as e:
                logger.error(f"Error during website download: {str(e)}")
                # Save whatever content we have
                try:
                    content = await page.content()
                    processed_html = await self.process_html(content)
                    os.makedirs(self.output_dir, exist_ok=True)
                    async with aiofiles.open(os.path.join(self.output_dir, 'index.html'), 'w', encoding='utf-8') as f:
                        await f.write(processed_html)
                except Exception as save_error:
                    logger.error(f"Failed to save partial content: {str(save_error)}")
            
            finally:
                await browser.close()

    async def simulate_user_interaction(self, page):
        """Simulate user interactions to reveal dynamic content"""
        try:
            logger.info(f"Loading page: {self.base_url}")
            await page.wait_for_load_state('networkidle', timeout=60000)
            logger.info("Page loaded, starting interactions")
            
            # Smooth scroll to bottom
            last_height = await page.evaluate('document.documentElement.scrollHeight')
            start_time = time.time()
            
            while time.time() - start_time < self.scroll_timeout:
                await page.evaluate('window.scrollBy({top: 100, behavior: "smooth"})')
                await asyncio.sleep(0.5)
                
                new_height = await page.evaluate('document.documentElement.scrollHeight')
                if new_height == last_height:
                    await asyncio.sleep(3)
                    if new_height == await page.evaluate('document.documentElement.scrollHeight'):
                        break
                last_height = new_height
            
            # Tilda-specific selectors
            selectors = [
                '.t-slds__arrow_wrapper',  # Tilda carousel arrows
                '.t-slds__bullet',         # Tilda carousel dots
                '.t-zoomable',             # Tilda zoomable images
                '.t-gallery__zoom',        # Tilda gallery zoom
                '[data-gallery-theme]',    # Gallery items
                '.t-carousel__zoomer',     # Carousel zoom buttons
                '.t-popup',                # Popup triggers
                '.t-gallery__item'         # Gallery items
            ]

            start_time = time.time()
            while time.time() - start_time < self.interaction_timeout:
                for selector in selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        for element in elements:
                            if await element.is_visible():
                                await element.scroll_into_view_if_needed()
                                await asyncio.sleep(0.5)
                                
                                try:
                                    await element.click()
                                    await asyncio.sleep(1)
                                    await page.wait_for_load_state('networkidle', timeout=5000)
                                except Exception as e:
                                    logger.debug(f"Click failed on {selector}: {str(e)}")
                                
                                # Close any opened modal/popup
                                try:
                                    close_button = await page.query_selector('.t-popup__close')
                                    if close_button:
                                        await close_button.click()
                                        await asyncio.sleep(0.5)
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.debug(f"Failed to process selector {selector}: {str(e)}")

        except Exception as e:
            logger.error(f"Error during user interaction simulation: {str(e)}")
            # Continue execution even if interaction fails
            pass

    def extract_urls_from_style(self, style):
        """Extract URLs from inline style attributes"""
        urls = set()
        url_pattern = r'url\([\'"]?([^\'")\s]+)[\'"]?\)'
        matches = re.finditer(url_pattern, style)
        for match in matches:
            url = match.group(1)
            if not url.startswith(('data:', 'https://www.youtube.com')):
                if url.startswith(('http', '//')):
                    urls.add(url)
                else:
                    urls.add(urljoin(self.base_url, url))
        return urls

    async def collect_resources(self, page):
        """Collect all resources from the page"""
        resources = set()
        
        try:
            # Shorter timeout for network idle
            await page.wait_for_load_state('networkidle', timeout=10000)
        except Exception as e:
            logger.warning(f"Network idle timeout reached, continuing anyway: {str(e)}")
        
        # Get all elements with background images
        elements_with_bg = await page.query_selector_all('[style*="background-image"]')
        for element in elements_with_bg:
            style = await element.get_attribute('style')
            if style:
                bg_urls = self.extract_urls_from_style(style)
                resources.update(bg_urls)
        
        # Get all resources from network requests
        client = await page.context.new_cdp_session(page)
        resources_tree = await client.send('Page.getResourceTree')
        for resource in resources_tree['frameTree']['resources']:
            if resource['type'] in ['Script', 'Stylesheet', 'Image', 'Font']:
                resources.add(resource['url'])
        
        # Get resources from DOM including thumbnails
        for selector, attr in [
            ('link[rel="stylesheet"]', 'href'),
            ('script', 'src'),
            ('img', 'src'),
            ('source', 'srcset'),
            ('[data-original]', 'data-original'),
            ('[data-img-zoom]', 'data-img-zoom'),
            ('[data-lazy-rule]', 'data-original'),
            ('[style*="background-image"]', 'style'),
            # Add Tilda thumbnail selectors
            ('.t-bgimg', 'data-original'),
            ('.t-cover__carrier', 'data-content-cover-bg'),
            ('.t-img', 'data-original'),
        ]:
            elements = await page.query_selector_all(selector)
            for element in elements:
                if attr == 'style':
                    style = await element.get_attribute(attr)
                    if style:
                        bg_urls = self.extract_urls_from_style(style)
                        resources.update(bg_urls)
                else:
                    url = await element.get_attribute(attr)
                    if url:
                        resources.add(url)
        
        return resources

    def get_file_type_info(self, content_type, path):
        """Determine subdirectory and extension for a file"""
        if content_type:
            if content_type.startswith('image/'):
                return 'images', mimetypes.guess_extension(content_type) or '.jpg'
            elif content_type.startswith('text/css'):
                return 'css', '.css'
            elif content_type.startswith(('application/javascript', 'text/javascript')):
                return 'js', '.js'
            elif content_type.startswith(('font/', 'application/font')):
                return 'fonts', '.woff'
            else:
                return 'other', ''
        else:
            ext = os.path.splitext(path)[1]
            if ext in ['.css']:
                return 'css', ext
            elif ext in ['.js']:
                return 'js', ext
            elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico']:
                return 'images', ext
            elif ext in ['.woff', '.woff2', '.ttf', '.eot', '.otf']:
                return 'fonts', ext
        return None, None

async def main():
    import sys
    if len(sys.argv) != 3:
        print("Usage: python script.py <url> <output_directory>")
        return
    
    url = sys.argv[1]
    output_dir = sys.argv[2]
    
    downloader = WebsiteDownloader(url, output_dir)
    await downloader.download_website()

if __name__ == "__main__":
    asyncio.run(main())