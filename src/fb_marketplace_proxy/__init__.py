import re

from flask import Flask, request, render_template, redirect, url_for, session


from .scraper import Scraper
from .facebook import FacebookClient, FacebookApiError, FacebookAuthCookies


app = Flask(__name__)
application = app
app.secret_key = "test"  # TODO move this into a config


def get_scraper() -> Scraper:
    try:
        auth = FacebookAuthCookies(int(session["c_user"]), session["xs"])
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
        c_user=session.get("c_user", ""),
        xs=session.get("xs", ""),
        user_name=user_name,
    )


@app.post("/settings")
def save_settings():
    c_user = request.form["c_user"]
    xs = request.form["xs"]

    if not re.fullmatch("\\d+", c_user):
        raise Exception("c_user must be numeric")

    session["c_user"] = c_user
    session["xs"] = xs

    return redirect(url_for("settings"))


@app.get("/search")
def search():
    scraper = get_scraper()
    try:
        query = request.args["query"]
    except KeyError:
        return redirect(url_for("index"))

    cursor = request.args.get("cursor")

    results, end_cursor = scraper.search_listings(query, cursor)
    return render_template(
        "search_results.html.jinja", query=query, results=results, end_cursor=end_cursor
    )


@app.get("/listing/<int:listing_id>")
def listing_details(listing_id: int):
    scraper = get_scraper()
    details = scraper.fetch_listing_details(listing_id)
    return render_template(
        "listing_details.html.jinja", listing_id=listing_id, **details
    )


@app.post("/message_seller")
def message_seller():
    # TODO make sure I'm logged in
    scraper = get_scraper()

    listing_id = int(request.form["listing_id"])
    message = request.form["message"]
    print(listing_id)
    print(message)

    chat_thread_url = scraper.message_seller(listing_id, message)
    return redirect(chat_thread_url)
