from __future__ import annotations

from src.core import Item, Request
from src.crawler.classifier import Classifier
from conftest import make_response

HTML = """
<html>
  <head>
    <meta name="section" content="股市">
    <meta property="article:section" content="財經">
    <meta name="news_keywords" content="台股,科技股,國銀">
    <script type="application/ld+json">
      {"@context": "https://schema.org", "@type": "BreadcrumbList",
       "itemListElement": [
         {"@type": "ListItem", "position": 1, "name": "首頁"},
         {"@type": "ListItem", "position": 2, "name": "股市"},
         {"@type": "ListItem", "position": 3, "name": "股市要聞"}
       ]}
    </script>
  </head>
  <body>
    <nav class="breadcrumb">
      <a class="breadcrumb-item">首頁</a>
      <a class="breadcrumb-item">股市</a>
    </nav>
  </body>
</html>
"""


def make_data(**kw) -> dict:
    data = {"title": "台股早盤開高", "content": "加權指數大漲", "url": "https://udn.com/news/story/7251/9700553"}
    data.update(kw)
    return data


def make_response_with_list_data(url: str = "https://udn.com/news/story/7251/9700553", list_data: dict | None = None) -> object:
    request = Request(url=url, callback="parse_article")
    if list_data is not None:
        request.meta["list_data"] = list_data
    response = make_response(url, HTML, 200)
    response.request = request
    return response


def classify_categories(classifier, url="https://udn.com/x", html=HTML, data=None):
    categories, _, _ = classifier.classify(make_response(url, html), data or make_data())
    return categories


def classify_tags(classifier, url="https://udn.com/x", html=HTML, data=None):
    _, _, tags = classifier.classify(make_response(url, html), data or make_data())
    return tags


class TestCategory:
    def test_meta_name_source(self):
        classifier = Classifier({"category": {"sources": [{"type": "meta", "name": "section"}]}})
        assert classify_categories(classifier) == ["股市"]

    def test_meta_property_source(self):
        classifier = Classifier({"category": {"sources": [{"type": "meta", "property": "article:section"}]}})
        assert classify_categories(classifier) == ["財經"]

    def test_url_source_with_mapping(self):
        classifier = Classifier(
            {
                "category": {
                    "sources": [
                        {
                            "type": "url",
                            "regex": "/story/(\\d+)/",
                            "mapping": {"7251": "股市", "6656": "政治"},
                        }
                    ]
                }
            }
        )
        assert classify_categories(classifier, url="https://udn.com/news/story/7251/9700553") == ["股市"]

    def test_url_source_without_mapping_returns_raw(self):
        classifier = Classifier({"category": {"sources": [{"type": "url", "regex": "/story/(\\d+)/"}]}})
        assert classify_categories(classifier, url="https://udn.com/news/story/7251/9700553") == ["7251"]

    def test_url_source_no_match_returns_default(self):
        classifier = Classifier({"category": {"sources": [{"type": "url", "regex": "/story/(\\d+)/"}], "default": "其他"}})
        assert classify_categories(classifier, url="https://udn.com/not-a-story") == ["其他"]

    def test_selector_source(self):
        classifier = Classifier({"category": {"sources": [{"type": "selector", "selector": "a.breadcrumb-item", "attr": "text"}]}})
        assert classify_categories(classifier) == ["首頁"]

    def test_selector_source_with_join(self):
        classifier = Classifier(
            {"category": {"sources": [{"type": "selector", "selector": "a.breadcrumb-item", "attr": "text", "join": ">"}]}}
        )
        assert classify_categories(classifier) == ["首頁>股市"]

    def test_json_ld_source(self):
        classifier = Classifier({"category": {"sources": [{"type": "json_ld", "path": "itemListElement.1.name"}]}})
        assert classify_categories(classifier) == ["股市"]

    def test_list_data_source(self):
        classifier = Classifier({"category": {"sources": [{"type": "list_data", "path": "cate_id"}]}})
        response = make_response_with_list_data(list_data={"cate_id": "6656"})
        categories, _, _ = classifier.classify(response, make_data())
        assert categories == ["6656"]

    def test_article_json_source(self):
        classifier = Classifier({"category": {"sources": [{"type": "article_json", "path": "data.category"}]}})
        assert classify_categories(classifier, html='{"data": {"category": "國際"}}') == ["國際"]

    def test_keyword_source_hit(self):
        classifier = Classifier(
            {
                "category": {
                    "sources": [
                        {
                            "type": "keyword",
                            "rules": [
                                {"keywords": ["台股", "股市"], "value": "財經"},
                                {"keywords": ["棒球"], "value": "體育"},
                            ],
                        }
                    ]
                }
            }
        )
        assert classify_categories(classifier) == ["財經"]

    def test_keyword_source_miss_returns_default(self):
        classifier = Classifier(
            {
                "category": {
                    "sources": [{"type": "keyword", "rules": [{"keywords": ["棒球"], "value": "體育"}]}],
                    "default": "其他",
                }
            }
        )
        assert classify_categories(classifier) == ["其他"]

    def test_multiple_sources_accumulate(self):
        classifier = Classifier(
            {
                "category": {
                    "sources": [
                        {"type": "meta", "name": "section"},
                        {"type": "meta", "property": "article:section"},
                    ]
                }
            }
        )
        assert classify_categories(classifier) == ["股市", "財經"]

    def test_duplicate_values_deduplicated(self):
        classifier = Classifier(
            {
                "category": {
                    "sources": [
                        {"type": "meta", "name": "section"},
                        {"type": "json_ld", "path": "itemListElement.1.name"},
                    ]
                }
            }
        )
        assert classify_categories(classifier) == ["股市"]

    def test_no_category_config_returns_empty(self):
        classifier = Classifier({})
        assert classify_categories(classifier) == []

    def test_default_used_when_all_sources_miss(self):
        classifier = Classifier(
            {
                "category": {
                    "sources": [{"type": "url", "regex": "/story/(\\d+)/"}],
                    "default": "其他",
                }
            }
        )
        assert classify_categories(classifier) == ["其他"]


