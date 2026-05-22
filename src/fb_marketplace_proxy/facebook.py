import json
import re
from enum import IntEnum, StrEnum
from functools import cache
from json import JSONDecodeError
from typing import IO, Any, NamedTuple
from uuid import uuid4

import requests

JSON_HIJACKING_PREFIX = "for (;;);"


class FacebookAuthCookies(NamedTuple):
    c_user: int
    xs: str


class FacebookMarketplaceDeliveryType(StrEnum):
    IN_PERSON = "IN_PERSON"
    PUBLIC_MEETUP = "PUBLIC_MEETUP"
    DOOR_PICKUP = "DOOR_PICKUP"
    DOOR_DROPOFF = "DOOR_DROPOFF"


class FacebookMarketplaceSellerThreadLabel(StrEnum):
    AWAITING_PAYMENT = "Pending payment"
    PAID = "Paid"
    NEEDS_SHIPPING = "To be shipped"
    SHIPPED = "Shipped"
    CASH_ON_DELIVERY = "Cash on delivery"
    COMPLETED = "Completed"


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

        if response.text.startswith(JSON_HIJACKING_PREFIX):
            # Attempt to parse structured error message
            try:
                error = json.loads(response.text.removeprefix(JSON_HIJACKING_PREFIX))
                raise FacebookApiError(
                    "\n".join(
                        [
                            error["errorSummary"],
                            error["errorDescription"],
                            error["redirectTo"],
                        ]
                    )
                )
            except JSONDecodeError:
                raise FacebookApiError(f"Unexpected GraphQL response {response.text}")

        payloads = response.text.split("\n")

        try:
            response_json = json.loads(payloads[0])
        except JSONDecodeError:
            raise FacebookApiError(f"Unexpected GraphQL response {response.text}")

        try:
            data = response_json["data"]
        except KeyError:
            if "errors" in response_json:
                raise FacebookApiError(
                    ", ".join(
                        error.get("message", "") for error in response_json["errors"]
                    )
                )
            else:
                raise FacebookApiError("No data in GraphQL response")

        # Merge deferred payloads
        for payload in payloads[1:]:
            payload_json = json.loads(payload)

            node = data
            for key in payload_json["path"]:
                node = node.setdefault(key, {})

            node.update(payload_json["data"])

        return data

    def CometMarketplaceSearchContentContainerQuery(
        self,
        query: str,
        latitude: float | None,
        longitude: float | None,
        cursor: str | None = None,
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
                        **(
                            {
                                "filter_location_latitude": latitude,
                                "filter_location_longitude": longitude,
                            }
                            if latitude is not None and longitude is not None
                            else {}
                        ),
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

    def CometMarketplaceYouSavedContentPaginationQuery(self, cursor: str | None = None):
        return self._graphql_query(
            26376372915396340,
            {
                "count": 6,
                "cursor": cursor,
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

    def CometMarketplaceInboxBuyerTabViewPaginationQuery(
        self, cursor: str | None = None
    ):
        return self._graphql_query(
            26202731575990325,
            {
                "count": 12,
                "cursor": cursor,
            },
        )

    def CometMarketplaceInboxSellerTabThreadViewPaginationQuery(
        self,
        filter_label: FacebookMarketplaceSellerThreadLabel | None = None,
        cursor: str | None = None,
    ):
        return self._graphql_query(
            25940357548956156,
            {
                "count": 12,
                "cursor": cursor,
                "filterLabels": [
                    {
                        "label_category": "THREAD_LABEL",
                        "label_string": filter_label.value,
                        "label_type": filter_label.name,
                    }
                ]
                if filter_label
                else {},
                "lookBackInDays": 60 if filter_label else None,
            },
        )

    def CometMarketplaceYouSellingFastContentContainerQuery(
        self,
    ):
        return self._graphql_query(
            26599015196447910,
            {
                "count": 5,
                "order": "CREATION_TIMESTAMP_DESC",
                "shouldDeferInfoSection": False,
                "state": None,
                "title_search": None,
            },
        )

    def CometMarketplaceYouSellingFastActiveSectionPaginationQuery(
        self,
    ):
        return self._graphql_query(
            35565035023140261,
            {
                "count": 5,
                "cursor": None,
                "order": "CREATION_TIMESTAMP_DESC",
                "state": None,
                "status": None,
                "title_search": None,
                "__relay_internal__pv__ShouldUpdateMarketplaceBoostListingBoostedStatusrelayprovider": False,
            },
        )

    def CometMarketplaceYouSellingFastInactiveSectionPaginationQuery(
        self,
    ):
        return self._graphql_query(
            27069247962711508,
            {
                "count": 5,
                "cursor": None,
                "order": "CREATION_TIMESTAMP_DESC",
                "state": None,
                "status": None,
                "title_search": None,
                "__relay_internal__pv__ShouldUpdateMarketplaceBoostListingBoostedStatusrelayprovider": False,
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

    def useCometMarketplaceSaveAsStoryMutation(self, story_id: str):
        return self._graphql_query(
            9587699291311838,
            {
                "input": {
                    "actor_id": self.auth_cookies and self.auth_cookies.c_user,
                    "save_mechanism": "SAVED_ADD",
                    "save_surface": "MARKETPLACE_PRODUCT_DETAILS",
                    "story_id": story_id,
                }
            },
        )

    def useCometMarketplaceUnsaveAsStoryMutation(self, story_id: str):
        return self._graphql_query(
            24145675458439589,
            {
                "input": {
                    "actor_id": self.auth_cookies and self.auth_cookies.c_user,
                    "save_mechanism": "SAVED_ADD",
                    "save_surface": "MARKETPLACE_PRODUCT_DETAILS",
                    "story_id": story_id,
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

        return json.loads(response.text.removeprefix(JSON_HIJACKING_PREFIX))

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
