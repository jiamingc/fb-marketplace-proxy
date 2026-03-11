from flask import Flask, request, render_template, redirect, url_for


from .scraper import Scraper
from .facebook import FacebookClient, FacebookApiError

facebook_client = FacebookClient()
scraper = Scraper(facebook_client)

app = Flask(__name__)
application = app


@app.errorhandler(FacebookApiError)
def handle_exception(e: FacebookApiError):
    return render_template("error.html.jinja", message=str(e)), 500


@app.route("/")
def index():
    return render_template("search_form.html.jinja")


@app.route("/search")
def search():
    try:
        query = request.args["query"]
    except KeyError:
        return redirect(url_for("index"))

    cursor = request.args.get("cursor")

    results, end_cursor = scraper.search_listings(query, cursor)
    return render_template(
        "search_results.html.jinja", query=query, results=results, end_cursor=end_cursor
    )


@app.route("/listing/<int:listing_id>")
def listing_details(listing_id: int):
    details = scraper.fetch_listing_details(listing_id)
    return render_template("listing_details.html.jinja", **details)
