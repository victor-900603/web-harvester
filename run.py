from src.utils import Settings, load_site_config, setup_logging

from src.core import build_engine
from src.crawler import SiteCrawler

def main():
    setup_logging('DEBUG')

    settings = Settings()
    site_config = load_site_config("udn_news")

    engine = build_engine(settings)

    crawler = SiteCrawler(site_config)
    engine.run(crawler)
    
if __name__ == "__main__":
    main()