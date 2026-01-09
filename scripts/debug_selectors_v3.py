#!/usr/bin/env python3
"""Debug script v3 - precise ad card detection."""

import asyncio
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright


async def debug_ad_library():
    url = "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&is_targeted_country=false&media_type=all&search_type=page&view_all_page_id=994431473743430"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        print(f"Navigating to: {url}")
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(3)

        # Scroll to load all ads
        print("Scrolling...")
        for _ in range(10):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5)

        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

        # Use XPath to find elements containing "Library ID:" text
        print("\n=== Using XPath to find ad cards ===\n")

        # Find all spans/divs with "Library ID:" text and get their ancestor
        ad_cards_info = await page.evaluate('''() => {
            // Use XPath to find text containing "Library ID:"
            const xpath = "//span[contains(text(), 'Library ID:')]/ancestor::div[contains(@class, 'x')]";
            const result = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);

            console.log("XPath results:", result.snapshotLength);

            // We need to find the correct ancestor level that gives us individual ad cards
            // Strategy: For each Library ID span, walk up and find the smallest container
            // that has a sibling with similar structure

            const libraryIdSpans = document.evaluate(
                "//span[contains(text(), 'Library ID:')]",
                document,
                null,
                XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
                null
            );

            const adCards = [];
            const seenContainers = new Set();

            for (let i = 0; i < libraryIdSpans.snapshotLength; i++) {
                const span = libraryIdSpans.snapshotItem(i);
                let el = span;

                // Walk up to find the ad card container
                // Look for a div that's a direct child of a container with multiple similar children
                for (let level = 0; level < 25; level++) {
                    if (!el.parentElement) break;
                    el = el.parentElement;

                    const parent = el.parentElement;
                    if (!parent) continue;

                    // Check siblings
                    const siblings = Array.from(parent.children).filter(c => c.tagName === 'DIV');

                    // If we have multiple div siblings and they have similar class patterns
                    if (siblings.length >= 2) {
                        // Check if siblings contain "Library ID:" (meaning they're also ad cards)
                        const siblingsWithLibraryId = siblings.filter(sib => {
                            return sib !== el && sib.innerText && sib.innerText.includes('Library ID:');
                        });

                        if (siblingsWithLibraryId.length > 0) {
                            // Found the right level!
                            const containerId = el.className + '_' + level;
                            if (!seenContainers.has(containerId)) {
                                seenContainers.add(containerId);
                                adCards.push({
                                    level: level,
                                    tagName: el.tagName,
                                    className: el.className,
                                    parentChildCount: siblings.length,
                                    parentClassName: parent.className,
                                    innerTextPreview: (el.innerText || '').substring(0, 200)
                                });
                            }
                            break;
                        }
                    }
                }
            }

            return {
                libraryIdCount: libraryIdSpans.snapshotLength,
                adCardsFound: adCards.length,
                adCards: adCards.slice(0, 10)
            };
        }''')

        print(f"Library ID spans: {ad_cards_info['libraryIdCount']}")
        print(f"Ad cards identified: {ad_cards_info['adCardsFound']}")
        print("\nAd card details:")
        for card in ad_cards_info.get('adCards', []):
            print(f"  Level {card['level']}: {card['tagName']}")
            print(f"    Class: {card['className'][:80]}")
            print(f"    Parent children: {card['parentChildCount']}")
            print(f"    Parent class: {card['parentClassName'][:60]}")
            print()

        # Now build and test the selector
        if ad_cards_info.get('adCards'):
            card = ad_cards_info['adCards'][0]
            parent_class = card['parentClassName'].split()[0] if card['parentClassName'] else ''
            child_class = card['className'].split()[0] if card['className'] else ''

            print(f"\n=== Building selector ===")
            print(f"Parent class: {parent_class}")
            print(f"Card class: {child_class}")

            # Test various selectors
            selectors_to_test = [
                f"div.{parent_class} > div.{child_class}" if parent_class and child_class else None,
                f"div.{child_class}",
                f"div[class*='{child_class}']",
            ]

            for sel in filter(None, selectors_to_test):
                try:
                    count = await page.evaluate(f'document.querySelectorAll("{sel}").length')
                    print(f"  {sel}: {count} elements")
                except Exception as e:
                    print(f"  {sel}: Error - {e}")

        # Alternative: Use the specific xpath approach for extraction
        print("\n=== Testing XPath-based extraction ===\n")

        extraction_test = await page.evaluate('''() => {
            const results = [];

            // Find all "Library ID:" occurrences and extract ad data
            const textNodes = [];
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            while (walker.nextNode()) {
                if (walker.currentNode.textContent.includes('Library ID:')) {
                    textNodes.push(walker.currentNode);
                }
            }

            textNodes.forEach((textNode, idx) => {
                // Get the Library ID value
                const match = textNode.textContent.match(/Library ID:\\s*(\\d+)/);
                if (!match) return;

                const libraryId = match[1];

                // Find the ad card container by walking up
                let container = textNode.parentElement;
                for (let i = 0; i < 20; i++) {
                    if (!container.parentElement) break;

                    // Check if this container has "Started running" text too
                    const text = container.innerText || '';
                    if (text.includes('Started running on') && text.includes('Library ID:')) {
                        // This is likely our ad card - verify it's self-contained
                        const libraryIdMatches = text.match(/Library ID:/g);
                        if (libraryIdMatches && libraryIdMatches.length === 1) {
                            results.push({
                                libraryId,
                                containerTag: container.tagName,
                                containerClass: container.className.substring(0, 100),
                                containerLevel: i
                            });
                            break;
                        }
                    }
                    container = container.parentElement;
                }
            });

            // Find the common container class pattern
            const classPatterns = {};
            results.forEach(r => {
                const firstClass = r.containerClass.split(' ')[0];
                classPatterns[firstClass] = (classPatterns[firstClass] || 0) + 1;
            });

            return {
                totalFound: results.length,
                results: results.slice(0, 5),
                classPatterns: Object.entries(classPatterns).sort((a,b) => b[1] - a[1]).slice(0, 5)
            };
        }''')

        print(f"Ads found via text walking: {extraction_test['totalFound']}")
        print("\nClass patterns:")
        for cls, count in extraction_test.get('classPatterns', []):
            print(f"  {cls}: {count}")

        print("\nSample extractions:")
        for r in extraction_test.get('results', []):
            print(f"  Library ID: {r['libraryId']}")
            print(f"    Container level: {r['containerLevel']}")
            print(f"    Container class: {r['containerClass']}")
            print()

        # Save the best selector approach
        best_class = extraction_test['classPatterns'][0][0] if extraction_test.get('classPatterns') else None
        if best_class:
            print(f"\n=== RECOMMENDED APPROACH ===")
            print(f"Best container class: {best_class}")

            # Final verification
            final_count = await page.evaluate(f'''() => {{
                const containers = document.querySelectorAll("div.{best_class}");
                let adCount = 0;
                containers.forEach(c => {{
                    const text = c.innerText || '';
                    const hasLibraryId = text.includes('Library ID:');
                    const hasSingleLibraryId = (text.match(/Library ID:/g) || []).length === 1;
                    if (hasLibraryId && hasSingleLibraryId) adCount++;
                }});
                return {{ total: containers.length, adCards: adCount }};
            }}''')
            print(f"Elements with class '{best_class}': {final_count['total']}")
            print(f"Actual ad cards: {final_count['adCards']}")

        await asyncio.sleep(2)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(debug_ad_library())
