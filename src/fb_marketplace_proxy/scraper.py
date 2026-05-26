from enum import StrEnum
from datetime import datetime
from typing import Any
from .facebook import (
    FacebookClient,
    FacebookApiError,
    FacebookMarketplaceCondition,
    FacebookMarketplaceDeliveryType,
    FacebookMarketplaceSellerThreadLabel,
    FacebookMarketplaceAvailability,
)
from typing import NamedTuple, TypedDict, IO


class PaginatedList[T](NamedTuple):
    items: list[T]
    end_cursor: str | None


class SearchResult(TypedDict):
    title: str
    image: str
    description: str
    id: int


class ListingDetails(TypedDict):
    id: int
    title: str
    description: str
    status: ListingStatus
    images: list[str]
    story: StoryDetails | None
    is_yours: bool


class ListingStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PENDING = "PENDING"
    SOLD = "SOLD"
    IN_STOCK = "IN_STOCK"


class StoryDetails(TypedDict):
    id: str
    saved: bool


class MessageThread(TypedDict):
    id: int
    unread_count: int
    snippet: str
    peer_name: str
    listing_info: MessageThreadListingInfo | None


class MessageThreadListingInfo(TypedDict):
    id: int
    title: str
    image: str


class YourListingDetails(TypedDict):
    id: int
    title: str
    image: str
    status_indicator: ListingStatusIndicator
    # status field to capture is_live, is_pending, is_sold, is_draft?


class ListingStatusIndicator(TypedDict):
    content: str
    style: ListingStatusIndicatorStyle


class ListingStatusIndicatorStyle(StrEnum):
    WARNING = "WARNING"
    INFO = "INFO"


def parse_paginated_connection(connection: dict) -> tuple[list, str | None]:
    nodes = [edge["node"] for edge in connection["edges"]]
    page_info = connection["page_info"]
    end_cursor = page_info["end_cursor"] if page_info["has_next_page"] else None

    return nodes, end_cursor


