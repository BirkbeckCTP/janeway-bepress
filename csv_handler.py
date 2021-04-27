"""
Collection of functions for handling of a bepress CSV

Missing Metadata:
 - DOI
 - Submission Date
 - Metadata


"""
import pathlib

from bs4 import BeautifulSoup
import requests
from django.template.loader import render_to_string
from utils.logger import get_logger

from plugins.bepress.plugin_settings import BEPRESS_PATH

logger = get_logger(__name__)


AUTHOR_FIELDS_MAP = {
    ('author%d_fname', 'first_name'),
    ('author%d_mname', 'middle_name'),
    ('author%d_lname', 'last_name'),
    ('author%d_suffix', 'salutation'),
    ('author%d_email', 'email'),
    ('author%d_institution', 'institution'),
    ('author%d_is_corporate', 'is_corporate'),
}


def csv_to_xml(reader, commit=True):
    """Converts a Bepress CSV Batch into Bepress XML format

    :param reader: A csv.DictReader
    :param commit: If true, the metadata is persisted to disk.
    :return (tuple):
    """
    for row in reader:
        parsed = parse_row(row)
        xml = render_xml(parsed)
        id = row.get("article_id") or row["context_key"]
        file_path = pathlib.Path(BEPRESS_PATH, row["issue"], id, "metadata.xml")
        if commit:
            logger.info("Writing to %s", file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(str(file_path), "w") as xml_file:
                xml_file.write(xml)
        else:
            print(xml)


def render_xml(parsed):
    """Render Bepress XML metadata from the given context
    :param parsed: Dict representation of an article's metadata
    :return: A rendered django Template of the metadata in XML format
    """
    template = 'bepress/xml/metadata.xml'
    context = {"article": parsed}
    return render_to_string(template, context)


def parse_row(row):
    """Parse the given Bepress CSV Row data into a dictionary
    :param row: Dict of a CSV Row:
    :return: Dict of the parsed data
    """
    article_dict = parse_article_metadata(row)
    article_dict["authors"] = parse_authors(row)
    return article_dict


def parse_article_metadata(row):
    """Parse the given Bepress CSV Row data into a dictionary
    :param row: Dict of a CSV Row:
    :return: Dict of the parsed article metadata
    """
    return dict(
        row,
        keywords=row['disciplines'].split(";"),
        fulltext_url=get_fulltext_url(row),
        article_id=row['context_key'],
        language=row.get('language', 'en'),
        peer_reviewed=row.get('peer_reviewed', False),
    )


def parse_authors(row):
    """ Parse author data from the given row into a nested mapping
    The bepress CSV exposes all authors in a single row, by adding an
    index to each column (e.g author1_fname, author2_fname). The indexes
    range from 1 to 5 and are present even with blank
    :param row: Dict of a CSV Row:
    :return: Dict of the parsed author metadata
    """
    authors = []
    for author_index in range(1,6):
        author = {}
        for src, dest in AUTHOR_FIELDS_MAP:
            if row.get(src % author_index):
                author[dest] = row[src % author_index]
        if author:
            # If not all fields were blank
            authors.append(author)
        else:
            # If author is blank, no point checking the next indexes
            break
    return authors


def get_fulltext_url(row, unstamped=True, scrape=True):
    """ Parse the given Bepress CSV Row and retrieve the fulltext PDF url
    If no fulltext url is found, we try to scrape it from the article page
    :param row: Dict of a CSV Row:
    :param row: (bool) Return URL to the stamped version of the PDF
    :param row: (bool) Attempt to scrape fulltext URL from remote article
    :return: URL of the fulltext file
    """
    url = row.get("fulltext_url")
    if not url and scrape and row.get("calc_url"):
        try:
            logger.info("Fetching article from %s", row["calc_url"])
            response = requests.get(row["calc_url"])
        except requests.exceptions.RequestException as exc:
            logger.warning("Failed to extract PDF URL: %s", exc)
        else:
            if response.ok:
                soup = BeautifulSoup(response.text, "html.parser")
                anchor_tag = soup.find("a", id="pdf")
                if anchor_tag:
                    url = anchor_tag.attrs["href"]
                    logger.debug("Extracted fulltext url %s", url)
                else:
                    logger.warning("No fulltext url found")

    if url and unstamped:
        if "?" in url:
            url += "&unstamped=1"
        else:
            url += "?unstamped=1"

    return url
