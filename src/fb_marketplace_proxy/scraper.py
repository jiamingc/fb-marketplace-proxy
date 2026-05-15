from datetime import datetime
from typing import Any
from .facebook import (
    FacebookClient,
    FacebookApiError,
    FacebookMarketplaceCondition,
    FacebookMarketplaceDeliveryType,
)
from typing import NamedTuple, TypedDict, IO


class SearchResult(TypedDict):
    title: str
    image: str
    description: str
    id: int


class SearchResults(NamedTuple):
    results: list[SearchResult]
    end_cursor: str | None


class ListingDetails(TypedDict):
    title: str
    description: str
    images: list[str]
    story: StoryDetails | None


class StoryDetails(TypedDict):
    id: str
    saved: bool


class Scraper:
    def __init__(self, facebook_client: FacebookClient):
        self.facebook_client = facebook_client

    def search_listings(
        self,
        query: str,
        latitude: float | None = None,
        longitude: float | None = None,
        cursor: str | None = None,
    ) -> SearchResults:
        data = self.facebook_client.CometMarketplaceSearchContentContainerQuery(
            query, latitude, longitude, cursor
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
                cursor = data["marketplace_search"]["feed_units"]["page_info"][
                    "end_cursor"
                ]
            else:
                # Sometimes a cursor for irrelevant results is given after the end of relevant results
                cursor = None

        listings = [edge["node"]["listing"] for edge in listing_edges]
        parsed_listings = [self._extract_search_result(listing) for listing in listings]

        return SearchResults(parsed_listings, cursor)

    def fetch_saved_listings(self, cursor: str | None = None) -> SearchResults:
        data = self.facebook_client.CometMarketplaceYouSavedContentPaginationQuery(
            cursor
        )
        all_saves = data["viewer"]["saver_info"]["all_saves"]
        edges = all_saves["edges"]
        page_info = all_saves["page_info"]

        listings = [edge["node"]["savable"] for edge in edges]
        parsed_listings = [self._extract_search_result(listing) for listing in listings]

        cursor = page_info["end_cursor"] if page_info["has_next_page"] else None

        # TODO does this have pagination?
        return SearchResults(parsed_listings, cursor)

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

        story_details = (
            StoryDetails(
                id=story["id"],
                saved=story["save_info"]["viewer_save_state"] == "SAVED",
            )
            if (story := item["story"]) is not None
            else None
        )

        return ListingDetails(
            title=title,
            description=description,
            images=self.fetch_images(listing_id),
            story=story_details,
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

    def save_listing(self, story_id: str):
        data = self.facebook_client.useCometMarketplaceSaveAsStoryMutation(story_id)
        assert data["story_save"]["story"]["save_info"]["viewer_save_state"] != "SAVED"

    def unsave_listing(self, story_id: str):
        data = self.facebook_client.useCometMarketplaceUnsaveAsStoryMutation(story_id)
        assert (
            data["story_unsave"]["story"]["save_info"]["viewer_save_state"]
            != "NOT_SAVED"
        )
