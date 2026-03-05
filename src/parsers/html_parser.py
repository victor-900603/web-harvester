from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from bs4 import BeautifulSoup, Tag


class HTMLParser:
    """A HTML parser that uses BeautifulSoup to extract data from HTML content.
    
    Args:
        html (str): The HTML content to parse.
        parser (str): The parser to use with BeautifulSoup ("lxml" | "html.parser" | "html5lib").
    
    """
    
    def __init__(self, html: str, parser: str = "lxml") -> None:
        self.soup = BeautifulSoup(html, parser)
        
    def select(self, selector: str) -> List[Tag]:
        """Select elements from the HTML using a CSS selector.
        
        Args:
            selector (str): The CSS selector to use for selecting elements.
        
        Returns:
            List[Tag]: A list of BeautifulSoup Tag objects that match the selector.
        """
        return self.soup.select(selector)
    
    def select_one(self, selector: str) -> Optional[Tag]:
        """Select the first element from the HTML that matches the CSS selector.
        
        Args:
            selector (str): The CSS selector to use for selecting the element.
            
        Returns:
            Optional[Tag]: The first BeautifulSoup Tag object that matches the selector, or None if no match is found.
        """
        return self.soup.select_one(selector)
    
    def extract_text(self, selector: str, strip: bool = True) -> Optional[str]:
        """Extract the text content from a BeautifulSoup Tag element.
        
        Args:
            selector (str): The CSS selector to use for selecting the element.
            strip (bool): Whether to strip whitespace from the extracted text.
            
        Returns:
            Optional[str]: The extracted text content, or None if the element is None.
        """
        element = self.select_one(selector)
        return element.get_text(strip=strip) if element else None
    
    def extract_attribute(self, selector: str, attribute: str) -> Optional[str]:
        """Extract the value of a specific attribute from a BeautifulSoup Tag element.
        
        Args:
            selector (str): The CSS selector to use for selecting the element.
            attribute (str): The name of the attribute to extract.
            
        Returns:
            Optional[str]: The value of the specified attribute, or None if the element or attribute is not found.
        """
        element = self.select_one(selector)
        value = element.get(attribute) if element else None
        return " ".join(value) if isinstance(value, list) else value
    
    def extract(self, selector: str, attribute: Optional[str] = None) -> Optional[str]:
        """Extract data from the HTML based on the provided selector and attribute.
        
        Args:
            selector (str): The CSS selector to use for selecting the element.
            attribute (Optional[str]): The attribute to extract. If None, defaults to "text". 
                Supported values: "text", "outer_html" (or "html"), "inner_html", or any specific attribute name.
                
        Returns:
            Optional[str]: The extracted data based on the specified attribute, or None if the element is not found.
        """
        
        if attribute == "text":
            return self.extract_text(selector)
        elif attribute == "outer_html" or attribute == "html":
            el = self.select_one(selector)
            return str(el) if el else None
        elif attribute == "inner_html":
            el = self.select_one(selector)
            return el.decode_contents() if el else None
        else:
            return self.extract_attribute(selector, attribute)
        
    def extract_all_text(self, selector: str, sep: str = " ", strip: bool = True) -> Optional[str]:
        """Extract and concatenate the text content from all elements that match the CSS selector.
        
        Args:
            selector (str): The CSS selector to use for selecting elements.
            sep (str): The separator to use when concatenating multiple text contents.
            strip (bool): Whether to strip whitespace from each extracted text content.
            
        Returns:
            Optional[str]: The concatenated text content, or None if no elements are found.
        """
        elements = self.select(selector)
        if not elements:
            return None
        texts = [el.get_text(strip=strip) for el in elements]
        return sep.join(texts) if texts else None