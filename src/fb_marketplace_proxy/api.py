import json
from datetime import datetime
from itertools import takewhile
from typing import Any

import requests


class UserViewableError(Exception):
    pass


def graphql_query(
    doc_id: int,
    variables: dict[str, object],
) -> dict[str, Any]:
    response = requests.post(
        "https://www.facebook.com/api/graphql/",
        data={
            "doc_id": doc_id,
            "variables": json.dumps(variables),
            # "fb_dtsg": "TODO",
        },
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Sec-Fetch-Site": "same-origin",
        },
        cookies={
            # "c_user": "TODO",
            # "xs": "TODO",
        },
    )

    response_json = response.json()
    if "data" not in response_json:
        if "errors" in response_json:
            raise UserViewableError(
                ", ".join(error.get("message", "") for error in response_json["errors"])
            )
        else:
            raise UserViewableError("No data in GraphQL response")

    return response_json["data"]


def search_listings(query: str, cursor: str | None = None):
    data = graphql_query(
        25360896583559734,
        {
            "count": 24,
            "cursor": cursor,
            "params": {
                "bqf": {"callsite": "COMMERCE_MKTPLACE_WWW", "query": query},
                "browse_request_params": {
                    "commerce_enable_local_pickup": True,
                    "commerce_enable_shipping": False,
                    "commerce_search_and_rp_available": True,
                    # "commerce_search_and_rp_category_id": [],
                    # "commerce_search_and_rp_condition": None,
                    # "commerce_search_and_rp_ctime_days": None,
                    # "filter_location_latitude": 37.394714355469,
                    # "filter_location_longitude": -122.07458496094,
                    # "filter_price_lower_bound": 0,
                    # "filter_price_upper_bound": 214748364700,
                    # "filter_radius_km": 65,
                    "filter_radius_km": 10,
                },
                "custom_request_params": {
                    "surface": "SEARCH",
                },
            },
        },
    )

    listing_edges = data["marketplace_search"]["feed_units"]["edges"]
    for idx, edge in enumerate(listing_edges):
        node_type = edge["node"]["__typename"]
        if node_type == "MarketplaceFeedListingStoryObject":
            continue

        assert node_type in [
            "MarketplaceSearchFeedHeader",
            "MarketplaceSearchFeedNoResults",
        ], f"unexpected node type: {node_type}"

        # We found a feed header, which marks the end of the regular search results
        listing_edges = listing_edges[:idx]
        cursor = None
        break
    else:
        if len(listing_edges) == 24:
            cursor = data["marketplace_search"]["feed_units"]["page_info"]["end_cursor"]
        else:
            # Sometimes a cursor for irrelevant results is given after the end of relevant results
            cursor = None

    listings = [edge["node"]["listing"] for edge in listing_edges]
    parsed_listings = [_extract_listing_info(listing) for listing in listings]

    return parsed_listings, cursor


def _extract_listing_info(listing: dict[str, Any]):
    try:
        try:
            price = listing["listing_price"]["formatted_amount"]
        except KeyError, TypeError:
            price = "?"

        try:
            location = listing["location"]["reverse_geocode"]["city_page"][
                "display_name"
            ]
        except KeyError, TypeError:
            location = "?"

        try:
            image = listing["primary_listing_photo"]["image"]["uri"]
        except KeyError, TypeError:
            image = ""

        return {
            "title": listing.get("marketplace_listing_title", ""),
            "image": image,
            "description": f"Price: {price}\nLocation: {location}",
            "id": listing.get("id", ""),
        }
    except AssertionError as e:
        listing_id = listing.get("id")
        return {
            "title": f"Error: {listing_id}",
            "image": "",
            "description": str(e),
            "id": listing_id,
        }


def fetch_images(listing_id: int) -> list[str]:
    data = graphql_query(
        10059604367394414,
        {
            "targetId": listing_id,
        },
    )

    listing_photos = data["viewer"]["marketplace_product_details_page"]["target"][
        "listing_photos"
    ]

    image_urls = [photo["image"]["uri"] for photo in listing_photos]
    return image_urls


def fetch_listing_details(listing_id: int):
    data = graphql_query(
        25771029242527736,
        {
            "targetId": listing_id,
        },
    )
    item = data["viewer"]["marketplace_product_details_page"]["target"]

    status = (
        "Sold"
        if item["is_sold"]
        else "Pending"
        if item["is_pending"]
        else "Live"
        if item["is_live"]
        else "?"
    )

    title = item["marketplace_listing_title"]
    attributes = {
        "Created": datetime.fromtimestamp(item["creation_time"]).isoformat(),
        "Status": status,
        # "Price": item["listing_price"]["formatted_amount_zeros_stripped"],
        # "Price": item["formatted_price"]["text"],
        "Price": f"{item['listing_price']['amount']} {item['listing_price']['currency']}",
        "Location": item["location_text"]["text"],
        **{
            attribute["attribute_name"]: attribute["label"]
            for attribute in item["attribute_data"]
        },
    }

    if item["is_shipping_offered"]:
        attributes["Shipping"] = item["formatted_shipping_price"]

    description = (
        "".join(f"{name}: {value}\n" for name, value in attributes.items())
        + "\n"
        + item["redacted_description"]["text"]
    )

    return {
        "title": title,
        "description": description,
        "images": fetch_images(listing_id),
    }
