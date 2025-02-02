import re
import os
import base64
import hashlib
import shutil
from bs4 import BeautifulSoup
from urllib.parse import unquote, urlparse

def cleanup_assets():
    """Remove existing assets directory if it exists"""
    if os.path.exists('assets'):
        print("\nCleaning up existing assets directory...")
        shutil.rmtree('assets')

def create_directory(path):
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"Created directory: {path}")

def get_safe_filename(url_or_content):
    """Generate a safe filename based on URL or content"""
    hash_object = hashlib.md5(str(url_or_content).encode())
    return hash_object.hexdigest()[:8]

def extract_base64_images(html_content, dry_run=False):
    """Extract base64 encoded images and save them to files"""
    print("\nExtracting base64 images...")
    pattern = r'data:(image\/[^;]+);base64,([^"\'\s]+)'
    matches = re.finditer(pattern, html_content)
    
    if not dry_run:
        create_directory('assets/images')
    count = 0
    
    for match in matches:
        mime_type, b64data = match.groups()
        ext = mime_type.split('/')[-1]
        safe_name = get_safe_filename(b64data)
        filename = f'assets/images/{safe_name}.{ext}'
        
        try:
            if not dry_run:
                image_data = base64.b64decode(b64data)
                with open(filename, 'wb') as f:
                    f.write(image_data)
                html_content = html_content.replace(match.group(0), filename)
            count += 1
        except Exception as e:
            print(f"Failed to decode image {safe_name}: {str(e)}")
    
    print(f"Found {count} images" + (" to extract" if dry_run else " and extracted them"))
    return html_content

def extract_fonts(style_content, dry_run=False):
    """Extract font references and download fonts"""
    print("\nProcessing font references...")
    if not dry_run:
        create_directory('assets/fonts')
    font_pattern = r'url\([\'"]?(chrome-extension://[^\'"]+)[\'"]?\)'
    
    def font_replace(match):
        font_url = match.group(1)
        font_name = os.path.basename(urlparse(font_url).path)
        return f"url('../fonts/{font_name}')"
    
    processed_content = re.sub(font_pattern, font_replace, style_content)
    return processed_content

def extract_styles(soup, dry_run=False):
    """Extract CSS styles into separate files"""
    print("\nExtracting styles...")
    if not dry_run:
        create_directory('assets/css')
    count = 0
    
    for style in soup.find_all('style'):
        if style.string:
            # Process font references
            css_content = extract_fonts(style.string, dry_run)
            
            # Generate filename based on content
            safe_name = get_safe_filename(css_content)
            filename = f'assets/css/{safe_name}.css'
            
            if not dry_run:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(css_content)
                
                # Replace style tag with link
                link = soup.new_tag('link')
                link['rel'] = 'stylesheet'
                link['href'] = filename
                style.replace_with(link)
            count += 1
    
    print(f"Found {count} style blocks" + (" to extract" if dry_run else " and extracted them"))

def extract_scripts(soup, dry_run=False):
    """Extract JavaScript into separate files"""
    print("\nExtracting scripts...")
    if not dry_run:
        create_directory('assets/js')
    count = 0
    
    for script in soup.find_all('script'):
        if script.string and not script.get('src'):  # Only process inline scripts
            # Generate filename based on content
            safe_name = get_safe_filename(script.string)
            filename = f'assets/js/{safe_name}.js'
            
            if not dry_run:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(script.string)
                
                # Update script tag
                script['src'] = filename
                script.string = ''
            count += 1
    
    print(f"Found {count} script blocks" + (" to extract" if dry_run else " and extracted them"))

def download_external_images(soup, dry_run=False):
    """Download external images from meta tags and img tags"""
    print("\nDownloading external images...")
    if not dry_run:
        create_directory('assets/images')
    count = 0
    
    # Process meta tags with image content
    for meta in soup.find_all(['meta', 'img']):  # Added img tags
        content = meta.get('content') or meta.get('src')  # Check both content and src attributes
        if content and content.startswith('https://'):
            safe_name = get_safe_filename(content)
            ext = os.path.splitext(content)[1] or '.jpg'
            filename = f'assets/images/{safe_name}{ext}'
            
            if not dry_run:
                try:
                    import requests
                    response = requests.get(content)
                    response.raise_for_status()
                    
                    with open(filename, 'wb') as f:
                        f.write(response.content)
                    
                    # Update meta/img tag
                    if meta.get('content'):
                        meta['content'] = filename
                    else:
                        meta['src'] = filename
                    count += 1
                except Exception as e:
                    print(f"Failed to download image {content}: {str(e)}")
    
    print(f"Found {count} external images" + (" to download" if dry_run else " and downloaded them"))

def process_html_file(input_file, dry_run=False):
    print(f"\nProcessing {input_file}...")
    if dry_run:
        print("DRY RUN MODE - No files will be written")
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading input file: {str(e)}")
        return
    
    # Clean up existing assets
    if not dry_run:
        cleanup_assets()
        create_directory('assets')
    
    try:
        # Rest of the processing remains the same
        content = extract_base64_images(content, dry_run)
        soup = BeautifulSoup(content, 'html.parser')
        download_external_images(soup, dry_run)
        extract_styles(soup, dry_run)
        extract_scripts(soup, dry_run)
        consolidate_css(soup, dry_run)
        
        if not dry_run:
            with open('index.html', 'w', encoding='utf-8') as f:
                f.write(str(soup.prettify()))
            print("\nProcessing complete! Check index.html and the assets directory.")
        else:
            print("\nDry run complete - no files were modified")
            
    except Exception as e:
        print(f"Error during processing: {str(e)}")

def consolidate_css(soup, dry_run=False):
    """Consolidate multiple CSS files into one"""
    print("\nConsolidating CSS files...")
    css_links = soup.find_all('link', {'rel': 'stylesheet'})
    unique_hrefs = set()
    
    for link in css_links:
        if link.get('href'):
            unique_hrefs.add(link['href'])
            if not dry_run:
                # Remove duplicate links
                if link['href'] not in unique_hrefs:
                    link.decompose()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('input_file', help='Input HTML file to process')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without writing files')
    args = parser.parse_args()
    
    process_html_file(args.input_file, args.dry_run)