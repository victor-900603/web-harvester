from src.utils import Settings, load_site_config, setup_logging

from src.core import build_engine
from src.crawler import SiteCrawler

def main():
    settings = Settings()
    setup_logging(
        level=settings.get("logging.level", "INFO"),
        log_format=settings.get("logging.format"),
        log_file=settings.get("logging.file"),
        max_bytes=settings.get("logging.max_bytes", 10 * 1024 * 1024),
        backup_count=settings.get("logging.backup_count", 5),
    )

    site_config = load_site_config("udn_news")

    engine = build_engine(settings)

    crawler = SiteCrawler(site_config)
    engine.run(crawler)
    
if __name__ == "__main__":
    main()