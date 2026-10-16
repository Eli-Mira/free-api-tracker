"""Main entry point for the Free LLM API Tracker."""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add tracker-core to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tracker-core" / "src"))

from tracker_core.schema import Provider, VerificationStatus
from tracker_core.adapters.seed import create_seed_providers, SEED_PROVIDERS
from tracker_core.adapters.google_ai_studio import GoogleAIStudioAdapter
from tracker_core.scheduler import TrackerScheduler
from tracker_core.reporter_html import get_html_reporter
from tracker_core.store import ProviderStorage
from tracker_core.cache import FileCache
from tracker_core.discovery import DiscoveryEngine, run_discovery


logger = logging.getLogger(__name__)


class FreeAPITracker:
    """Main tracker for free LLM API providers."""

    def __init__(
        self,
        data_dir: Path | str = "./data",
        cache_dir: Path | str = "./.cache",
        reports_dir: Path | str = "./reports",
        theme: str = "default"
    ):
        self.data_dir = Path(data_dir)
        self.cache_dir = Path(cache_dir)
        self.reports_dir = Path(reports_dir)
        self.theme = theme

        # Initialize components
        self.storage = ProviderStorage(self.data_dir)
        self.cache = FileCache(self.cache_dir)
        self.reporter = get_html_reporter(theme)

        # Load or create seed providers
        self.providers: list[Provider] = []
        self._load_or_create_seed()

    def _load_or_create_seed(self) -> None:
        """Load providers from storage or create from seed."""
        loaded = asyncio.run(self.storage.load())

        if loaded:
            self.providers = loaded
            logger.info(f"Loaded {len(self.providers)} providers from storage")
        else:
            # Create from seed
            seed_data = create_seed_providers()
            self.providers = [Provider(**p) for p in seed_data]
            logger.info(f"Created {len(self.providers)} seed providers")
            asyncio.run(self.storage.save(self.providers))

    async def check_providers(self) -> list[Provider]:
        """Check all providers for updates."""
        changed = []

        for provider in self.providers:
            try:
                # Get adapter for this provider
                adapter = self._get_adapter(provider)
                if adapter is None:
                    continue

                # Fetch and check for changes
                raw = await asyncio.to_thread(adapter.fetch)

                # Check if content changed
                if self.cache.has_changed(provider.name, raw.content):
                    logger.info(f"Provider {provider.name} has changes")
                    provider.needs_review = True
                    provider.last_checked = datetime.now(timezone.utc)

                    # Parse and update
                    parsed = adapter.parse(raw)
                    if parsed:
                        provider.content_hash = parsed[0].content_hash
                        provider.free_tier_details = parsed[0].free_tier_details

                    # Update cache
                    self.cache.save_with_hash(
                        provider.name,
                        raw.content,
                        {"last_fetched": str(datetime.now(timezone.utc))}
                    )

                    changed.append(provider)
                else:
                    provider.last_checked = datetime.now(timezone.utc)

            except Exception as e:
                logger.error(f"Failed to check {provider.name}: {e}")

        return changed

    def _get_adapter(self, provider: Provider):
        """Get adapter for a provider based on name."""
        name = provider.name.lower()

        if "google" in name or "ai studio" in name:
            return GoogleAIStudioAdapter()

        # Add more adapters here as they're built
        logger.warning(f"No adapter found for {provider.name}")
        return None

    async def run_check(self) -> dict[str, Any]:
        """Run a full check cycle."""
        logger.info("Starting provider check...")

        changed = await self.check_providers()
        await self.storage.save(self.providers)

        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_providers": len(self.providers),
            "changed": len(changed),
            "needs_review": sum(1 for p in self.providers if p.needs_review),
            "verified": sum(1 for p in self.providers if p.status == VerificationStatus.VERIFIED),
            "changes": [p.name for p in changed]
        }

        logger.info(f"Check complete: {result['changed']} changes, {result['needs_review']} need review")
        return result

    async def discover_new(self) -> list[dict[str, Any]]:
        """Run discovery engine to find new providers."""
        logger.info("Running discovery engine...")

        candidates = await run_discovery(
            providers=self.providers,
            output_path=self.reports_dir / "discovery_candidates.json"
        )

        logger.info(f"Discovery found {len(candidates)} new candidates")
        return candidates

    def generate_report(
        self,
        output_path: Path | str | None = None
    ) -> str:
        """Generate HTML report."""
        api_items = []
        for p in self.providers:
            api_items.append({
                "name": p.name,
                "status": p.status.value if hasattr(p.status, "value") else str(p.status),
                "description": self._format_description(p)
            })

        output_path = output_path or self.reports_dir / f"report_{datetime.utcnow().strftime('%Y%m%d')}.html"

        html = self.reporter.render(
            api_items=api_items,
            news_items=[],  # Empty for API tracker
            report_date=datetime.utcnow().strftime("%Y-%m-%d"),
            generated_at=datetime.utcnow().strftime("%H:%M UTC"),
            persona_image_url=None
        )

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(html, encoding="utf-8")
            logger.info(f"Report saved to {output_path}")

        return html

    def _format_description(self, provider: Provider) -> str:
        """Format provider description."""
        parts = []

        if provider.free_tier_details:
            details = provider.free_tier_details
            if "rate_limit" in details:
                parts.append(f"Rate limit: {details['rate_limit']}")
            if "models" in details:
                models = details["models"]
                if isinstance(models, list):
                    parts.append(f"Models: {', '.join(models[:3])}" + ("..." if len(models) > 3 else ""))
                else:
                    parts.append(f"Models: {models}")

        if provider.tags:
            parts.append(f"Tags: {', '.join(provider.tags)}")

        return " | ".join(parts) if parts else "No details available"

    def list_providers(self) -> list[dict]:
        """List all providers with their status."""
        return [
            {
                "name": p.name,
                "status": p.status.value if hasattr(p.status, "value") else str(p.status),
                "region": p.region,
                "needs_review": p.needs_review,
                "last_checked": p.last_checked.isoformat() if p.last_checked else None
            }
            for p in self.providers
        ]

    def verify_provider(self, name: str) -> bool:
        """Mark a provider as verified."""
        for p in self.providers:
            if p.name.lower() == name.lower():
                p.status = VerificationStatus.VERIFIED
                p.needs_review = False
                p.last_verified = datetime.now(timezone.utc)
                asyncio.run(self.storage.save(self.providers))
                return True
        return False

    def mark_for_review(self, name: str) -> bool:
        """Mark a provider for manual review."""
        for p in self.providers:
            if p.name.lower() == name.lower():
                p.needs_review = True
                asyncio.run(self.storage.save(self.providers))
                return True
        return False


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Free LLM API Tracker")
    parser.add_argument("action", choices=["check", "report", "list", "verify", "discover"], help="Action to perform")
    parser.add_argument("--theme", choices=["default", "lain"], default="default", help="Report theme")
    parser.add_argument("--name", help="Provider name for verify action")
    parser.add_argument("--data-dir", default="./data", help="Data directory")
    parser.add_argument("--reports-dir", default="./reports", help="Reports directory")

    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create tracker
    tracker = FreeAPITracker(
        data_dir=args.data_dir,
        reports_dir=args.reports_dir,
        theme=args.theme
    )

    # Execute action
    if args.action == "check":
        result = asyncio.run(tracker.run_check())
        print(f"Check complete: {result['changed']} changes found")
        print(f"Providers needing review: {result['needs_review']}")

    elif args.action == "report":
        html = tracker.generate_report()
        print(f"Report generated ({len(html)} bytes)")

    elif args.action == "list":
        providers = tracker.list_providers()
        print(f"\n{'Name':<30} {'Status':<15} {'Region':<10} {'Review':<8}")
        print("-" * 70)
        for p in providers:
            print(f"{p['name']:<30} {p['status']:<15} {p['region'] or 'N/A':<10} {str(p['needs_review']):<8}")

    elif args.action == "verify" and args.name:
        if tracker.verify_provider(args.name):
            print(f"Verified: {args.name}")
        else:
            print(f"Provider not found: {args.name}")
            sys.exit(1)

    elif args.action == "discover":
        candidates = asyncio.run(tracker.discover_new())
        print(f"\nDiscovered {len(candidates)} new candidates:")
        for c in candidates[:10]:
            print(f"  - {c['name']} (confidence: {c.get('confidence', 0):.2f})")
            print(f"    {c.get('reason', '')}")
