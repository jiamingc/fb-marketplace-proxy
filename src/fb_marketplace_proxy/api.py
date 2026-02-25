import json
from datetime import datetime
from typing import Any

import requests


class UserViewableError(Exception):
    pass


def graphql_query(doc_id: int, variables: dict[str, object]) -> dict[str, Any]:
    response = requests.post(
        "https://www.facebook.com/api/graphql/",
        data={
            "doc_id": doc_id,
            "variables": json.dumps(variables),
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


def search_listings(query: str):
    # Seems like I need to mask my request to get more than 20 results
    data = graphql_query(
        25565941223068174,
        {
            "count": 24,
            # "cursor": '',
            "params": {
                "bqf": {
                    "callsite": "COMMERCE_MKTPLACE_WWW",
                    "query": query,
                },
                "browse_request_params": {
                    "commerce_enable_local_pickup": True,
                    "commerce_enable_shipping": True,
                    "commerce_search_and_rp_available": True,
                    # "commerce_search_and_rp_category_id": [],
                    # "commerce_search_and_rp_condition": None,
                    # "commerce_search_and_rp_ctime_days": None,
                    # exclude to use my location
                    # "filter_location_latitude": 37.7793,
                    # "filter_location_longitude": -122.419,
                    # "filter_radius_km": 65,
                    # "filter_price_lower_bound": 0,
                    # "filter_price_upper_bound": 214748364700,
                },
                "custom_request_params": {
                    "surface": "SEARCH",
                },
            },
        },
    )

    # has next page, cursor
    # cursor = data["marketplace_search"]["feed_units"]["page_info"][
    #     "end_cursor"
    # ]

    listing_edges = data["marketplace_search"]["feed_units"]["edges"]
    listings = [edge["node"]["listing"] for edge in listing_edges]

    result = [
        {
            "title": listing["marketplace_listing_title"],
            "image": listing["primary_listing_photo"]["image"]["uri"],
            "description": f"Price: {listing['listing_price']['formatted_amount']}\nLocation: {listing['location']['reverse_geocode']['city_page']['display_name']}",
            "id": listing["id"],
        }
        for listing in listings
    ]
    return result


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