class TestNormalizedCategory:
    def test_normalization_applied(self):
        classifier = Classifier(
            {"category": {"sources": [{"type": "meta", "name": "section"}]}},
            category_normalization={"股市": "財經"},
        )
        _, normalized, _ = classifier.classify(make_response("https://udn.com/x", HTML), make_data())
        assert normalized == ["財經"]

    def test_normalization_unmatched_keeps_raw(self):
        classifier = Classifier(
            {"category": {"sources": [{"type": "meta", "name": "section"}]}},
            category_normalization={"科技": "科技"},
        )
        _, normalized, _ = classifier.classify(make_response("https://udn.com/x", HTML), make_data())
        assert normalized == ["股市"]

    def test_normalization_applied_per_value(self):
        classifier = Classifier(
            {
                "category": {
                    "sources": [
                        {"type": "meta", "name": "section"},
                        {"type": "meta", "property": "article:section"},
                    ]
                }
            },
            category_normalization={"股市": "財經", "財經": "財經"},
        )
        _, normalized, _ = classifier.classify(make_response("https://udn.com/x", HTML), make_data())
        assert normalized == ["財經"]

    def test_no_normalization_returns_same(self):
        classifier = Classifier({"category": {"sources": [{"type": "meta", "name": "section"}]}})
        _, normalized, _ = classifier.classify(make_response("https://udn.com/x", HTML), make_data())
        assert normalized == ["股市"]

    def test_default_normalized(self):
        classifier = Classifier(
            {"category": {"sources": [{"type": "url", "regex": "/nope/(\\d+)/"}], "default": "其他"}},
            category_normalization={"其他": "未分類"},
        )
        _, normalized, _ = classifier.classify(make_response("https://udn.com/x", HTML), make_data())
        assert normalized == ["未分類"]


