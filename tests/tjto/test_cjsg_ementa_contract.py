"""Offline contract for TJTO ``cjsg_ementa(uuid)``.

The public method calls a separate Solr endpoint (``/ementa.php?id=<uuid>``)
that returns the ementa for a single document. ``cjsg``/``cjpg`` do *not*
invoke this — only ``cjsg_ementa`` does.
"""
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.courts.tjto.download import EMENTA_URL
from tests._helpers import load_sample

_UUID_1 = "f4b3440350bb6c8e6bdd708d78c43e85"
_UUID_2 = "a9a493e88b4575de7c18f6411c49348b"


def _add_get(uuid: str) -> None:
    responses.add(
        responses.GET,
        EMENTA_URL,
        body=load_sample("tjto", f"cjsg/ementa_{uuid}.json"),
        status=200,
        content_type="application/json",
        match=[query_param_matcher({"id": uuid})],
    )


@responses.activate
def test_cjsg_ementa_returns_doc_dict():
    """``cjsg_ementa(uuid)`` returns the first ``response.docs[0]`` JSON dict."""
    _add_get(_UUID_1)

    doc = jus.scraper("tjto").cjsg_ementa(_UUID_1)

    assert isinstance(doc, dict)
    assert doc  # at least one populated field
    # The endpoint URL was hit once with the right id param.
    assert len(responses.calls) == 1
    assert responses.calls[0].request.url.endswith(f"id={_UUID_1}")


@responses.activate
def test_cjsg_ementa_handles_two_uuids_independently():
    """Two distinct UUIDs hit two distinct ementa.php URLs."""
    _add_get(_UUID_1)
    _add_get(_UUID_2)

    doc_1 = jus.scraper("tjto").cjsg_ementa(_UUID_1)
    doc_2 = jus.scraper("tjto").cjsg_ementa(_UUID_2)

    assert isinstance(doc_1, dict) and isinstance(doc_2, dict)
    assert len(responses.calls) == 2
