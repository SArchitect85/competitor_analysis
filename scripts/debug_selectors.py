#!/usr/bin/env python3
"""Debug script to inspect Ad Library page structure."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright


async def debug_ad_library():
    """Open Ad Library in visible browser and inspect structure."""
    url = "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&is_targeted_country=false&media_type=all&search_type=page&view_all_page_id=994431473743430"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        print(f"Navigating to: {url}")
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(3)

        print("\n=== Scrolling to load more ads ===")
        for i in range(5):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            print(f"Scroll {i+1}/5")

        # Scroll back to top
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

        print("\n=== Analyzing page structure ===\n")

        # Try various selectors to find ad containers
        selectors_to_try = [
            'div[class*="x1dr59a3"]',
            'div[class*="_7jvw"]',
            'div[class*="xh8yej3"]',
            'div[role="article"]',
            'div[data-testid]',
            'div[class*="x9f619"]',
            'div[class*="xrvj5dj"]',
            'div[class*="x1yztbdb"]',
            'div[class*="x1n2onr6"]',
            'div[class*="x78zum5"]',
            # More specific patterns
            'div.x1dr59a3',
            'div._99s5',
            'div[class*="x1lliihq"]',
        ]

        print("Testing selectors:")
        for selector in selectors_to_try:
            try:
                elements = await page.query_selector_all(selector)
                if elements:
                    print(f"  {selector}: {len(elements)} elements")
            except Exception as e:
                print(f"  {selector}: Error - {e}")

        # Get the page HTML structure around ads
        print("\n=== Extracting DOM structure ===\n")

        # Find divs that contain "Started running" text (these are likely ad cards)
        ad_structure = await page.evaluate('''() => {
            const results = [];

            // Find all elements containing "Started running"
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                null,
                false
            );

            const adContainers = new Set();
            while (walker.nextNode()) {
                if (walker.currentNode.textContent.includes('Started running')) {
                    // Walk up to find the ad container
                    let parent = walker.currentNode.parentElement;
                    for (let i = 0; i < 15; i++) {
                        if (parent && parent.parentElement) {
                            parent = parent.parentElement;
                        }
                    }
                    if (parent) {
                        adContainers.add(parent);
                    }
                }
            }

            // Analyze each container
            adContainers.forEach((container, index) => {
                if (index < 3) {  // Only first 3
                    results.push({
                        tagName: container.tagName,
                        className: container.className,
                        childCount: container.children.length,
                        outerHTMLPreview: container.outerHTML.substring(0, 500)
                    });
                }
            });

            return {
                totalAdContainers: adContainers.size,
                samples: results
            };
        }''')

        print(f"Found {ad_structure['totalAdContainers']} potential ad containers")
        print("\nSample container structures:")
        for i, sample in enumerate(ad_structure.get('samples', [])):
            print(f"\n--- Ad Container {i+1} ---")
            print(f"Tag: {sample['tagName']}")
            print(f"Classes: {sample['className'][:200]}...")
            print(f"Children: {sample['childCount']}")
            print(f"HTML preview: {sample['outerHTMLPreview'][:300]}...")

        # Find the common parent pattern
        print("\n=== Finding common ad card selector ===\n")

        common_selector = await page.evaluate('''() => {
            // Find elements with "See ad details" links
            const detailLinks = document.querySelectorAll('a[href*="ads/library"][href*="id="]');
            console.log("Found detail links:", detailLinks.length);

            if (detailLinks.length === 0) {
                // Try finding by "Started running" text
                const allDivs = document.querySelectorAll('div');
                const adDivs = [];
                allDivs.forEach(div => {
                    const text = div.innerText || '';
                    if (text.includes('Started running on') && text.length < 5000) {
                        // Check if this looks like an individual ad card
                        const hasImage = div.querySelector('img');
                        const hasVideo = div.querySelector('video');
                        if (hasImage || hasVideo) {
                            adDivs.push({
                                classes: div.className,
                                hasImg: !!hasImage,
                                hasVideo: !!hasVideo
                            });
                        }
                    }
                });
                return { method: 'text-search', count: adDivs.length, samples: adDivs.slice(0, 5) };
            }

            // Get parent containers of detail links
            const containers = [];
            detailLinks.forEach((link, i) => {
                if (i < 5) {
                    let parent = link;
                    for (let j = 0; j < 10; j++) {
                        if (parent.parentElement) parent = parent.parentElement;
                    }
                    containers.push({
                        classes: parent.className,
                        tagName: parent.tagName
                    });
                }
            });

            return { method: 'link-search', count: detailLinks.length, containers };
        }''')

        print(f"Method: {common_selector.get('method')}")
        print(f"Count: {common_selector.get('count')}")
        print(f"Samples: {common_selector.get('samples', common_selector.get('containers', []))[:3]}")

        # Take a screenshot
        screenshot_path = Path(__file__).parent.parent / "logs" / "ad_library_debug.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_path), full_page=False)
        print(f"\nScreenshot saved to: {screenshot_path}")

        # Dump full class analysis
        print("\n=== Detailed class analysis ===\n")

        class_analysis = await page.evaluate('''() => {
            // Find the main content area
            const mainContent = document.querySelector('[role="main"]') || document.body;

            // Find all divs with images (likely ad cards)
            const divsWithMedia = mainContent.querySelectorAll('div:has(img[src*="scontent"]), div:has(video)');

            const classCounts = {};
            const adCardCandidates = [];

            divsWithMedia.forEach(div => {
                // Split and count each class
                const classes = div.className.split(' ');
                classes.forEach(c => {
                    if (c && c.length > 2) {
                        classCounts[c] = (classCounts[c] || 0) + 1;
                    }
                });

                // Check if this div has ad-like content
                const text = div.innerText || '';
                if (text.includes('Started running') || text.includes('Active') || text.includes('Inactive')) {
                    adCardCandidates.push({
                        className: div.className.substring(0, 150),
                        hasStartedRunning: text.includes('Started running'),
                        textLength: text.length
                    });
                }
            });

            // Sort classes by frequency
            const sortedClasses = Object.entries(classCounts)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 20);

            return {
                totalDivsWithMedia: divsWithMedia.length,
                topClasses: sortedClasses,
                adCardCandidates: adCardCandidates.slice(0, 10)
            };
        }''')

        print(f"Divs with media: {class_analysis['totalDivsWithMedia']}")
        print("\nTop classes by frequency:")
        for cls, count in class_analysis['topClasses']:
            print(f"  .{cls}: {count}")

        print(f"\nAd card candidates: {len(class_analysis['adCardCandidates'])}")
        for i, card in enumerate(class_analysis['adCardCandidates'][:5]):
            print(f"  {i+1}. classes={card['className'][:80]}...")

        # Final recommendation
        print("\n=== Getting final selector recommendation ===\n")

        final_analysis = await page.evaluate('''() => {
            // The Ad Library typically wraps each ad in a container
            // Look for the pattern by finding "Library ID:" text
            const allText = document.body.innerText;
            const libraryIdCount = (allText.match(/Library ID:/g) || []).length;

            // Try to find the wrapper
            const wrappers = [];

            // Method 1: Find by data attributes
            const dataAttrDivs = document.querySelectorAll('div[data-pagelet]');

            // Method 2: Find by aria labels
            const ariaLabeled = document.querySelectorAll('[aria-label*="Ad"]');

            // Method 3: Find by the unique ad ID links
            const adIdLinks = document.querySelectorAll('a[href*="/ads/library/?id="]');

            // Method 4: Find the container div pattern - usually siblings of the same class
            let containerClass = null;
            adIdLinks.forEach(link => {
                let el = link;
                for (let i = 0; i < 8; i++) {
                    if (el.parentElement) el = el.parentElement;
                }
                if (el.className) {
                    const classes = el.className.split(' ').filter(c => c.startsWith('x'));
                    if (classes.length > 0) {
                        containerClass = classes[0];
                    }
                }
            });

            // Method 5: Look for the scrollable container with ad cards
            const scrollContainers = document.querySelectorAll('div[style*="overflow"]');

            return {
                libraryIdCount,
                dataAttrDivsCount: dataAttrDivs.length,
                ariaLabeledCount: ariaLabeled.length,
                adIdLinksCount: adIdLinks.length,
                suggestedContainerClass: containerClass,
                adIdLinkHrefs: Array.from(adIdLinks).slice(0, 5).map(a => a.href)
            };
        }''')

        print(f"Library ID mentions: {final_analysis['libraryIdCount']}")
        print(f"Ad ID links found: {final_analysis['adIdLinksCount']}")
        print(f"Suggested container class: {final_analysis['suggestedContainerClass']}")
        print(f"\nSample ad links:")
        for href in final_analysis['adIdLinkHrefs']:
            print(f"  {href}")

        await asyncio.sleep(2)
        await browser.close()
        print("\nBrowser closed.")


if __name__ == "__main__":
    asyncio.run(debug_ad_library())
