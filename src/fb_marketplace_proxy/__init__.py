import re

from flask import Flask, request, render_template, redirect, url_for, session


from .scraper import Scraper
from .facebook import (
    FacebookClient,
    FacebookApiError,
    FacebookAuthCookies,
    FacebookMarketplaceCondition,
    FacebookMarketplaceDeliveryType,
)


app = Flask(__name__)
application = app
app.config.update(
    SECRET_KEY="test",  # TODO move this into a config
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


def get_scraper() -> Scraper:
    try:
        auth = FacebookAuthCookies(session["c_user"], session["xs"])
    except KeyError:
        auth = None

    facebook_client = FacebookClient(auth)
    return Scraper(facebook_client)


@app.errorhandler(FacebookApiError)
def handle_exception(e: FacebookApiError):
    return render_template("error.html.jinja", message=str(e)), 500


@app.get("/")
def index():
    return render_template("search_form.html.jinja")


@app.get("/settings")
def settings():
    if "c_user" in session:
        try:
            scraper = get_scraper()
            user_name = scraper.get_user_name()
        except FacebookApiError:
            user_name = None
    else:
        user_name = None

    return render_template(
        "settings.html.jinja",
        user_name=user_name,
        c_user=session.get("c_user"),
        xs=session.get("xs"),
        latitude=session.get("latitude"),
        longitude=session.get("longitude"),
    )


@app.post("/settings")
def save_settings():
    c_user = request.form["c_user"]
    xs = request.form["xs"]
    latitude = request.form["latitude"]
    longitude = request.form["longitude"]

    if not re.fullmatch("\\d+", c_user):
        raise Exception("c_user must be numeric")

    c_user = int(c_user)

    try:
        latitude = float(latitude)
    except ValueError:
        raise Exception("latitude must be float")

    try:
        longitude = float(longitude)
    except ValueError:
        raise Exception("longitude must be float")

    session["c_user"] = c_user
    session["xs"] = xs
    session["latitude"] = latitude
    session["longitude"] = longitude
    session.permanent = True

    return redirect(url_for("settings"))


@app.get("/saved")
def saved():
    scraper = get_scraper()
    cursor = request.args.get("cursor")
    saves, end_cursor = scraper.fetch_saved_listings(cursor)
    return render_template(
        "saved_listings.html.jinja",
        saves=saves,
        end_cursor=end_cursor,
    )


@app.get("/inbox")
def inbox():
    scraper = get_scraper()
    cursor = request.args.get("cursor")
    threads, end_cursor = scraper.fetch_buyer_chat_threads(cursor)
    return render_template(
        "inbox.html.jinja",
        threads=threads,
        end_cursor=end_cursor,
    )


@app.get("/search")
def search():
    scraper = get_scraper()
    try:
        query = request.args["query"]
    except KeyError:
        return redirect(url_for("index"))

    cursor = request.args.get("cursor")
    latitude = session.get("latitude")
    longitude = session.get("longitude")

    results, end_cursor = scraper.search_listings(query, latitude, longitude, cursor)
    return render_template(
        "search_results.html.jinja", query=query, results=results, end_cursor=end_cursor
    )


@app.get("/listing/<int:listing_id>")
def listing_details(listing_id: int):
    scraper = get_scraper()
    details = scraper.fetch_listing_details(listing_id)
    return render_template(
        "listing_details.html.jinja", listing_id=listing_id, details=details
    )


@app.post("/listing/save")
def save_listing():
    scraper = get_scraper()

    listing_id = request.form["listing_id"]
    story_id = request.form["story_id"]

    scraper.save_listing(story_id)

    return redirect(url_for("listing_details", listing_id=listing_id))


@app.post("/listing/unsave")
def unsave_listing():
    scraper = get_scraper()

    listing_id = request.form["listing_id"]
    story_id = request.form["story_id"]

    scraper.unsave_listing(story_id)

    return redirect(url_for("listing_details", listing_id=listing_id))


@app.post("/message_seller")
def message_seller():
    # TODO make sure I'm logged in
    scraper = get_scraper()

    listing_id = int(request.form["listing_id"])
    message = request.form["message"]

    thread_id = scraper.message_seller(listing_id, message)
    return redirect(f"https://www.facebook.com/messages/t/{thread_id}/")


@app.get("/listing/create")
def create_listing_form():
    return render_template("listing_create.html.jinja")


@app.post("/listing/create")
def create_listing():
    scraper = get_scraper()

    title = request.form["title"]
    description = request.form["description"]
    photos = [file.stream for file in request.files.getlist("photos")]
    price = int(request.form["price"])
    condition = FacebookMarketplaceCondition(request.form["condition"])
    delivery_types = [
        FacebookMarketplaceDeliveryType.IN_PERSON,
        FacebookMarketplaceDeliveryType.DOOR_PICKUP,
    ]
    latitude = session["latitude"]
    longitude = session["longitude"]

    listing_id = scraper.create_listing(
        title,
        description,
        photos,
        price,
        condition,
        delivery_types,
        latitude,
        longitude,
    )

    return redirect(url_for("listing_details", listing_id=listing_id))
