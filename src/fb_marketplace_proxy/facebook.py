import json
from typing import Any
from typing import NamedTuple

import requests


class FacebookAuthCookies(NamedTuple):
    c_user: str
    xs: str


class FacebookApiError(Exception):
    pass


class FacebookClient:
    def __init__(self, auth_cookies: FacebookAuthCookies | None = None):
        self.auth_cookies: FacebookAuthCookies | None = auth_cookies

    def _graphql_query(
        self,
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
                "c_user": self.auth_cookies.c_user,
                "xs": self.auth_cookies.xs,
            }
            if self.auth_cookies is not None
            else None,
        )

        response_json = response.json()
        if "data" not in response_json:
            if "errors" in response_json:
                raise FacebookApiError(
                    ", ".join(
                        error.get("message", "") for error in response_json["errors"]
                    )
                )
            else:
                raise FacebookApiError("No data in GraphQL response")

        return response_json["data"]

    def CometMarketplaceSearchContentContainerQuery(
        self, query: str, cursor: str | None
    ):
        return self._graphql_query(
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

    def MarketplacePDPC2CMediaViewerWithImagesQuery(self, listing_id: int):
        return self._graphql_query(
            10059604367394414,
            {
                "targetId": listing_id,
            },
        )

    def MarketplacePDPContainerQuery(self, listing_id: int):
        return self._graphql_query(
            26002077532790480,
            {
                "targetId": listing_id,
            },
        )
