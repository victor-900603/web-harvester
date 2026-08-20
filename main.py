import argparse
import sys

from src.utils import Settings, get_all_site_ids, load_site_config, setup_logging

from src.core import build_engine
from src.crawler import SiteCrawler


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
    return parser


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
    )
    engine.run(crawler)
    return 0


if __name__ == "__main__":
    sys.exit(main())