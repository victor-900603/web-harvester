import argparse
import sys

from src.utils import Settings, get_all_site_ids, load_site_config, setup_logging

from src.core import build_engine
from src.crawler import SiteCrawler


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
        prog="main.py",
        description="設定檔驅動的新聞爬蟲入口",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-s",
        "--site",
        metavar="NAME",
        help="要爬取的站點 ID（對應 config/sites/<NAME>.yaml）",
    )
    group.add_argument(
        "-l",
        "--list-sites",
        action="store_true",
        help="列出所有可用的站點後退出",
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
    return parser


def build_cli_limits(args: argparse.Namespace) -> dict:
    """Extract the limits overridden by CLI args, only including specified keys.

    Absent flags (None) are omitted so they do not override config defaults.
    """
    limits = {}
    if args.max_items is not None:
        limits["max_items"] = args.max_items
    if args.max_pages is not None:
        limits["max_pages"] = args.max_pages
    if args.stop_on_duplicate is not None:
        limits["stop_on_duplicate"] = args.stop_on_duplicate
    if args.timeout is not None:
        limits["timeout"] = args.timeout
    return limits


def list_sites() -> int:
    site_ids = get_all_site_ids()
    if not site_ids:
        print("No site configs found.", file=sys.stderr)
        return 1
    print("Available sites:")
    for site_id in site_ids:
        print(f"  {site_id}")
    return 0


def main(argv: list | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_sites:
        return list_sites()

    try:
        site_config = load_site_config(args.site)
    except FileNotFoundError:
        parser.error(f"site '{args.site}' not found")
    except Exception:
        raise

    settings = Settings()
    setup_logging(
        level=settings.get("logging.level", "INFO"),
        log_format=settings.get("logging.format"),
        log_file=settings.get("logging.file"),
        max_bytes=settings.get("logging.max_bytes", 10 * 1024 * 1024),
        backup_count=settings.get("logging.backup_count", 5),
    )

    engine = build_engine(settings)
    crawler = SiteCrawler(
        site_config,
        category_normalization=settings.get("category_normalization"),
        keyword=args.keyword,
        category=args.category,
        default_limits=settings.get("limits"),
        limit_overrides=build_cli_limits(args),
    )
    engine.run(crawler)
    return 0


if __name__ == "__main__":
    sys.exit(main())