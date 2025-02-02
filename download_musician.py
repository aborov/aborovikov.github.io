import asyncio
from playwright.async_api import async_playwright
import os
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
import mimetypes
import re
import logging
import hashlib
import time
import aiofiles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MusicianDownloader:
    def __init__(self, base_url, output_dir):
        self.base_url = base_url
        self.output_dir = output_dir
        self.base_domain = urlparse(base_url).netloc
        self.downloaded_urls = set()
        self.resource_mapping = {}
        
    async def download_website(self):
        """Main method to download the website"""
        # Clean up existing assets
        if os.path.exists(self.output_dir):
            import shutil
            shutil.rmtree(self.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = await context.new_page()
            
            try:
                await page.goto(self.base_url)
                await self.simulate_user_interaction(page)
                
                # Collect resources
                resources = await self.collect_resources(page)
                
                # Download resources before processing HTML
                await self.download_resources(resources)
                
                # Get and process HTML content
                content = await page.content()
                processed_html = await self.process_html(content)
                
                # Save the processed HTML
                output_file = os.path.join(self.output_dir, 'index.html')
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                async with aiofiles.open(output_file, 'w', encoding='utf-8') as f:
                    await f.write(processed_html)
                    
            finally:
                await browser.close()

    async def download_resource(self, url, session):
        """Download a single resource"""
        try:
            output_path = self.get_resource_path(url)
            if output_path in self.resource_mapping:
                return
                
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.read()
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    async with aiofiles.open(output_path, 'wb') as f:
                        await f.write(content)
                    self.resource_mapping[url] = os.path.relpath(output_path, self.output_dir)
                else:
                    logger.error(f"Failed to download {url}: {response.status}")
        except Exception as e:
            logger.error(f"Error downloading {url}: {str(e)}")

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
                return 'fonts', os.path.splitext(path)[1] or '.woff'
        
        # Fallback to path extension
        ext = os.path.splitext(path)[1].lower()
        if ext in ['.css']:
            return 'css', ext
        elif ext in ['.js']:
            return 'js', ext
        elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']:
            return 'images', ext
        elif ext in ['.woff', '.woff2', '.ttf', '.eot']:
            return 'fonts', ext
        return None, None

    async def collect_resources(self, page):
        """Collect all resources from the page"""
        resources = set()
        
        # First collect required Tilda resources
        cdn_resources = await self.collect_required_scripts(page)
        resources.update(cdn_resources)
        
        # Get all resources from network requests
        client = await page.context.new_cdp_session(page)
        resources_tree = await client.send('Page.getResourceTree')
        for resource in resources_tree['frameTree']['resources']:
            if resource['type'] in ['Script', 'Stylesheet', 'Image', 'Font']:
                resources.add(resource['url'])
        
        # Get resources from DOM
        selectors = [
            ('link[rel="stylesheet"]', 'href'),
            ('script[src]', 'src'),
            ('img', 'src'),
            ('source', {'src', 'srcset'}),
            ('[data-original]', 'data-original'),
            ('[data-img-zoom]', 'data-img-zoom'),
            ('[style*="background-image"]', 'style'),
            # Enhanced Tilda image selectors
            ('.t-bgimg', {'data-original', 'data-original-hover'}),
            ('.t-cover__carrier', {'data-content-cover-bg', 'data-content-cover-hover-bg'}),
            ('.t-img', {'data-original', 'data-img-zoom-url'}),
            ('.t-zoomable', {'data-img-zoom-url', 'data-zoomable-url', 'data-original'}),
            ('.t-gallery__zoom', {'data-zoom-target', 'data-original'}),
            ('.t-slds__item', {'data-original', 'data-img-zoom-url'}),
            # Additional zoom-related selectors
            ('.t-carousel__zoomer__img', 'data-original'),
            ('.t-carousel__zoomer__inner', {'data-original', 'data-img-zoom-url', 'data-zoomable'}),
            ('.t-carousel__zoomer__slides', {'data-img-zoom-url'}),
            ('.t-gallery__item', {'data-original-item', 'data-img-zoom-url'}),
            ('.t-slds__thumbs-item', {'data-img-zoom-url', 'data-original'}),
        ]
        
        for selector, attrs in selectors:
            elements = await page.query_selector_all(selector)
            for element in elements:
                if await element.is_visible():
                    try:
                        if attrs == 'style':
                            style = await element.get_attribute('style')
                            if style and 'background-image' in style:
                                urls = self.extract_urls_from_style(style)
                                resources.update(urls)
                        else:
                            # Handle multiple attributes
                            attr_set = attrs if isinstance(attrs, set) else {attrs}
                            for attr in attr_set:
                                url = await element.get_attribute(str(attr))
                                if url:
                                    resources.add(url)
                    except Exception as e:
                        logger.debug(f"Failed to get attribute for {selector}: {str(e)}")
                        continue
        
        return resources

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

    async def get_local_path(self, url):
        """Get local path for saving resource"""
        if not url or url.startswith('data:'):
            return None
            
        parsed = urlparse(url)
        path = parsed.path.lstrip('/')
        filename = os.path.basename(path)
        
        # Determine resource type from extension or content type
        ext = os.path.splitext(filename)[1].lower()
        if ext in {'.css', '.scss'}:
            subdir = 'css'
        elif ext in {'.js', '.jsx', '.ts'}:
            subdir = 'js'
        elif ext in {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'}:
            is_thumb = await self.is_thumbnail(url)
            subdir = 'images/thumbnails' if is_thumb else 'images'
        elif ext in {'.woff', '.woff2', '.ttf', '.eot'}:
            subdir = 'fonts'
        else:
            subdir = 'other'
            
        # Generate unique filename
        unique_name = f"{os.path.splitext(filename)[0]}_{hashlib.md5(url.encode()).hexdigest()[:8]}{ext}"
        
        return os.path.join(self.output_dir, subdir, unique_name)
        
    async def is_thumbnail(self, url):
        """Check if image is a thumbnail (under 5KB)"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url) as response:
                    size = int(response.headers.get('content-length', 0))
                    return size < 5 * 1024  # 5KB
        except:
            return False

    async def collect_required_scripts(self, page):
        """Dynamically collect all required JavaScript files and CSS"""
        resources = set()
        
        # Get all script and link tags
        elements = await page.query_selector_all('script[src], link[rel="stylesheet"]')
        for element in elements:
            tag_name = await element.evaluate('el => el.tagName.toLowerCase()')
            if tag_name == 'script':
                url = await element.get_attribute('src')
            else:
                url = await element.get_attribute('href')
                
            if url and 'tilda' in url.lower():
                resources.add(url)
        
        # Add essential Tilda resources that might not be in the DOM
        essential_resources = [
            # Core CSS
            'https://static.tildacdn.com/css/tilda-grid-3.0.min.css',
            'https://static.tildacdn.com/css/tilda-blocks-2.12.min.css',
            'https://static.tildacdn.com/css/tilda-zoom-2.0.min.css',
            'https://static.tildacdn.com/css/tilda-slds-1.4.min.css',
            'https://static.tildacdn.com/css/tilda-animation-1.0.min.css',
            
            # Core JavaScript in correct order
            'https://static.tildacdn.com/js/jquery-1.10.2.min.js',
            'https://static.tildacdn.com/js/tilda-scripts-3.0.min.js',
            'https://static.tildacdn.com/js/lazyload-1.3.min.js',
            'https://static.tildacdn.com/js/hammer.min.js',
            'https://static.tildacdn.com/js/tilda-zoom-2.0.min.js',
            'https://static.tildacdn.com/js/tilda-slds-1.4.min.js',
            'https://static.tildacdn.com/js/tilda-animation-sbs-1.0.min.js'
        ]
        resources.update(essential_resources)
        
        return resources

    async def process_html(self, content):
        """Process HTML content while preserving Tilda functionality"""
        soup = BeautifulSoup(content, 'html.parser')
        
        # Add required meta tags
        head = soup.find('head')
        if head:
            meta_viewport = soup.new_tag('meta', attrs={
                'name': 'viewport',
                'content': 'width=device-width, initial-scale=1.0'
            })
            head.insert(0, meta_viewport)
        
        # Update resource references
        for tag, attr in [
            ('link', 'href'),
            ('script', 'src'),
            ('img', 'src'),
            ('source', {'src', 'srcset'}),
            ('meta', 'content'),
            ('div', {
                'data-original', 
                'data-content-cover-bg', 
                'data-img-zoom',
                'data-img-zoom-url',
                'data-zoomable',
                'data-zoomable-url',
                'data-zoom-target',
                'data-original-item',
                'data-animate-style',
                'data-animate-chain'
            }),
            ('a', {'data-content-popup-img-url'}),
        ]:
            for element in soup.find_all(tag):
                # Handle srcset attributes
                if attr == {'src', 'srcset'} and element.get('srcset'):
                    srcset = element['srcset'].split(',')
                    new_srcset = []
                    for src_desc in srcset:
                        src, *desc = src_desc.strip().split()
                        if src in self.resource_mapping:
                            new_srcset.append(f"{self.resource_mapping[src]} {' '.join(desc)}")
                    if new_srcset:
                        element['srcset'] = ', '.join(new_srcset)
                
                # Handle other attributes
                for a in (attr if isinstance(attr, set) else {attr}):
                    if element.get(a):
                        url = element[a]
                        if url in self.resource_mapping:
                            element[a] = self.resource_mapping[url]
        
        # Process background images in style attributes
        elements_with_style = soup.find_all(lambda tag: tag.get('style') and 'background-image' in tag['style'])
        for element in elements_with_style:
            style = element['style']
            url_match = re.search(r'background-image:\s*url\([\'"]?(.*?)[\'"]?\)', style)
            if url_match:
                original_url = url_match.group(1)
                if original_url in self.resource_mapping:
                    new_url = self.resource_mapping[original_url]
                    element['style'] = style.replace(original_url, new_url)
        
        # Add initialization script
        init_script = soup.new_tag('script')
        init_script.string = """
            window.addEventListener('DOMContentLoaded', function() {
                document.body.classList.add('t-body');
                var records = document.getElementById('allrecords');
                if (records) {
                    records.classList.add('t-records');
                    records.style.opacity = '1';
                }
                
                if (typeof jQuery === 'function') {
                    // Initialize components in correct order
                    if (typeof t_lazyload_update === 'function') t_lazyload_update();
                    if (typeof t_animationInit === 'function') t_animationInit();
                    
                    // Reset any zoom state
                    jQuery('body').removeClass('t-zoomer__show');
                    jQuery('.t-zoomer').removeClass('t-zoomer_show');
                    
                    // Initialize zoom after state reset
                    if (typeof t_zoomInit === 'function') t_zoomInit('');
                    
                    // Handle zoom events
                    jQuery(document).on('click', '.t-zoomer__close, .t-zoomer__bg', function() {
                        jQuery('body').removeClass('t-zoomer__show');
                        jQuery('.t-zoomer').removeClass('t-zoomer_show');
                        document.body.style.overflow = '';
                        document.documentElement.style.overflow = '';
                        document.body.style.position = '';
                    });
                    
                    // Ensure scrolling is enabled
                    document.body.style.overflow = 'auto';
                    document.documentElement.style.overflow = 'auto';
                    document.body.style.position = 'relative';
                    
                    // Initialize scroll animations with a slight delay
                    setTimeout(function() {
                        jQuery(window).trigger('scroll');
                        jQuery(window).on('scroll', function() {
                            jQuery('[data-animate-style]').each(function() {
                                if (jQuery(this).offset().top < jQuery(window).scrollTop() + jQuery(window).height() - 100) {
                                    jQuery(this).addClass('t-animate_started');
                                }
                            });
                        });
                    }, 500);
                }
            });
        """
        soup.body.append(init_script)
        
        return str(soup)

    async def simulate_user_interaction(self, page):
        try:
            logger.info(f"Loading page: {self.base_url}")
            await page.wait_for_load_state('networkidle', timeout=15000)
            
            # Scroll through the page more slowly and smoothly
            total_height = await page.evaluate('document.documentElement.scrollHeight')
            viewport_height = await page.evaluate('window.innerHeight')
            current_position = 0
            
            while current_position < total_height:
                await page.evaluate(f'''
                    window.scrollTo({{
                        top: {current_position},
                        behavior: 'smooth'
                    }});
                ''')
                await asyncio.sleep(0.5)  # Increased delay for smoother scrolling
                current_position += viewport_height // 4  # Smaller steps
            
            # Click through gallery items quickly
            gallery_items = await page.query_selector_all('.t-gallery__item')
            for item in gallery_items:
                if await item.is_visible():
                    await item.click()
                    await asyncio.sleep(0.2)
            
            # Trigger zoom on first item of each type
            for selector in ['.t-zoomable', '.t-gallery__zoom', '.t-carousel__zoomer']:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    await element.click()
                    await page.wait_for_load_state('networkidle', timeout=2000)
                    
                    # Click first navigation button if available
                    nav_button = await page.query_selector('.t-carousel__zoomer__arrow')
                    if nav_button and await nav_button.is_visible():
                        await nav_button.click()
                        await asyncio.sleep(0.2)
                    
                    # Close zoom
                    close_button = await page.query_selector('.t-carousel__zoomer__close')
                    if close_button:
                        await close_button.click()
                        await asyncio.sleep(0.2)
                        
        except Exception as e:
            logger.error(f"Error during user interaction simulation: {str(e)}")

    async def download_resources(self, resources):
        """Download all collected resources"""
        async with aiohttp.ClientSession() as session:
            tasks = []
            for url in resources:
                if not url.startswith('data:'):
                    task = asyncio.create_task(self.download_single_resource(session, url))
                    tasks.append(task)
            await asyncio.gather(*tasks)
            
    async def download_single_resource(self, session, url):
        """Download a single resource with retries"""
        retries = 3
        while retries > 0:
            try:
                if url.startswith('data:') or url in self.resource_mapping:
                    return
                    
                async with session.get(url, allow_redirects=True, timeout=30) as response:
                    if response.status == 200:
                        content = await response.read()
                        if len(content) > 0:  # Only save non-empty files
                            local_path = await self.get_local_path(url)
                            if local_path:
                                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                                async with aiofiles.open(local_path, 'wb') as f:
                                    await f.write(content)
                                self.resource_mapping[url] = os.path.relpath(local_path, self.output_dir)
                                logger.info(f"Downloaded: {url}")
                        return
                    elif response.status == 404:
                        logger.warning(f"Resource not found: {url}")
                        return
                        
            except Exception as e:
                retries -= 1
                if retries == 0:
                    logger.error(f"Failed to download {url} after 3 retries: {str(e)}")
                await asyncio.sleep(1)

async def download_musician_pages():
    pages = {
        'musician': 'musician/index.html',
        'musician-ru': 'musician/ru/index.html'
    }
    
    base_url = "https://aborovikov.com"
    
    for path, output_file in pages.items():
        url = f"{base_url}/{path}"
        output_dir = os.path.join('dist', os.path.dirname(output_file))
        
        print(f"\nDownloading musician page: {url} to {output_dir}")
        downloader = MusicianDownloader(url, output_dir)
        await downloader.download_website()

if __name__ == "__main__":
    asyncio.run(download_musician_pages()) 