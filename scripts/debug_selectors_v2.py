#!/usr/bin/env python3
"""Debug script v2 - find exact ad card selectors."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright


async def debug_ad_library():
    """Find the exact selectors for ad cards."""
    url = "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&is_targeted_country=false&media_type=all&search_type=page&view_all_page_id=994431473743430"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = await context.new_page()

        print(f"Navigating to: {url}")
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(3)

        # Scroll to load ads
        print("Scrolling to load ads...")
        for i in range(8):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5)

        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

        # Strategy: Find all elements containing "Library ID:" and trace their parent ad container
        print("\n=== Finding ad containers by Library ID ===\n")

        ad_card_analysis = await page.evaluate('''() => {
            const results = {
                adCards: [],
                commonAncestorClasses: {},
                selectorRecommendation: null
            };

            // Find all text nodes containing "Library ID"
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                { acceptNode: (node) =>
                    node.textContent.includes('Library ID') ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT
                }
            );

            const libraryIdElements = [];
            while (walker.nextNode()) {
                libraryIdElements.push(walker.currentNode.parentElement);
            }

            console.log("Found Library ID elements:", libraryIdElements.length);

            // For each Library ID, find the ad card container (go up until we find a sibling with same structure)
            libraryIdElements.forEach((el, idx) => {
                // Walk up to find the card container
                let current = el;
                let cardContainer = null;

                for (let i = 0; i < 20; i++) {
                    if (!current.parentElement) break;
                    current = current.parentElement;

                    // Check if this has siblings with similar structure (other ad cards)
                    const parent = current.parentElement;
                    if (parent) {
                        const siblings = Array.from(parent.children);
                        const similarSiblings = siblings.filter(sib =>
                            sib.className === current.className && sib !== current
                        );

                        if (similarSiblings.length > 0) {
                            cardContainer = current;
                            break;
                        }
                    }
                }

                if (cardContainer && idx < 5) {
                    const classes = cardContainer.className.split(' ').filter(c => c);
                    results.adCards.push({
                        index: idx,
                        tagName: cardContainer.tagName,
                        className: cardContainer.className,
                        classList: classes,
                        siblingCount: cardContainer.parentElement ? cardContainer.parentElement.children.length : 0
                    });

                    // Count class frequency
                    classes.forEach(cls => {
                        results.commonAncestorClasses[cls] = (results.commonAncestorClasses[cls] || 0) + 1;
                    });
                }
            });

            // Find the most common class combination
            const sortedClasses = Object.entries(results.commonAncestorClasses)
                .sort((a, b) => b[1] - a[1]);

            if (sortedClasses.length > 0 && results.adCards.length > 0) {
                // Use the first card's full class as the selector
                results.selectorRecommendation = results.adCards[0].className;
            }

            results.libraryIdCount = libraryIdElements.length;
            results.sortedClasses = sortedClasses.slice(0, 10);

            return results;
        }''')

        print(f"Library ID elements found: {ad_card_analysis['libraryIdCount']}")
        print(f"\nAd card samples:")
        for card in ad_card_analysis.get('adCards', []):
            print(f"  Card {card['index']}: {card['tagName']} siblings={card['siblingCount']}")
            print(f"    Classes: {card['className'][:100]}...")

        print(f"\nCommon classes in ad containers:")
        for cls, count in ad_card_analysis.get('sortedClasses', []):
            print(f"  .{cls}: {count}")

        # Now let's test potential selectors
        print("\n=== Testing selector candidates ===\n")

        if ad_card_analysis.get('adCards'):
            first_card = ad_card_analysis['adCards'][0]
            # Try selecting by the exact class string
            test_results = await page.evaluate('''(testClasses) => {
                const results = {};

                // Test each class individually
                testClasses.forEach(cls => {
                    const selector = `div.${cls}`;
                    try {
                        const elements = document.querySelectorAll(selector);
                        results[selector] = elements.length;
                    } catch(e) {
                        results[selector] = 'error';
                    }
                });

                // Test combinations
                if (testClasses.length >= 2) {
                    const combo = `div.${testClasses[0]}.${testClasses[1]}`;
                    try {
                        results[combo] = document.querySelectorAll(combo).length;
                    } catch(e) {}
                }

                // Test the specific pattern for ad containers
                // Usually ad cards are direct children of a scrollable container
                const specificTests = [
                    'div[class*="x9f619"][class*="x1n2onr6"][class*="x1ja2u2z"]',
                    'div.x9f619.x1n2onr6.x1ja2u2z',
                    'div[class*="xrvj5dj"]',
                ];

                specificTests.forEach(sel => {
                    try {
                        results[sel] = document.querySelectorAll(sel).length;
                    } catch(e) {
                        results[sel] = 'error';
                    }
                });

                return results;
            }''', first_card.get('classList', [])[:5])

            for selector, count in test_results.items():
                print(f"  {selector}: {count}")

        # Get the actual structure using a different approach
        print("\n=== Alternative: Finding ad cards by structure ===\n")

        structure_analysis = await page.evaluate('''() => {
            // Find the main scrollable content area
            const mainArea = document.querySelector('[role="main"]');
            if (!mainArea) return { error: "No main area" };

            // Look for repeated div patterns that contain ad content
            // Ad cards typically have: image/video, text, "Started running on", "Library ID"

            const allDivs = mainArea.querySelectorAll('div');
            const candidates = [];

            allDivs.forEach(div => {
                const text = div.innerText || '';
                const hasLibraryId = text.includes('Library ID:');
                const hasStartedRunning = text.includes('Started running on');
                const hasMedia = div.querySelector('img, video');

                // This could be an ad card if it has all three
                if (hasLibraryId && hasStartedRunning && hasMedia) {
                    // Check text length - ad cards should be reasonably sized
                    if (text.length > 50 && text.length < 10000) {
                        // Count how many Library IDs are in this div (should be 1 for individual cards)
                        const libraryIdCount = (text.match(/Library ID:/g) || []).length;

                        candidates.push({
                            className: div.className,
                            libraryIdCount,
                            textLength: text.length,
                            rect: div.getBoundingClientRect()
                        });
                    }
                }
            });

            // Filter to only those with exactly 1 Library ID (individual ad cards)
            const singleAdCards = candidates.filter(c => c.libraryIdCount === 1);

            // Group by className to find the pattern
            const classGroups = {};
            singleAdCards.forEach(card => {
                const key = card.className;
                if (!classGroups[key]) {
                    classGroups[key] = { count: 0, sample: card };
                }
                classGroups[key].count++;
            });

            // Sort by count
            const sortedGroups = Object.entries(classGroups)
                .sort((a, b) => b[1].count - a[1].count)
                .slice(0, 5);

            return {
                totalCandidates: candidates.length,
                singleAdCards: singleAdCards.length,
                topClassGroups: sortedGroups.map(([cls, data]) => ({
                    className: cls.substring(0, 150),
                    count: data.count,
                    textLength: data.sample.textLength
                }))
            };
        }''')

        print(f"Total candidates: {structure_analysis.get('totalCandidates', 0)}")
        print(f"Single ad cards: {structure_analysis.get('singleAdCards', 0)}")
        print(f"\nTop class groups (likely the ad card selector):")
        for group in structure_analysis.get('topClassGroups', []):
            print(f"  Count: {group['count']}, TextLen: {group['textLength']}")
            print(f"    Classes: {group['className']}")

        # Final selector test
        if structure_analysis.get('topClassGroups'):
            best_class = structure_analysis['topClassGroups'][0]['className']
            print(f"\n=== Recommended selector ===")
            print(f"Use the class: {best_class[:100]}")

            # Build a usable selector
            class_parts = best_class.split()[:3]
            selector = 'div.' + '.'.join(class_parts)
            print(f"CSS Selector: {selector}")

            count = await page.evaluate(f'document.querySelectorAll("{selector}").length')
            print(f"Elements matched: {count}")

        await asyncio.sleep(2)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(debug_ad_library())
