"""Command line entry point for web-harvester."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .core import build_engine
from .crawler import SiteCrawler
from .utils import Settings, setup_logging
from .utils.config import (
    ConfigDirNotFound,
    ConfigValidationError,
    PathLike,
    get_all_site_ids,
    load_site_config,
    resolve_config_dir,
)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid int value: {value!r}")
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer (>= 1)")
    return parsed


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid float value: {value!r}")
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive number (> 0)")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="web-harvester",
        description="設定檔驅動的新聞爬蟲入口",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "-s",
        "--site",
        metavar="NAME",
        help="要爬取的站點 ID（對應 <config-dir>/sites/<NAME>.yaml）",
    )
    target.add_argument(
        "-a",
        "--all-sites",
        action="store_true",
        help="依序爬取設定目錄下的所有站點",
    )
    target.add_argument(
        "-l",
        "--list-sites",
        action="store_true",
        help="列出所有可用的站點後退出",
    )
    parser.add_argument(
        "--config-dir",
        metavar="DIR",
        help="設定目錄（含 settings.yaml、sites/、schema/）；預設由目前目錄向上尋找",
    )
    parser.add_argument(
        "-k",
        "--keyword",
        metavar="KW",
        help="關鍵字搜尋（需站點設定 sources）",
    )
    parser.add_argument(
        "-c",
        "--category",
        metavar="CAT",
        help="分類篩選（需站點設定 categories）",
    )
    parser.add_argument(
        "--max-items",
        type=_positive_int,
        metavar="N",
        help="覆寫 limits.max_items：收集達此數量即停止（>= 1）",
    )
    parser.add_argument(
        "--max-pages",
        type=_positive_int,
        metavar="N",
        help="覆寫 limits.max_pages：爬取列表頁數上限（>= 1）",
    )
    parser.add_argument(
        "--stop-on-duplicate",
        action=argparse.BooleanOptionalAction,
        help="覆寫 limits.stop_on_duplicate：遇到重複 URL 即停止（預設沿用設定值）",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        metavar="SEC",
        help="覆寫 limits.timeout：整體爬取逾時秒數（> 0）",
    )
    parser.add_argument(
        "--skip-seen",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="覆寫 engine.skip_seen_urls：已存在於資料庫的 URL 是否跳過（預設沿用設定值）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只請求列表頁並統計可抓文章數，不抓文章頁、不寫入資料",
    )
    return parser


def build_cli_limits(args: argparse.Namespace) -> Dict[str, Any]:
    """Extract the limits overridden by CLI args, only including specified keys.

    Absent flags (None) are omitted so they do not override config defaults.
    """
    limits: Dict[str, Any] = {}
    if args.max_items is not None:
        limits["max_items"] = args.max_items
    if args.max_pages is not None:
        limits["max_pages"] = args.max_pages
    if args.stop_on_duplicate is not None:
        limits["stop_on_duplicate"] = args.stop_on_duplicate
    if args.timeout is not None:
        limits["timeout"] = args.timeout
    return limits


def list_sites(config_dir: Optional[PathLike] = None) -> int:
    """Print the available site IDs.

    Returns:
        int: 0 when at least one site exists, 1 otherwise.
    """
    site_ids = get_all_site_ids(config_dir=config_dir)
    if not site_ids:
        print("No site configs found.", file=sys.stderr)
        return 1
    print("Available sites:")
    for site_id in site_ids:
        print(f"  {site_id}")
    return 0


def _build_crawler(site_config: Dict[str, Any], settings: Settings, args: argparse.Namespace) -> SiteCrawler:
    return SiteCrawler(
        site_config,
        category_normalization=settings.get("category_normalization"),
        keyword=args.keyword,
        category=args.category,
        default_limits=settings.get("limits"),
        limit_overrides=build_cli_limits(args),
    )


def _run_site(
    site_id: str,
    site_config: Dict[str, Any],
    settings: Settings,
    args: argparse.Namespace,
) -> Tuple[int, int]:
    """Crawl a single site.

    Returns:
        Tuple[int, int]: Number of collected items and the number of article
        pages skipped by a dry run.
    """
    engine = build_engine(settings, skip_seen_urls=args.skip_seen, dry_run=args.dry_run)
    items = engine.run(_build_crawler(site_config, settings, args))
    return len(items), engine.skipped_articles


def _load_site_configs(
    site_ids: Sequence[str],
    config_dir: Path,
    parser: argparse.ArgumentParser,
    *,
    strict: bool,
) -> Dict[str, Dict[str, Any]]:
    """Load site configurations.

    Args:
        site_ids: Site IDs to load.
        config_dir: Resolved configuration directory.
        parser: Parser used to report usage errors.
        strict: When true a missing or invalid site aborts the process; when
            false the site is reported and skipped.

    Returns:
        Dict[str, Dict[str, Any]]: Successfully loaded site configurations.
    """
    loaded: Dict[str, Dict[str, Any]] = {}
    for site_id in site_ids:
        try:
            loaded[site_id] = load_site_config(site_id, config_dir=config_dir)
        except FileNotFoundError:
            message = f"site '{site_id}' not found in {config_dir / 'sites'}"
            if strict:
                parser.error(message)
            print(f"Skipping {site_id}: {message}", file=sys.stderr)
        except ConfigValidationError as e:
            message = f"invalid config for site '{site_id}': {e}"
            if strict:
                parser.error(message)
            print(f"Skipping {site_id}: {message}", file=sys.stderr)
    return loaded


def _print_summary(results: List[Tuple[str, int, int]], *, dry_run: bool) -> None:
    """Print a per-site summary for a multi-site run."""
    print("Crawl summary:")
    total_items = 0
    total_dry = 0
    for site_id, item_count, dry_count in results:
        total_items += item_count
        total_dry += dry_count
        if dry_run:
            print(f"  {site_id:<16} articles={dry_count}")
        else:
            print(f"  {site_id:<16} items={item_count}")
    if dry_run:
        print(f"  {'total':<16} articles={total_dry}")
    else:
        print(f"  {'total':<16} items={total_items}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config_dir = resolve_config_dir(args.config_dir)
    except ConfigDirNotFound as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    if args.list_sites:
        return list_sites(config_dir)

    settings = Settings(config_dir=config_dir)
    setup_logging(
        level=settings.get("logging.level", "INFO"),
        log_format=settings.get("logging.format"),
        log_file=settings.get("logging.file"),
        max_bytes=settings.get("logging.max_bytes", 10 * 1024 * 1024),
        backup_count=settings.get("logging.backup_count", 5),
    )

    if args.all_sites:
        site_ids: List[str] = get_all_site_ids(config_dir=config_dir)
    else:
        if args.site is None:  # pragma: no cover - argparse enforces this
            parser.error("missing --site")
        site_ids = [args.site]
    if not site_ids:
        print("No site configs found.", file=sys.stderr)
        return 1

    site_configs = _load_site_configs(site_ids, config_dir, parser, strict=not args.all_sites)
    if not site_configs:
        return 1

    results: List[Tuple[str, int, int]] = []
    for site_id, site_config in site_configs.items():
        item_count, dry_count = _run_site(site_id, site_config, settings, args)
        results.append((site_id, item_count, dry_count))
        if args.dry_run and not args.all_sites:
            print(
                f"Dry run finished: {dry_count} article page(s) would be fetched, "
                f"{item_count} item(s) stored."
            )

    if args.all_sites:
        _print_summary(results, dry_run=args.dry_run)

    failed = args.all_sites and len(site_configs) < len(site_ids)
    return 1 if failed else 0