class TestTags:
    def test_meta_source_with_split(self):
        classifier = Classifier({"tags": {"sources": [{"type": "meta", "name": "news_keywords", "split": ","}]}})
        assert classify_tags(classifier) == ["台股", "科技股", "國銀"]

    def test_meta_source_without_split_single_tag(self):
        classifier = Classifier({"tags": {"sources": [{"type": "meta", "name": "section"}]}})
        assert classify_tags(classifier) == ["股市"]

    def test_keyword_source_all_matching_rules(self):
        classifier = Classifier(
            {
                "tags": {
                    "sources": [
                        {
                            "type": "keyword",
                            "rules": [
                                {"keywords": ["台股"], "value": "台股"},
                                {"keywords": ["大漲", "開高"], "value": "股市"},
                                {"keywords": ["棒球"], "value": "體育"},
                            ],
                        }
                    ]
                }
            }
        )
        assert classify_tags(classifier) == ["台股", "股市"]

    def test_multiple_sources_accumulate_and_dedupe(self):
        classifier = Classifier(
            {
                "tags": {
                    "sources": [
                        {"type": "meta", "name": "news_keywords", "split": ","},
                        {"type": "meta", "name": "section"},
                    ]
                }
            }
        )
        assert classify_tags(classifier) == ["台股", "科技股", "國銀", "股市"]

    def test_no_tags_config_returns_empty(self):
        classifier = Classifier({})
        assert classify_tags(classifier) == []

    def test_article_json_source_array(self):
        classifier = Classifier({"tags": {"sources": [{"type": "article_json", "path": "data.tags"}]}})
        assert classify_tags(classifier, html='{"data": {"tags": ["a", "b"]}}') == ["a", "b"]

    def test_source_without_match_skipped(self):
        classifier = Classifier({"tags": {"sources": [{"type": "url", "regex": "/nope/(\\d+)/"}]}})
        assert classify_tags(classifier) == []


class TestMapping:
    def test_mapping_applied_to_meta(self):
        classifier = Classifier({"category": {"sources": [{"type": "meta", "name": "section", "mapping": {"股市": "金融"}}]}})
        assert classify_categories(classifier) == ["金融"]

    def test_mapping_missing_key_keeps_raw(self):
        classifier = Classifier({"category": {"sources": [{"type": "meta", "name": "section", "mapping": {"未知": "X"}}]}})
        assert classify_categories(classifier) == ["股市"]

    def test_mapping_applied_to_tags(self):
        classifier = Classifier(
            {"tags": {"sources": [{"type": "meta", "name": "news_keywords", "split": ",", "mapping": {"台股": "TWSE"}}]}}
        )
        assert classify_tags(classifier) == ["TWSE", "科技股", "國銀"]


class TestRobustness:
    def test_malformed_json_ld_skipped(self):
        html = '<html><head><script type="application/ld+json">{not valid</script></head></html>'
        classifier = Classifier({"category": {"sources": [{"type": "json_ld", "path": "itemListElement.1.name"}]}})
        assert classify_categories(classifier, html=html) == []

    def test_unknown_source_type_logs_and_skips(self):
        classifier = Classifier({"category": {"sources": [{"type": "bogus", "foo": "bar"}], "default": "其他"}})
        assert classify_categories(classifier) == ["其他"]

    def test_meta_missing_on_page_returns_empty(self):
        classifier = Classifier({"category": {"sources": [{"type": "meta", "name": "nonexistent"}]}})
        assert classify_categories(classifier) == []

    def test_keyword_matches_content_not_only_title(self):
        classifier = Classifier(
            {
                "category": {
                    "sources": [
                        {
                            "type": "keyword",
                            "rules": [{"keywords": ["加權指數"], "value": "財經"}],
                        }
                    ]
                }
            }
        )
        assert classify_categories(classifier) == ["財經"]

    def test_item_integration(self):
        classifier = Classifier(
            {
                "category": {"sources": [{"type": "meta", "name": "section"}], "default": "其他"},
                "tags": {"sources": [{"type": "meta", "name": "news_keywords", "split": ","}]},
            }
        )
        item = Item(data=make_data(), source="udn", url="https://udn.com/news/story/7251/9700553")
        categories, normalized, tags = classifier.classify(make_response(item.url, HTML), item.data)
        assert categories == ["股市"]
        assert normalized == ["股市"]
        assert tags == ["台股", "科技股", "國銀"]
