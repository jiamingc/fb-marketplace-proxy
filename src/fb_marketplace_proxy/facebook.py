import json
from uuid import uuid4
from functools import cache
from typing import Any, NamedTuple, IO
import re
from enum import StrEnum, IntEnum

import requests


class FacebookAuthCookies(NamedTuple):
    c_user: int
    xs: str


class FacebookMarketplaceDeliveryType(StrEnum):
    IN_PERSON = "IN_PERSON"
    PUBLIC_MEETUP = "PUBLIC_MEETUP"
    DOOR_PICKUP = "DOOR_PICKUP"
    DOOR_DROPOFF = "DOOR_DROPOFF"


class FacebookMarketplaceCondition(StrEnum):
    NEW = "new"
    USED_LIKE_NEW = "used_like_new"
    USED_GOOD = "used_good"
    USED_FAIR = "used_fair"


class FacebookMarketplaceCategory(IntEnum):
    NONE = 0
    MISCELLANEOUS = 144248014304211
    BOOKS = 819915902202289


class FacebookApiError(Exception):
    pass


class FacebookClient:
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"

    def __init__(self, auth_cookies: FacebookAuthCookies | None = None):
        self.auth_cookies: FacebookAuthCookies | None = auth_cookies
        self.dtsg: str | None = auth_cookies and self._get_dtsg(auth_cookies)

    @classmethod
    @cache
    def _get_dtsg(cls, auth_cookies: FacebookAuthCookies) -> str:
        response = requests.get(
            "https://www.facebook.com/bookmarks",
            cookies={
                "c_user": str(auth_cookies.c_user),
                "xs": auth_cookies.xs,
            },
            headers={
                "User-Agent": cls.USER_AGENT,
                "Sec-Fetch-Mode": "navigate",
            },
            stream=True,
        )

        for line in response.iter_lines():
            match = re.search(
                b'DTSGInitialData",\\[\\],\\{"token":"(?P<token>[^"]+)"',
                line,
            )
            if match is not None:
                return match["token"].decode()

        raise FacebookApiError("Can't find dtsg")

    def _graphql_query(
        self,
        doc_id: int,
        variables: dict[str, object],
    ) -> dict[str, Any]:
        response = requests.post(
            "https://www.facebook.com/api/graphql/",
            data={
                "__a": 1,
                "__comet_req": 1,
                "doc_id": doc_id,
                "variables": json.dumps(variables),
                "fb_dtsg": self.dtsg,
            },
            headers={
                "User-Agent": self.USER_AGENT,
                "Sec-Fetch-Site": "same-origin",
            },
            cookies={
                "c_user": str(self.auth_cookies.c_user),
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
        self,
        query: str,
        latitude: float | None,
        longitude: float | None,
        cursor: str | None,
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
                        "filter_location_latitude": latitude,
                        "filter_location_longitude": longitude,
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

    def CometSettingsDropdownTriggerQuery(self):
        return self._graphql_query(
            24059733830298575,
            {
                "pageManagementNuxId": 0,
                "profileSwitcherNuxId": 0,
                "coreAppAdminProfileSwitcherNuxId": 0,
                "profileSwitcherAdminEducationNuxId": 0,
                "showNewToast": False,
            },
        )

    def CometMarketplaceMessageSellerMutation(self, listing_id: int, message: str):
        return self._graphql_query(
            29483122031334726,
            {
                "input": {
                    "listing_id": listing_id,
                    "message": message,
                    "actor_id": self.auth_cookies and self.auth_cookies.c_user,
                }
            },
        )

    def useCometMarketplaceListingCreateMutation(
        self,
        title: str,
        description: str,
        photo_ids: list[int],
        price: int,
        condition: FacebookMarketplaceCondition,
        delivery_types: list[FacebookMarketplaceDeliveryType],
        latitude: float,
        longitude: float,
    ):
        return self._graphql_query(
            9551550371629242,
            {
                "input": {
                    "actor_id": self.auth_cookies and self.auth_cookies.c_user,
                    "client_mutation_id": "0",
                    "audience": {"marketplace": {"marketplace_id": "1663689853903557"}},
                    "data": {
                        "common": {
                            "attribute_data_json": json.dumps({"condition": condition}),
                            "category_id": FacebookMarketplaceCategory.NONE,
                            "delivery_types": delivery_types,
                            "description": {
                                "text": description,
                            },
                            "item_price": {
                                "currency": "USD",
                                "price": price,
                            },
                            "latitude": latitude,
                            "longitude": longitude,
                            "title": title,
                            # "video_ids": [],
                            "photo_ids": photo_ids,
                        }
                    },
                }
            },
        )

    def uploadPhoto(self, image: IO[bytes]):
        response = requests.post(
            "https://upload.facebook.com/ajax/react_composer/attachments/photo/upload",
            params={"__a": "1", "fb_dtsg": self.dtsg},
            cookies=self.auth_cookies
            and {"c_user": str(self.auth_cookies.c_user), "xs": self.auth_cookies.xs},
            headers={
                "User-Agent": self.USER_AGENT,
                "Sec-Fetch-Site": "same-site",
            },
            files={
                "source": (None, "8"),
                "farr": ("blob", image),
            },
        )

        return json.loads(response.text[9:])

    def LSPlatformGraphQLLightspeedRequestQuery(self):
        # TODO make sense of what this does
        return self._graphql_query(
            9697184873702141,
            {
                "deviceId": str(uuid4()),
                "requestId": 0,
                "requestPayload": json.dumps(
                    {
                        "database": 1,
                        "epoch_id": 0,
                        "last_applied_cursor": None,
                        "sync_params": '{"locale":"en_US"}',
                        "version": 27510149861906152,
                    }
                ),
                "requestType": 1,
            },
        )