class Scraper:
    def __init__(self, facebook_client: FacebookClient):
        self.facebook_client = facebook_client

    def search_listings(
        self,
        query: str,
        latitude: float | None = None,
        longitude: float | None = None,
        cursor: str | None = None,
    ) -> PaginatedList[SearchResult]:
        data = self.facebook_client.CometMarketplaceSearchContentContainerQuery(
            query, latitude, longitude, cursor
        )

        feed_units, end_cursor = parse_paginated_connection(
            data["marketplace_search"]["feed_units"]
        )
        for idx, feed_unit in enumerate(feed_units):
            unit_type = feed_unit["__typename"]
            if unit_type == "MarketplaceFeedListingStoryObject":
                continue

            assert unit_type in [
                "MarketplaceSearchFeedHeader",
                "MarketplaceSearchFeedNoResults",
            ], f"unexpected feed unit type: {unit_type}"

            # We found a feed header, which marks the end of the regular search results
            feed_units = feed_units[:idx]
            end_cursor = None
            break
        else:
            if len(feed_units) < 24:
                # Sometimes a cursor for irrelevant results is given after the end of relevant results
                end_cursor = None

        listings = [feed_unit["listing"] for feed_unit in feed_units]
        parsed_listings = [self._extract_search_result(listing) for listing in listings]

        return PaginatedList(parsed_listings, end_cursor)

    def fetch_saved_listings(
        self, cursor: str | None = None
    ) -> PaginatedList[SearchResult]:
        data = self.facebook_client.CometMarketplaceYouSavedContentPaginationQuery(
            cursor
        )
        saves, end_cursor = parse_paginated_connection(
            data["viewer"]["saver_info"]["all_saves"]
        )

        listings = [save["savable"] for save in saves]
        parsed_listings = [self._extract_search_result(listing) for listing in listings]

        return PaginatedList(parsed_listings, end_cursor)

    def _extract_search_result(self, listing: dict[str, Any]) -> SearchResult:
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

        return SearchResult(
            title=listing.get("marketplace_listing_title", ""),
            image=image,
            description=f"Price: {price}\nLocation: {location}",
            id=int(listing.get("id", "0")),
        )

    def fetch_images(self, listing_id: int) -> list[str]:
        data = self.facebook_client.MarketplacePDPC2CMediaViewerWithImagesQuery(
            listing_id
        )

        listing_photos = data["viewer"]["marketplace_product_details_page"]["target"][
            "listing_photos"
        ]

        image_urls = [photo["image"]["uri"] for photo in listing_photos]
        return image_urls

    def fetch_listing_details(self, listing_id: int) -> ListingDetails:
        data = self.facebook_client.MarketplacePDPContainerQuery(listing_id)

        item = data["viewer"]["marketplace_product_details_page"]["target"]

        status = ListingStatus(item["renderable_listing_status"])

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

        story_details = (
            StoryDetails(
                id=story["id"],
                saved=story["save_info"]["viewer_save_state"] == "SAVED",
            )
            if (story := item["story"]) is not None
            else None
        )

        return ListingDetails(
            id=int(item["id"]),
            title=title,
            description=description,
            status=status,
            images=self.fetch_images(listing_id),
            story=story_details,
            is_yours=item["is_viewer_seller"],
        )

    def get_user_name(self) -> str | None:
        try:
            data = self.facebook_client.CometSettingsDropdownTriggerQuery()
        except FacebookApiError:
            return None
        else:
            return data["viewer"]["actor"]["name"]

    def message_seller(self, listing_id: int, message: str) -> int:
        data = self.facebook_client.CometMarketplaceMessageSellerMutation(
            listing_id, message
        )

        return data["marketplace_message_seller"]["thread_id"]

    def upload_photo(self, image: IO[bytes]) -> int:
        response = self.facebook_client.uploadPhoto(image)
        return int(response["payload"]["photoID"])

    def create_listing(
        self,
        title: str,
        description: str,
        photos: list[IO[bytes]],
        price: int,
        condition: FacebookMarketplaceCondition,
        delivery_types: list[FacebookMarketplaceDeliveryType],
        latitude: float,
        longitude: float,
    ) -> int:
        photo_ids = [self.upload_photo(photo) for photo in photos]
        data = self.facebook_client.useCometMarketplaceListingCreateMutation(
            title,
            description,
            photo_ids,
            price,
            condition,
            delivery_types,
            latitude,
            longitude,
        )

        return int(data["marketplace_listing_create"]["listing"]["id"])

    def set_listing_availability(
        self, story_id: str, availability: FacebookMarketplaceAvailability
    ) -> None:
        self.facebook_client.CometProductItemChangeAvailabilityMutation(
            story_id, availability
        )

    def delete_listing(self, listing_id: int) -> None:
        self.facebook_client.useCometMarketplaceForSaleItemDeleteMutation(listing_id)

    def _extract_your_listing_info(self, listing: dict[str, Any]) -> YourListingDetails:
        return YourListingDetails(
            id=listing["id"],
            title=listing["marketplace_listing_title"],
            image=listing["primary_listing_photo"]["image"]["uri"],
            status_indicator=(status_indicator := listing["listing_status_indicator"])
            and ListingStatusIndicator(
                content=status_indicator["content"],
                style=ListingStatusIndicatorStyle(status_indicator["style"]),
            ),
        )

    def fetch_your_active_listings(
        self, cursor: str | None = None
    ) -> PaginatedList[YourListingDetails]:
        data = self.facebook_client.CometMarketplaceYouSellingFastActiveSectionPaginationQuery(
            cursor
        )
        listing_sets, end_cursor = parse_paginated_connection(
            data["viewer"]["marketplace_listing_sets"]
        )
        listings = [
            self._extract_your_listing_info(listing_set["first_listing"])
            for listing_set in listing_sets
        ]
        return PaginatedList(listings, end_cursor)

    def fetch_your_inactive_listings(
        self, cursor: str | None = None
    ) -> PaginatedList[YourListingDetails]:
        data = self.facebook_client.CometMarketplaceYouSellingFastInactiveSectionPaginationQuery(
            cursor
        )
        listing_sets, end_cursor = parse_paginated_connection(
            data["viewer"]["inactive_listing_sets"]
        )
        listings = [
            self._extract_your_listing_info(listing_set["first_listing"])
            for listing_set in listing_sets
        ]
        return PaginatedList(listings, end_cursor)

    def save_listing(self, story_id: str):
        data = self.facebook_client.useCometMarketplaceSaveAsStoryMutation(story_id)
        assert data["story_save"]["story"]["save_info"]["viewer_save_state"] == "SAVED"

    def unsave_listing(self, story_id: str):
        data = self.facebook_client.useCometMarketplaceUnsaveAsStoryMutation(story_id)
        assert (
            data["story_unsave"]["story"]["save_info"]["viewer_save_state"]
            == "NOT_SAVED"
        )

    def _extract_thread_info(self, thread: dict[str, Any]) -> MessageThread:
        return MessageThread(
            id=thread["thread_key"]["thread_fbid"],
            unread_count=thread["unread_count"],
            snippet=thread["messages"]["edges"][0]["node"]["snippet"],
            peer_name=thread["other_participants"]["edges"][0]["node"][
                "messaging_actor"
            ]["name"],
            listing_info=(item := thread["marketplace_thread_data"]["messageable_item"])
            and MessageThreadListingInfo(
                id=item["id"],
                title=item["marketplace_listing_title"],
                image=item["primary_listing_photo"]["image"]["uri"],
            ),
        )

    def fetch_buyer_chat_threads(
        self, cursor: str | None = None
    ) -> PaginatedList[MessageThread]:
        data = self.facebook_client.CometMarketplaceInboxBuyerTabViewPaginationQuery(
            cursor
        )
        threads, end_cursor = parse_paginated_connection(
            data["viewer"]["marketplaceInboxBuyerMessageThreads"]
        )

        parsed_threads = [self._extract_thread_info(thread) for thread in threads]

        return PaginatedList(parsed_threads, end_cursor)

    def fetch_seller_chat_threads(
        self,
        filter_label: FacebookMarketplaceSellerThreadLabel | None = None,
        cursor: str | None = None,
    ) -> PaginatedList[MessageThread]:
        data = self.facebook_client.CometMarketplaceInboxSellerTabThreadViewPaginationQuery(
            filter_label, cursor
        )
        threads, end_cursor = parse_paginated_connection(
            data["viewer"]["marketplaceInboxSellerMessageThreads"]
        )

        parsed_threads = [self._extract_thread_info(thread) for thread in threads]

        return PaginatedList(parsed_threads, end_cursor)
